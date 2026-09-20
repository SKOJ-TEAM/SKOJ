# SKOJ 운영 배포 가이드

## 관련 파일

### 운영자가 사용하는 파일

| 파일 | 역할 |
| --- | --- |
| `setup-deployment.sh` | 최초 1회 Nginx Blue/Green 설정과 제한된 전환 권한을 설치합니다. Nginx 템플릿이 변경된 경우에도 다시 실행합니다. |
| `deploy.sh` | 마이그레이션이 없는 릴리스를 비활성 색상에 올린 뒤 Nginx를 전환하는 무중단 배포 진입점입니다. 직전 일반 배포 롤백도 담당합니다. |
| `restart.sh` | 최초 도입, 마이그레이션 또는 비호환 변경을 DB 백업 후 Maintenance 상태에서 배포하는 중단 배포 진입점입니다. |
| `dev.sh` | 운영과 분리된 프로젝트명·포트·데이터로 로컬 개발 서버를 시작하고 종료합니다. 운영 배포에는 사용하지 않습니다. |
| `.env.docker` | 운영 DB, Redis, Django 등 Compose 실행에 필요한 환경 변수를 보관합니다. Git에 포함하지 않습니다. |
| `.deployment/state.env` | 활성 색상과 Blue/Green 이미지·릴리스 정보를 기록합니다. 스크립트가 자동 생성하므로 직접 수정하지 않습니다. |
| `.deployment/history.log` | `deploy.sh`와 `restart.sh`의 주요 배포 기록을 저장합니다. Git에 포함하지 않습니다. |

### 배포 내부 구성 파일

| 파일 | 역할 |
| --- | --- |
| `deploy/lib.sh` | 두 배포 스크립트가 함께 사용하는 잠금, 사전 검사, 이미지 빌드, 상태 저장, health 및 Nginx 전환 함수입니다. 직접 실행하지 않습니다. |
| `compose.yaml` | 운영용 DB, Redis, Bridge, Judge, Blue/Green Web·Celery와 init 서비스 구성을 정의합니다. 운영 배포는 이 파일만 명시적으로 사용합니다. |
| `compose.override.yaml` | 개발 환경에서 build와 소스·설정 mount를 복원합니다. 운영 배포 스크립트에서는 사용하지 않습니다. |
| `dockerfile` | Git SHA를 `RELEASE_ID`로 포함하는 불변 애플리케이션 이미지를 만듭니다. |
| `docker/django/entrypoint.sh` | 컨테이너 시작 시 릴리스별 정적 파일 및 problems 디렉터리를 준비합니다. |
| `docker/django/local_settings.py` | `RELEASE_ID`를 검증하고 릴리스별 `STATIC_ROOT`와 `STATIC_URL`을 설정합니다. |
| `deploy/skoj-nginx-switch` | Blue, Green, Legacy, Maintenance 중 하나로 Nginx route를 안전하게 전환합니다. 설치 후 `/usr/local/sbin/`에서 실행됩니다. |
| `deploy/nginx/skoj.conf` | SKOJ 운영 Nginx virtual host 템플릿입니다. |
| `deploy/nginx/routes/blue.conf` | Blue Web의 `127.0.0.1:8001` route입니다. |
| `deploy/nginx/routes/green.conf` | Green Web의 `127.0.0.1:8002` route입니다. |
| `deploy/nginx/routes/legacy.conf` | 최초 전환 전 기존 Web의 `127.0.0.1:8000` 호환 route입니다. |
| `deploy/nginx/routes/maintenance.conf` | 중단 배포와 장애 대응에 사용하는 Maintenance route입니다. |
| `deploy/nginx/maintenance.html` | Maintenance route가 반환하는 안내 페이지입니다. |

### 상태 확인과 검증 파일

| 파일 | 역할 |
| --- | --- |
| `site/judge/views/health.py` | Web, MariaDB, Redis와 현재 `RELEASE_ID`를 확인하는 `/healthz/` readiness endpoint입니다. |
| `site/dmoj/urls.py` | `/healthz/` URL을 Django에 연결합니다. |
| `site/judge/views/tests/test_health.py` | health endpoint의 정상 및 장애 응답을 검증합니다. |
| `tests/test_docker_configuration.py` | 운영 Compose의 소스 mount 금지, Blue/Green 구성과 배포 스크립트의 안전 조건을 검증합니다. |
| `.dockerignore` | 로컬 배포 상태와 불필요한 파일이 운영 이미지 build context에 들어가지 않도록 제외합니다. |
| `.gitignore` | `.deployment/`의 서버별 상태와 로그가 Git에 포함되지 않도록 제외합니다. |
| `DOCKER.md` | 개발용 Compose 실행 방법과 운영 Blue/Green 구성의 차이를 설명합니다. |

이 문서는 단일 운영 서버에서 Web을 Blue/Green으로 전환하는 절차를 설명합니다. 서버 자체, MariaDB 또는 Redis 장애를 복구하는 고가용성 구성은 포함하지 않습니다.

## 구성 원칙

- Web Blue는 호스트 `127.0.0.1:8001`, Green은 `127.0.0.1:8002`를 사용합니다.
- Nginx는 `/etc/nginx/skoj/active.conf`로 Blue, Green, Maintenance 중 하나를 선택합니다.
- DB, Redis, media, problems는 두 색상이 공유합니다.
- `deploy.sh`는 Bridge와 Judge를 재시작하지 않습니다. `restart.sh`는 기존 채점 완료 후 Bridge를 새 릴리스로 교체하고 실행 중인 Judge의 재연결을 확인합니다.
- 운영 컨테이너는 `./site`를 mount하지 않고 `skoj-app:<Git SHA>` 이미지를 실행합니다.
- `.deployment/state.env`는 활성 색상과 현재·직전 이미지를 기록하는 로컬 상태이며 Git에 포함하지 않습니다.

## 최초 설치

먼저 변경을 커밋하고 운영 서버의 `HEAD`가 배포하려는 SHA인지 확인합니다. 실제 `.env.docker`와 영속 데이터 디렉터리를 보존합니다.

```sh
sudo ./setup-deployment.sh
```

설치 프로그램은 기존 `/etc/nginx/conf.d/nginx.conf`를 `/etc/nginx/skoj-backup-<시각>/`에 보관합니다. 설치 직후에는 기존 `127.0.0.1:8000` Web을 가리키는 `legacy` route를 사용하므로 설정 설치만으로 Web이 중단되지 않습니다.

최초 managed 배포는 중단 배포로 수행합니다. 기존 Web·Celery 종료 및 채점 완료 확인 후 Bridge를 불변 이미지로 재생성합니다. 최초 도입에서는 Judge 두 서비스를 시작하고 연결을 확인합니다.

```sh
./restart.sh
```

## 무중단 배포

```sh
./deploy.sh
```

## Bridge 변경을 포함한 중단 배포

변경을 검증·커밋한 뒤 `./restart.sh`를 실행합니다. 현재 HEAD를 새 이미지로 빌드한 후 다음 순서로 진행합니다.

1. 점검 화면 전환 → Web의 진행 중 요청 종료 → Celery의 진행 중 작업 종료.
2. 기존 Bridge를 유지한 채 대기·처리·채점 중 제출(`QU/P/G`)이 모두 완료될 때까지 대기.
3. Bridge 정지 → 검증된 DB 백업 → 초기화·마이그레이션.
4. 새 릴리스 이미지로 Bridge 교체 → 환경 설정의 Judge 2개가 이번 교체 이후 새로 연결됐는지 확인.
5. 새 Web·Celery 검증 → 사이트 재개 → Bridge 이미지를 포함한 배포 상태 저장.

`SKOJ_JUDGE_DRAIN_TIMEOUT`은 채점 완료 대기(기본600초), `SKOJ_JUDGE_READY_TIMEOUT`은 재연결 대기(기본120초)를 조절합니다. 완료 대기 실패 시 기존 Bridge를 정지하지 않습니다. 이후 단계 실패 시에도 점검 화면을 유지하며 자동 재채점이나 DB 복원은 하지 않습니다. 대기 중인 제출을 강제로 무시하지 마세요. Bridge 시작 시 미완료 제출은 IE로 처리됩니다.

언어별 메모리는 관리자에서 숫자와 KB/MB를 함께 입력합니다. `1024 + MB`는 내부적으로1048576KB로 저장됩니다. 기존1024KB 설정은1MB로 표시·보존되므로 필요한 경우 직접 변경 후 재채점합니다.

## 무중단 배포 상세

인자를 생략하면 현재 `HEAD`를 배포하며, 필요한 경우에만 `./deploy.sh <git-sha>`로 명시할 수 있습니다. 스크립트는 dirty worktree와 현재 HEAD가 아닌 SHA를 거부합니다. 빌드 전 Compose 유효성, 최소 4GiB 여유 공간, MariaDB·Redis health를 검사하며 `SKOJ_MIN_FREE_KB`로 공간 기준을 높일 수 있습니다. 이미지를 만든 뒤 모델 누락 마이그레이션과 운영 DB의 미적용 마이그레이션을 검사합니다. 미적용 마이그레이션이 하나라도 있으면 DB, 실행 컨테이너, Nginx를 변경하지 않고 종료 코드 `20`으로 중단합니다.

```text
Blue/Green deployment rejected: pending database migrations detected.
Run: ./restart.sh
```

마이그레이션이 없으면 비활성 Web의 health/smoke 검사를 통과한 뒤 Nginx를 원자적으로 전환합니다. 실제 HTTPS 검사까지 성공하면 새 Celery를 올리고 기존 Celery를 warm shutdown합니다. 이전 Web은 즉시 롤백을 위해 계속 실행합니다.

다음 변경은 Django가 자동 판별할 수 없으므로 마이그레이션이 없어도 개발자가 `restart.sh`를 선택합니다.

- Celery task 이름 또는 인자의 비호환 변경
- Redis에 저장한 Python 객체나 캐시 형식의 비호환 변경
- media 또는 problems에 기록하는 공유 파일 형식의 비호환 변경
- 구버전과 신버전이 동시에 동작할 수 없는 외부 연동 변경

## 즉시 롤백

```sh
./deploy.sh rollback
```

직전 Web과 Celery 이미지가 준비된 것을 확인한 뒤 Nginx를 이전 색상으로 전환합니다. DB 스키마는 변경하지 않습니다. 중단 배포는 마이그레이션을 포함할 수 있으므로 이 명령의 즉시 롤백 대상이 아닙니다.

## 마이그레이션이 있는 중단 배포

```sh
./restart.sh
```

수행 순서는 위의 Bridge 변경 중단 배포와 같습니다. 기존 채점 완료 후 Bridge를 정지하고 DB dump와 `initialize_docker`를 실행한 뒤 새 Bridge의 Judge 재연결을 확인합니다. DB, Redis, 실행 중인 Judge는 보존합니다. Redis DB 1의 Django 캐시만 비우며 DB 0의 Celery queue는 보존합니다.

백업은 기본적으로 `/home/songg9572/skoj-backups/skoj-pre-deploy-<시각>.sql.gz`에 권한 `0600`으로 생성됩니다. dump 생성이나 gzip 검증이 실패하면 migrate를 실행하지 않습니다. 실패 후에는 Maintenance 화면을 유지하므로 로그와 DB 상태를 확인한 뒤 복구합니다.

### DB 수동 복원

DB 복원은 현재 데이터를 덮어쓰는 작업이므로 배포 스크립트가 자동 수행하지 않습니다. 반드시 Maintenance 상태와 복원 대상 dump를 확인한 뒤 관리자가 실행합니다.

```sh
gzip -t /home/songg9572/skoj-backups/<backup>.sql.gz
gzip -dc /home/songg9572/skoj-backups/<backup>.sql.gz | \
  docker compose --env-file .env.docker -f compose.yaml exec -T db sh -c \
  'exec mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" "$MARIADB_DATABASE"'
```

복원 뒤에는 적용된 migration 목록, 핵심 테이블 행 수, Web health를 확인하고 새 코드 또는 이전 호환 코드로 서비스를 기동합니다.

## Nginx 운영

일반 배포에서는 설정 파일을 직접 편집하지 않습니다.

```sh
sudo -n /usr/local/sbin/skoj-nginx-switch blue
sudo -n /usr/local/sbin/skoj-nginx-switch green
sudo -n /usr/local/sbin/skoj-nginx-switch maintenance
```

전환 도구는 허용된 이름만 받아 심볼릭 링크를 교체하고 `nginx -t` 성공 후에만 reload합니다. 검사 또는 reload 실패 시 이전 링크를 복원합니다. 저장소의 Nginx 템플릿 자체가 변경됐을 때만 `sudo ./setup-deployment.sh`를 다시 실행하며, 실행 전에 기존 설정이 별도 디렉터리에 백업됩니다.

현재 상태와 로그는 다음으로 확인합니다.

```sh
readlink /etc/nginx/skoj/active.conf
sudo journalctl -t skoj-deploy
docker compose --env-file .env.docker --env-file .deployment/state.env \
  --profile deployment -f compose.yaml ps
```

## Judge 증설

Judge 증설은 Web 배포와 분리합니다. 고유한 Judge 이름·키를 Admin에 등록하고 독립 서비스로 추가한 뒤 해당 Judge만 기동합니다. 기존 Bridge, Redis, Web 색상은 변경하지 않습니다.

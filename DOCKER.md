# Linux Docker 개발 환경

이 구성은 AMD64 또는 ARM64 Linux 서버의 Docker Engine에서 Ubuntu 22.04 기반 SKOJ 웹 애플리케이션과 MariaDB, Redis, Celery, Bridge, DMOJ Judge를 함께 실행합니다. Docker가 호스트 아키텍처에 맞는 이미지를 자동으로 선택합니다. 로컬 접근용이므로 웹 서비스는 `127.0.0.1:8000`에만 공개되며 Nginx와 HTTPS는 포함하지 않습니다.

## 1. 준비

- AMD64 또는 ARM64 Linux
- Docker Engine과 Docker Compose 플러그인
- 사용 가능 메모리 4GB 이상 권장
- `SYS_PTRACE` capability를 허용하는 일반 Docker 환경(rootless 또는 ptrace 제한 환경 제외)

프로젝트 루트에서 환경 파일과 영구 데이터 디렉터리를 준비합니다.

```sh
cp .env.docker.example .env.docker
mkdir -p data/mariadb logs problems
```

- `data/mariadb`: MariaDB 데이터
- `logs`: Django Web, Celery, Bridge 및 초기화 로그
- `problems`: 문제와 테스트 데이터

세 경로는 호스트 bind mount이므로 일반 종료뿐 아니라 `docker compose down --volumes`를 실행해도 삭제되지 않습니다.

`.env.docker`에서 최소한 다음 값을 다른 문자열로 변경합니다.

- `SECRET_KEY`
- `DB_PASSWORD`
- `DB_ROOT_PASSWORD`
- `JUDGE_KEY`

`JUDGE_KEY`는 자동 초기화와 Judge 컨테이너가 동일하게 사용합니다. 기본값 `change-me`로는 초기화가 실패합니다. `.env.docker`는 Git에서 제외되므로 커밋하지 않습니다.

Judge는 기본적으로 AMD64와 ARM64를 모두 제공하는 `dmoj/runtimes-tier1:latest` 이미지를 사용합니다. 특정 런타임 이미지를 사용해야 하면 `.env.docker`의 `DMOJ_RUNTIMES_IMAGE`를 변경할 수 있습니다.

## 2. 전체 서비스 시작 및 자동 초기화

```sh
docker compose --env-file .env.docker up -d --build
```

처음에는 Ubuntu 패키지, Python 라이브러리, DMOJ 런타임을 내려받으므로 시간이 걸릴 수 있습니다.

Compose의 `init` 서비스는 MariaDB와 Redis가 정상 상태가 될 때까지 기다린 뒤 다음 작업을 자동으로 수행합니다.

컨테이너에서는 `python manage.py initialize_docker` 관리 명령이 실행됩니다.

- 데이터베이스 마이그레이션
- 정적 파일 수집
- `.env.docker`의 이름과 키를 사용한 Judge 등록 또는 인증 키 갱신

초기화 상태와 로그는 다음 명령으로 확인합니다.

```sh
docker compose --env-file .env.docker ps -a
docker compose --env-file .env.docker logs init
```

`init`가 종료 코드 0으로 완료된 뒤 Web, Celery, Bridge가 시작됩니다. 이 작업은 반복 실행해도 안전하며 같은 이름의 Judge가 있으면 중복 생성하지 않고 인증 키를 현재 `.env.docker` 값으로 갱신합니다.

## 3. 관리자 계정 생성

관리자 비밀번호를 환경 파일에 저장하지 않도록 이 단계만 대화형 명령으로 한 번 실행합니다.

```sh
docker compose --env-file .env.docker exec web python manage.py createsuperuser
```

브라우저에서 <http://127.0.0.1:8000> 또는 <http://127.0.0.1:8000/admin>을 엽니다.

서비스 상태와 로그는 다음 명령으로 확인합니다.

```sh
docker compose --env-file .env.docker ps
docker compose --env-file .env.docker logs -f web bridge judge
```

Judge가 `online`이 되지 않으면 `JUDGE_NAME`과 `JUDGE_KEY`가 등록할 때 사용한 값과 같은지 먼저 확인합니다. `bridge`와 `judge` 로그에 인증 실패 또는 문제 디렉터리 오류가 있는지도 확인합니다.

## 4. 종료와 재시작

컨테이너를 종료하되 데이터베이스는 유지합니다.

```sh
docker compose --env-file .env.docker down
```

다시 시작할 때는 `docker compose --env-file .env.docker up -d`를 실행하면 됩니다. `init`가 다시 현재 구성을 적용한 뒤 종료됩니다. MariaDB 데이터, 애플리케이션 로그, 문제 데이터는 각각 호스트의 `./data/mariadb`, `./logs`, `./problems`에 유지됩니다. Redis 데이터는 Docker named volume에 유지됩니다.

`down --volumes`를 실행하면 Redis와 수집된 정적 파일의 named volume은 삭제되지만 호스트 bind mount인 MariaDB, 로그, 문제 데이터는 삭제되지 않습니다. MariaDB를 초기화하려면 컨테이너를 내린 상태에서 `DB_DATA_DIR`의 실제 호스트 디렉터리를 별도로 비워야 하므로, 필요한 데이터를 먼저 백업하세요.

기존 `mariadb_data` named volume을 사용한 적이 있다면 이 변경이 그 데이터를 자동으로 `./data/mariadb`로 옮기지는 않습니다. 기존 데이터가 필요한 환경에서는 새 구성을 시작하기 전에 SQL dump/restore 방식으로 이전하세요.

## 구성 개요

- `web`: Django 개발 서버, 호스트의 `127.0.0.1:8000`에만 공개
- `db`: MariaDB 10.11, Docker 내부 네트워크 전용, 데이터는 `./data/mariadb`에 저장
- `redis`: 캐시 및 Celery 브로커, Docker 내부 네트워크 전용
- `init`: 마이그레이션, 정적 파일 수집, Judge 등록 후 종료되는 초기화 작업
- `celery`: 비동기 작업 처리
- `bridge`: 웹 애플리케이션과 Judge 연결
- `judge`: 호스트 아키텍처에 맞는 Tier 1 런타임 기반 DMOJ 채점기

웹 소스는 `./site`가 컨테이너에 마운트되므로 Python과 프론트엔드 파일 변경이 개발 서버에 반영됩니다. Django 계열 서비스의 파일 로그는 `./logs`에 저장됩니다. Docker 전용 설정은 추적 중인 `settings.example.py`를 기본값으로 사용하고 `docker/django/local_settings.py`에서 Linux 경로와 서비스 주소를 적용합니다.

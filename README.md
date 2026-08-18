# SKOJ

SKOJ(SKALA Online Judge)는 SK가 주관하는 SKALA 교육과정의 교육생을 위한 알고리즘 문제 풀이 및 자동 채점 사이트입니다.

교육생은 다양한 알고리즘 문제를 풀고 코드를 제출해 채점 결과를 바로 확인할 수 있습니다. 운영진은 문제와 테스트 케이스를 관리하고, 교육 과정에 맞춘 과제와 대회를 운영할 수 있습니다.

## 주요 기능

- 알고리즘 문제 조회 및 코드 제출
- 제출 코드 자동 채점과 결과 확인
- 문제별 시간 및 메모리 제한 적용
- 과제와 프로그래밍 대회 운영
- 대회 순위표 및 제출 현황 제공
- 문제, 테스트 케이스 및 채점기 관리
- 여러 프로그래밍 언어 지원

## 기술 기반

SKOJ는 [DMOJ Online Judge](https://github.com/DMOJ/online-judge)를 기반으로 구성했습니다. 웹 애플리케이션과 채점 환경은 다음 서비스로 이루어집니다.

- Django 기반 웹 애플리케이션
- DMOJ Judge 및 Bridge
- MariaDB
- Redis 및 Celery
- Docker Compose 기반 실행 환경

## 실행 방법

AMD64 또는 ARM64 Linux 서버에서 Docker Compose로 웹, 데이터베이스, 비동기 작업 처리기와 채점기를 함께 실행할 수 있습니다.

환경 설정과 최초 실행 방법은 [Docker 실행 가이드](DOCKER.md)를 참고하세요.

```bash
cp .env.docker.example .env.docker
mkdir -p data/mariadb data/static logs problems
docker compose --env-file .env.docker up -d --build
```

`.env.docker`에는 데이터베이스 비밀번호, Django Secret Key와 Judge 인증 키 등 실제 운영 값을 설정해야 합니다. 이 파일은 Git에 커밋하지 않습니다.

## 프로젝트 구조

```text
SKOJ/
├── site/                 # Django 및 DMOJ 웹 애플리케이션
├── docker/django/        # Docker 전용 Django 설정
├── docker/judge/         # DMOJ Judge 이미지와 설정
├── compose.yaml          # 전체 서비스 구성
├── dockerfile            # 웹·Celery·Bridge 공용 이미지
├── tests/                # Docker 구성 회귀 테스트
└── DOCKER.md             # 설치 및 운영 가이드
```

## 개발 및 검증

Docker 구성 변경 후 다음 테스트를 실행합니다.

```bash
python3 -m unittest tests.test_docker_configuration
```

## 라이선스

이 프로젝트는 [GNU Affero General Public License v3.0](site/LICENSE)에 따라 배포됩니다. 기반 프로젝트인 DMOJ의 라이선스와 저작권 고지를 준수합니다.

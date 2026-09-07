#!/usr/bin/env bash

# 운영 Blue/Green 컨테이너와 분리된 로컬 개발 서버를 관리하는 스크립트입니다.
#
# 사용 방법:
#   ./dev.sh up                 DB·Redis·초기화·Web만 시작
#   ./dev.sh up-full            Web과 Celery·Bridge·Judge 2개까지 시작
#   ./dev.sh down               개발 컨테이너만 종료하고 데이터는 보존
#   ./dev.sh status             개발 컨테이너 상태 확인
#   ./dev.sh logs [서비스...]   로그 확인, 서비스 생략 시 web-blue 로그 확인
#   ./dev.sh init               migration과 개발 초기화만 다시 실행
#   ./dev.sh shell              실행 중인 Web에서 Django shell 열기
#
# 기본 접속 주소는 http://127.0.0.1:18000 입니다.
# 포트는 SKOJ_DEV_WEB_PORT, SKOJ_DEV_GREEN_PORT, SKOJ_DEV_DB_PORT로 바꿀 수 있습니다.
# 환경 파일은 기본 `.env.docker`이며 SKOJ_DEV_ENV_FILE로 다른 파일을 지정할 수 있습니다.

set -Eeuo pipefail

readonly SCRIPT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
readonly PROJECT_NAME=${SKOJ_DEV_PROJECT_NAME:-skoj-dev}
readonly ENV_FILE=${SKOJ_DEV_ENV_FILE:-$SCRIPT_ROOT/.env.docker}
readonly DEV_ROOT=${SKOJ_DEV_ROOT:-$SCRIPT_ROOT/.development}

# 운영 기본 포트 8001/8002/3306과 겹치지 않는 개발 전용 포트를 Compose에 전달합니다.
export BLUE_WEB_HOST_PORT=${SKOJ_DEV_WEB_PORT:-18000}
export GREEN_WEB_HOST_PORT=${SKOJ_DEV_GREEN_PORT:-18002}
export DB_HOST_PORT=${SKOJ_DEV_DB_PORT:-13306}

# 운영 bind mount와 데이터가 섞이지 않도록 모든 개발 데이터 경로를 별도 디렉터리에 둡니다.
export DB_DATA_DIR=$DEV_ROOT/data/mariadb
export STATIC_DIR=$DEV_ROOT/data/static
export MEDIA_DIR=$DEV_ROOT/data/media
export LOGS_DIR=$DEV_ROOT/logs
export PROBLEMS_DIR=$DEV_ROOT/problems
export SKOJ_ENV_FILE=$ENV_FILE

die() {
    printf '오류: %s\n' "$*" >&2
    exit 1
}

compose() {
    # 파일과 프로젝트명을 모두 명시해 운영 `skoj` 프로젝트를 조작하지 않도록 합니다.
    docker compose \
        --project-name "$PROJECT_NAME" \
        --env-file "$ENV_FILE" \
        --profile tools \
        -f "$SCRIPT_ROOT/compose.yaml" \
        -f "$SCRIPT_ROOT/compose.override.yaml" \
        "$@"
}

prepare() {
    command -v docker >/dev/null 2>&1 || die 'docker 명령을 찾을 수 없습니다.'
    [[ -f "$ENV_FILE" ]] || die "환경 파일이 없습니다: $ENV_FILE (먼저 cp .env.docker.example .env.docker 실행)"

    # down 후 다시 시작해도 개발 DB와 정적·미디어·문제 데이터를 그대로 사용합니다.
    mkdir -p \
        "$DB_DATA_DIR" "$STATIC_DIR" "$MEDIA_DIR" "$LOGS_DIR" "$PROBLEMS_DIR"

    compose config --quiet
}

initialize() {
    # 공유 의존성을 먼저 시작하고 healthy가 되면 현재 개발 소스로 init을 실행합니다.
    compose up -d db redis
    compose build init
    compose run --rm init
}

start_core() {
    initialize
    # 화면 개발에 필요한 Web만 시작하고 비동기·채점 서비스는 기본 실행에서 제외합니다.
    compose up -d web-blue
    printf '개발 서버가 시작되었습니다: http://127.0.0.1:%s\n' "$BLUE_WEB_HOST_PORT"
}

main() {
    [[ $# -ge 1 ]] || die '사용법: ./dev.sh up|up-full|down|status|logs|init|shell'
    local action=$1
    shift
    prepare

    case "$action" in
        up)
            start_core
            ;;
        up-full)
            start_core
            # 제출과 채점까지 확인할 때만 Celery·Bridge와 Judge 두 개를 추가로 시작합니다.
            compose up -d --build celery-blue bridge judge judge-02
            ;;
        down)
            # --volumes를 사용하지 않아 개발 DB와 Redis 데이터를 다음 실행까지 보존합니다.
            compose down --remove-orphans
            ;;
        status)
            compose ps -a
            ;;
        logs)
            # 서비스명이 없으면 화면 개발에 가장 유용한 Web 로그를 기본으로 봅니다.
            if (($# == 0)); then
                set -- web-blue
            fi
            compose logs --tail 200 -f "$@"
            ;;
        init)
            initialize
            ;;
        shell)
            compose exec web-blue python manage.py shell
            ;;
        *)
            die "알 수 없는 명령입니다: $action"
            ;;
    esac
}

main "$@"

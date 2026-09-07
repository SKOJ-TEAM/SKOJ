#!/usr/bin/env bash

# `deploy.sh`와 `restart.sh`가 공통으로 불러오는 배포 함수 모음입니다.
#
# 사용 방법:
# - 관리자가 직접 실행하는 파일이 아닙니다.
# - 실행 진입점은 무중단 배포 `./deploy.sh` 또는 중단 배포
#   `./restart.sh`를 사용합니다. 특정 Git SHA가 필요할 때만 인자로 지정합니다.
# - 다른 배포 스크립트에서 사용할 때만 다음과 같이 source 합니다.
#     source "$(dirname "${BASH_SOURCE[0]}")/deploy/lib.sh"
#
# 담당 역할:
# - `.deployment/state.env`의 Blue/Green 활성 상태를 안전하게 읽고 저장합니다.
# - 배포 잠금, 사전 검사, 불변 이미지 빌드와 운영 Compose 실행을 담당합니다.
# - Web/Celery readiness, smoke test, Nginx 전환에 필요한 공통 함수를 제공합니다.
# - 운영 Compose는 `compose.yaml`을 명시해 개발용 `compose.override.yaml`이 자동으로
#   적용되거나 호스트 소스가 mount되는 일을 방지합니다.

# 이 파일을 source한 상위 스크립트에도 엄격한 오류 처리를 적용합니다.
set -Eeuo pipefail

# 경로와 운영 기본값을 한곳에서 고정하고 필요한 경우 전용 환경 변수로만 재정의합니다.
readonly PROJECT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
readonly DEPLOYMENT_DIR="${SKOJ_DEPLOYMENT_DIR:-$PROJECT_ROOT/.deployment}"
readonly STATE_FILE="${SKOJ_STATE_FILE:-$DEPLOYMENT_DIR/state.env}"
readonly LOCK_FILE="${SKOJ_LOCK_FILE:-$DEPLOYMENT_DIR/deploy.lock}"
readonly ENV_FILE="${SKOJ_ENV_FILE:-$PROJECT_ROOT/.env.docker}"
readonly COMPOSE_FILE="$PROJECT_ROOT/compose.yaml"
readonly NGINX_SWITCH="${SKOJ_NGINX_SWITCH:-/usr/local/sbin/skoj-nginx-switch}"
readonly PUBLIC_URL="${SKOJ_PUBLIC_URL:-https://skoj.site}"
readonly HEALTH_ATTEMPTS="${SKOJ_HEALTH_ATTEMPTS:-30}"
readonly MIN_FREE_KB="${SKOJ_MIN_FREE_KB:-4194304}"

log() {
    local line
    line="[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] $*"
    printf '%s\n' "$line" >&2
    # 배포 디렉터리가 준비된 뒤부터 화면 출력과 같은 내용을 권한 0600 로그에 남깁니다.
    if [[ -d "$DEPLOYMENT_DIR" ]]; then
        umask 077
        printf '%s\n' "$line" >>"$DEPLOYMENT_DIR/history.log"
    fi
}

die() {
    log "ERROR: $*" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

prepare_runtime() {
    # 배포 흐름에서 사용하는 외부 명령이 모두 설치됐는지 시작 전에 확인합니다.
    require_command docker
    require_command curl
    require_command git
    require_command flock
    require_command sudo
    # 상태·잠금·기록은 배포 계정만 접근하도록 권한을 제한합니다.
    mkdir -p "$DEPLOYMENT_DIR"
    chmod 700 "$DEPLOYMENT_DIR"
    touch "$DEPLOYMENT_DIR/history.log"
    chmod 600 "$DEPLOYMENT_DIR/history.log"
    # 비밀 환경 파일과 root 소유 Nginx 전환 helper가 없으면 배포를 시작하지 않습니다.
    [[ -f "$ENV_FILE" ]] || die "environment file not found: $ENV_FILE"
    [[ -x "$NGINX_SWITCH" ]] || die "Nginx switch helper not installed; run sudo ./setup-deployment.sh"
    # 파일 descriptor 9의 non-blocking flock으로 배포 두 개가 동시에 실행되는 것을 막습니다.
    exec 9>"$LOCK_FILE"
    flock -n 9 || die "another deployment is already running"
}

platform_preflight() {
    local available_kb service container health
    require_command awk
    require_command df

    # 이미지 build나 DB 백업 중 디스크가 고갈되지 않도록 기본 4 GiB를 미리 요구합니다.
    # 더 큰 여유가 필요한 서버는 SKOJ_MIN_FREE_KB로 기준을 높일 수 있습니다.
    available_kb=$(df -Pk "$PROJECT_ROOT" | awk 'NR == 2 {print $4}')
    [[ "$available_kb" =~ ^[0-9]+$ ]] || die "could not determine free disk space"
    ((available_kb >= MIN_FREE_KB)) \
        || die "insufficient disk space: ${available_kb} KiB available, ${MIN_FREE_KB} KiB required"

    # Compose 문법을 검사한 뒤 공유 인프라인 DB와 Redis의 실제 health를 확인합니다.
    compose config --quiet
    for service in db redis; do
        container=$(compose ps -q "$service")
        [[ -n "$container" ]] || die "$service is not running"
        health=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container")
        [[ "$health" == healthy ]] || die "$service is not healthy (status: $health)"
    done
    log "Preflight passed: disk, Compose, MariaDB, and Redis are ready"
}

# 운영 명령은 compose.yaml을 명시해 개발용 compose.override.yaml의 자동 로드와
# 변경 가능한 호스트 소스 mount를 차단합니다.
compose() {
    # state.env가 생성된 이후에는 이미지와 색상 값을 Compose interpolation에 함께 전달합니다.
    local args=(docker compose --env-file "$ENV_FILE")
    if [[ -f "$STATE_FILE" ]]; then
        args+=(--env-file "$STATE_FILE")
    fi
    args+=(--profile deployment --profile tools -f "$COMPOSE_FILE")
    "${args[@]}" "$@"
}

validate_release() {
    local requested=$1
    local resolved head
    # 임의 이미지나 과거 checkout이 배포되지 않도록 요청 SHA가 현재의 깨끗한 HEAD인지 검증합니다.
    resolved=$(git -C "$PROJECT_ROOT" rev-parse --verify "${requested}^{commit}") || die "unknown Git revision: $requested"
    head=$(git -C "$PROJECT_ROOT" rev-parse HEAD)
    [[ "$resolved" == "$head" ]] || die "release must match current HEAD ($head)"
    [[ -z "$(git -C "$PROJECT_ROOT" status --porcelain)" ]] || die "working tree is dirty; commit or stash changes before deployment"
    printf '%s\n' "$resolved"
}

build_release_image() {
    local release=$1
    local image="skoj-app:$release"
    log "Building immutable image $image"
    # 동일 SHA가 이미지 tag, 컨테이너 RELEASE_ID, OCI revision label에 공통으로 기록됩니다.
    docker build \
        --build-arg "RELEASE_ID=$release" \
        --label "org.opencontainers.image.revision=$release" \
        --tag "$image" \
        --file "$PROJECT_ROOT/dockerfile" \
        "$PROJECT_ROOT" >&2
    printf '%s\n' "$image"
}

other_colour() {
    # 활성 색상의 반대편만 다음 후보 슬롯으로 선택할 수 있게 매핑합니다.
    case "$1" in
        blue) printf 'green\n' ;;
        green) printf 'blue\n' ;;
        *) die "invalid colour: $1" ;;
    esac
}

web_port() {
    # 두 Web 슬롯은 임시 포트가 아니라 각각 고정된 호스트 loopback 포트를 사용합니다.
    case "$1" in
        blue) printf '8001\n' ;;
        green) printf '8002\n' ;;
        *) die "invalid colour: $1" ;;
    esac
}

load_state() {
    [[ -f "$STATE_FILE" ]] || return 1
    # state.env는 write_state만 생성하고 0600으로 보관합니다. source하기 전에 생성 단계에서
    # Bash와 Compose에 안전한 이미지·SHA·색상 문자만 허용합니다.
    # shellcheck disable=SC1090
    source "$STATE_FILE"
    case "${ACTIVE_COLOR:-}" in blue|green) ;; *) die "invalid deployment state: ACTIVE_COLOR" ;; esac
    case "${PREVIOUS_COLOR:-}" in blue|green|'') ;; *) die "invalid deployment state: PREVIOUS_COLOR" ;; esac
}

write_state() {
    local active=$1 previous=$2 blue_image=$3 blue_release=$4 green_image=$5 green_release=$6
    local value temporary default_image tool_image bridge_image
    default_image=${active_image:-skoj-app:local}
    tool_image=${SKOJ_TOOL_IMAGE:-$default_image}
    bridge_image=${SKOJ_BRIDGE_IMAGE:-$default_image}
    # source되는 파일이므로 허용 문자 밖의 값은 기록하지 않아 명령 삽입을 차단합니다.
    for value in "$active" "$previous" "$blue_image" "$blue_release" "$green_image" "$green_release" "$tool_image" "$bridge_image"; do
        [[ "$value" =~ ^[A-Za-z0-9._:/-]*$ ]] || die "unsafe deployment state value: $value"
    done
    # 부분 기록을 피하기 위해 임시 파일을 완성한 뒤 같은 디렉터리에서 원자적으로 교체합니다.
    temporary=$(mktemp "$DEPLOYMENT_DIR/state.env.XXXXXX")
    chmod 600 "$temporary"
    {
        printf '# SKOJ 배포 스크립트가 자동 생성합니다. 배포 중에는 직접 수정하지 마세요.\n'
        printf 'ACTIVE_COLOR=%s\n' "$active"
        printf 'PREVIOUS_COLOR=%s\n' "$previous"
        printf 'SKOJ_BLUE_IMAGE=%s\n' "$blue_image"
        printf 'SKOJ_BLUE_RELEASE=%s\n' "$blue_release"
        printf 'SKOJ_GREEN_IMAGE=%s\n' "$green_image"
        printf 'SKOJ_GREEN_RELEASE=%s\n' "$green_release"
        # 일반 배포가 Bridge를 재생성하지 않도록 도구와 Bridge 이미지도 별도로 고정합니다.
        printf 'SKOJ_TOOL_IMAGE=%s\n' "$tool_image"
        printf 'SKOJ_BRIDGE_IMAGE=%s\n' "$bridge_image"
    } >"$temporary"
    mv -f "$temporary" "$STATE_FILE"
}

set_colour_release() {
    local colour=$1 image=$2 release=$3
    case "$colour" in
        blue)
            SKOJ_BLUE_IMAGE=$image
            SKOJ_BLUE_RELEASE=$release
            ;;
        green)
            SKOJ_GREEN_IMAGE=$image
            SKOJ_GREEN_RELEASE=$release
            ;;
        *) die "invalid colour: $colour" ;;
    esac
}

export_compose_state() {
    # 셸 환경은 --env-file보다 우선하므로 전환 성공 전 state.env를 바꾸지 않고도
    # 후보 컨테이너에 새 이미지와 RELEASE_ID를 전달할 수 있습니다.
    export ACTIVE_COLOR PREVIOUS_COLOR
    export SKOJ_BLUE_IMAGE SKOJ_BLUE_RELEASE SKOJ_GREEN_IMAGE SKOJ_GREEN_RELEASE
    export SKOJ_TOOL_IMAGE SKOJ_BRIDGE_IMAGE
}

persist_loaded_state() {
    local active_image
    if [[ "$ACTIVE_COLOR" == blue ]]; then
        active_image=$SKOJ_BLUE_IMAGE
    else
        active_image=$SKOJ_GREEN_IMAGE
    fi
    # 성공한 활성 이미지를 init/Bridge 기본값으로 사용한 뒤 원자적 상태 저장을 호출합니다.
    export active_image
    export_compose_state
    write_state "$ACTIVE_COLOR" "${PREVIOUS_COLOR:-}" \
        "$SKOJ_BLUE_IMAGE" "$SKOJ_BLUE_RELEASE" \
        "$SKOJ_GREEN_IMAGE" "$SKOJ_GREEN_RELEASE"
}

switch_nginx() {
    local target=$1
    log "Switching Nginx to $target"
    # 비밀번호 프롬프트로 배포가 멈추지 않도록 설치된 제한 sudo 규칙만 사용합니다.
    sudo -n "$NGINX_SWITCH" "$target"
}

wait_for_web() {
    local colour=$1 release=$2 port attempt payload
    port=$(web_port "$colour")
    # 최대 30회, 2초 간격으로 DB·Redis가 포함된 health와 정확한 RELEASE_ID를 확인합니다.
    for ((attempt = 1; attempt <= HEALTH_ATTEMPTS; attempt++)); do
        if payload=$(curl --fail --silent --show-error \
            --header 'Host: skoj.site' \
            --header 'X-Forwarded-Proto: https' \
            "http://127.0.0.1:${port}/healthz/" 2>/dev/null) \
            && grep -q "\"release\": \"$release\"" <<<"$payload"; then
            log "Web $colour is ready with release $release"
            return 0
        fi
        sleep 2
    done
    return 1
}

smoke_candidate() {
    local colour=$1 port
    port=$(web_port "$colour")
    # Nginx 전환 전에 후보 슬롯의 실제 Django 로그인 경로까지 요청합니다.
    curl --fail --silent --show-error --output /dev/null \
        --header 'Host: skoj.site' \
        --header 'X-Forwarded-Proto: https' \
        "http://127.0.0.1:${port}/accounts/login/"
}

smoke_public() {
    # Nginx 전환 후 공개 도메인의 TLS와 proxy 경로를 함께 확인합니다.
    curl --fail --silent --show-error --output /dev/null "$PUBLIC_URL/healthz/"
}

wait_for_service_health() {
    local service=$1 attempt container status
    container=$(compose ps -q "$service")
    [[ -n "$container" ]] || return 1
    # healthy/running이면 성공하고 명확한 장애 상태면 재시도하지 않고 즉시 실패합니다.
    for ((attempt = 1; attempt <= HEALTH_ATTEMPTS; attempt++)); do
        status=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container")
        [[ "$status" == healthy || "$status" == running ]] && return 0
        [[ "$status" == unhealthy || "$status" == exited || "$status" == dead ]] && return 1
        sleep 2
    done
    return 1
}

stop_service_gracefully() {
    local service=$1 timeout=${2:-600}
    # 실행 중인 Celery 작업이 끝날 시간을 주고 최대 10분 뒤 종료합니다.
    compose stop --timeout "$timeout" "$service"
}

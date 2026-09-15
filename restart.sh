#!/usr/bin/env bash

# 최초 Blue/Green 도입 또는 마이그레이션·비호환 변경을 중단 배포하는 스크립트입니다.
#
# 사용 방법:
#   cd /home/songg9572/SKOJ
#   ./restart.sh
#
# 특정 SHA를 명시하는 방법:
#   ./restart.sh <git-sha>
#
# 다음 상황에서 사용합니다:
# - `deploy.sh`가 미적용 마이그레이션을 발견해 종료 코드 20으로 중단된 경우
# - Blue/Green 관리 상태를 처음 생성하는 최초 배포
# - Celery task 인자, Redis 캐시 형식, 공유 파일 형식 등 구버전과 신버전이
#   동시에 동작할 수 없는 변경이 포함된 경우
#
# 실행 전 조건:
# - `sudo ./setup-deployment.sh`로 Nginx 전환 도구가 설치되어 있어야 합니다.
# - 배포할 커밋이 현재 HEAD와 같고 작업 트리에 미커밋 변경이 없어야 합니다.
# - `.env.docker`가 존재하고 MariaDB와 Redis가 healthy 상태여야 합니다.
#
# 배포 동작:
# - Nginx를 Maintenance로 전환하고 Web·Celery를 정상 종료한 뒤 기존 채점 완료를 기다립니다.
# - 채점 완료 확인 후 Bridge를 정지해 백업·초기화 중 채점 쓰기를 막습니다.
# - MariaDB dump를 만들고 gzip 무결성과 파일 크기를 확인한 뒤 init/migrate를 실행합니다.
# - Redis DB 1의 Django 캐시만 비우고 Celery queue가 있는 DB 0은 보존합니다.
# - 새 Bridge에 Judge 2개가 재연결되고 Web·Celery readiness가 통과하면 사이트를 재개합니다.
# - DB·Redis·실행 중인 Judge는 보존하며 Bridge는 매번 새 릴리스 이미지로 교체합니다.
# - SKOJ_JUDGE_DRAIN_TIMEOUT(기본600초), SKOJ_JUDGE_READY_TIMEOUT(기본120초)으로 대기를 조절합니다.
#
# 백업과 실패 처리:
# - 기본 백업 위치는 `/home/songg9572/skoj-backups/skoj-pre-deploy-<시각>.sql.gz`입니다.
# - `SKOJ_BACKUP_DIR=/다른/경로 ./restart.sh`로 백업 위치를 바꿀 수 있습니다.
# - 백업 생성 또는 검증 실패 시 migrate를 실행하지 않습니다.
# - 배포 실패 시 Maintenance 화면을 유지하며 DB는 자동 복원하지 않습니다.
#   원인을 확인한 뒤 DEPLOYMENT.md의 수동 복원 절차를 사용해야 합니다.

# 명령 실패, 미정의 변수, 파이프 중간 실패를 즉시 배포 실패로 처리합니다.
set -Eeuo pipefail

readonly SCRIPT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=deploy/lib.sh
source "$SCRIPT_ROOT/deploy/lib.sh"

# Maintenance 전환 이후의 실패인지 구분해 서비스가 잘못 열린 채 남지 않게 합니다.
maintenance_enabled=0

report_failure() {
    local exit_code=$?
    if ((exit_code == 0)); then
        return
    fi
    log "Maintenance deployment failed"
    # 서비스 중단 이후 실패했다면 Nginx를 반드시 Maintenance로 되돌립니다.
    if ((maintenance_enabled == 1)); then
        switch_nginx maintenance >/dev/null 2>&1 \
            || log "ERROR: failed to restore Nginx maintenance mode"
        log "Nginx remains in maintenance mode. Inspect the error before manual recovery."
    fi
    exit "$exit_code"
}
# 어느 단계에서든 실패하면 위 정책을 적용합니다. DB 자동 복원은 수행하지 않습니다.
trap report_failure EXIT

stop_legacy_application() {
    local service container
    # 최초 도입 때 기존 web/celery 서비스는 새 Compose 모델에 이름이 없으므로
    # Compose 프로젝트와 서비스 label로 정확한 컨테이너만 찾아 정상 종료합니다.
    for service in web celery; do
        while read -r container; do
            [[ -n "$container" ]] && docker stop --time 600 "$container"
        done < <(docker ps -q \
            --filter 'label=com.docker.compose.project=skoj' \
            --filter "label=com.docker.compose.service=$service")
    done
}

backup_database() {
    local backup_dir=${SKOJ_BACKUP_DIR:-/home/songg9572/skoj-backups}
    local timestamp temporary backup
    timestamp=$(date -u '+%Y%m%dT%H%M%SZ')
    backup="$backup_dir/skoj-pre-deploy-$timestamp.sql.gz"
    temporary="$backup.tmp"
    # 백업 디렉터리와 파일은 배포 계정만 접근할 수 있도록 제한합니다.
    mkdir -p "$backup_dir"
    chmod 700 "$backup_dir"
    umask 077

    log "Creating database backup $backup"
    # InnoDB 쓰기를 장시간 막지 않도록 single-transaction 방식으로 dump합니다.
    if ! compose exec -T db sh -c \
        'exec mariadb-dump --single-transaction --quick --routines --triggers --events -uroot -p"$MARIADB_ROOT_PASSWORD" "$MARIADB_DATABASE"' \
        | gzip -c >"$temporary"; then
        rm -f "$temporary"
        die "database dump failed"
    fi
    # 압축 스트림이 손상됐거나 빈 백업이면 migration 전에 배포를 중단합니다.
    if ! gzip -t "$temporary"; then
        rm -f "$temporary"
        die "database backup gzip validation failed"
    fi
    if [[ ! -s "$temporary" ]]; then
        rm -f "$temporary"
        die "database backup is empty"
    fi
    # 모든 검증을 통과한 임시 파일만 최종 백업 이름으로 원자적으로 옮깁니다.
    mv -f "$temporary" "$backup"
    chmod 600 "$backup"
    DATABASE_BACKUP=$backup
    export DATABASE_BACKUP
}

initialize_state_for_first_deploy() {
    local image=$1 release=$2
    # 최초 관리 상태는 Blue를 활성 슬롯으로 삼고 두 색상에 같은 기준 이미지를 기록합니다.
    ACTIVE_COLOR=blue
    PREVIOUS_COLOR=''
    SKOJ_BLUE_IMAGE=$image
    SKOJ_BLUE_RELEASE=$release
    SKOJ_GREEN_IMAGE=$image
    SKOJ_GREEN_RELEASE=$release
    SKOJ_TOOL_IMAGE=$image
    SKOJ_BRIDGE_IMAGE=$image
    export_compose_state
}

main() {
    # 인자를 생략하면 현재 HEAD를 사용하며, 특정 SHA는 하나만 명시할 수 있습니다.
    [[ $# -le 1 ]] || die "usage: ./restart.sh [git-sha]"
    prepare_runtime
    require_command gzip
    platform_preflight
    local requested release image target_colour bridge_started_after had_state=1
    local drain_timeout=${SKOJ_JUDGE_DRAIN_TIMEOUT:-600} ready_timeout=${SKOJ_JUDGE_READY_TIMEOUT:-120}
    [[ "$drain_timeout" =~ ^[0-9]+$ && "$ready_timeout" =~ ^[0-9]+$ ]] \
        || die "judge wait timeouts must be nonnegative integer seconds"
    requested=${1:-$(git -C "$SCRIPT_ROOT" rev-parse HEAD)}
    release=$(validate_release "$requested")
    image=$(build_release_image "$release")

    # state.env가 없으면 기존 단일 구조에서 Blue/Green으로 처음 전환하는 경우입니다.
    if ! load_state; then
        had_state=0
        initialize_state_for_first_deploy "$image" "$release"
    fi

    # 이후 중단 배포도 활성 슬롯의 반대편에 새 릴리스를 준비합니다.
    if ((had_state == 1)); then
        target_colour=$(other_colour "$ACTIVE_COLOR")
    else
        target_colour=blue
    fi
    set_colour_release "$target_colour" "$image" "$release"
    export_compose_state

    # DB 백업과 migration 전에 먼저 사용자 요청을 Maintenance 페이지로 전환합니다.
    switch_nginx maintenance
    maintenance_enabled=1

    # Web의 진행 중 요청을 마친 다음 Celery의 작업도 마쳐 새 제출 유입을 차단합니다.
    compose stop --timeout 600 web-blue web-green
    compose stop --timeout 600 celery-blue celery-green
    if ((had_state == 0)); then
        stop_legacy_application
    fi

    # 새 이미지의 읽기 전용 명령으로 대기열까지 확인합니다. 타임아웃 시 Bridge는 유지합니다.
    SKOJ_TOOL_IMAGE=$image
    export_compose_state
    compose run --rm --no-deps init python manage.py wait_for_judge_state drained --timeout "$drain_timeout" \
        || die "unfinished submissions remain; Bridge was not restarted"
    compose stop --timeout 60 bridge

    # 검증된 백업 없이는 아래 init/migrate 단계로 진행하지 않습니다.
    backup_database

    # initialize_docker는 migration을 포함하며 여러 번 실행해도 안전한 초기화를 담당합니다.
    log "Applying migrations and idempotent Docker initialization"
    SKOJ_TOOL_IMAGE=$image
    export_compose_state
    compose run --rm init

    SKOJ_BRIDGE_IMAGE=$image
    export_compose_state
    bridge_started_after=$(date +%s)
    compose up -d --no-deps --force-recreate bridge
    if ((had_state == 0)); then
        compose up -d --no-deps judge judge-02
    fi
    # 이전 online 값만으로 통과하지 않도록 이번 교체 이후 연결 시각까지 검증합니다.
    compose run --rm --no-deps init python manage.py wait_for_judge_state ready \
        --since "$bridge_started_after" --timeout "$ready_timeout" \
        || die "judges did not reconnect to the new Bridge"

    # 캐시 DB 1에는 이전 릴리스의 Python 직렬화 객체가 남을 수 있어 비웁니다.
    # Celery queue가 있는 Redis DB 0은 작업 유실 방지를 위해 절대 비우지 않습니다.
    compose exec -T redis redis-cli -n 1 FLUSHDB >/dev/null

    # 새 Web과 Celery를 함께 시작하고 Nginx 전환 전에 모두 검증합니다.
    compose up -d --no-deps "web-$target_colour" "celery-$target_colour"
    wait_for_web "$target_colour" "$release" || die "new Web failed readiness check"
    smoke_candidate "$target_colour" || die "new Web smoke test failed"
    wait_for_service_health "celery-$target_colour" || die "new Celery failed readiness check"

    # 내부 검증이 끝난 뒤 새 색상으로 공개 트래픽을 열고 외부 HTTPS도 확인합니다.
    switch_nginx "$target_colour"
    smoke_public || die "public HTTPS smoke test failed after maintenance deployment"

    # DB 스키마가 달라졌을 수 있으므로 이전 색상을 즉시 롤백 대상으로 기록하지 않습니다.
    PREVIOUS_COLOR=''
    ACTIVE_COLOR=$target_colour
    persist_loaded_state
    maintenance_enabled=0
    log "Maintenance deployment complete: active colour is $ACTIVE_COLOR ($release)"
    log "Pre-deployment database backup: $DATABASE_BACKUP"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi

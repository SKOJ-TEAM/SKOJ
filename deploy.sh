#!/usr/bin/env bash

# 마이그레이션이 없는 릴리스를 무중단 Blue/Green 방식으로 배포하는 스크립트입니다.
#
# 사용 방법:
#   cd /home/songg9572/SKOJ
#   ./deploy.sh
#
# 특정 SHA를 명시하는 방법:
#   ./deploy.sh <git-sha>
#
# 직전 무중단 배포로 롤백하는 방법:
#   ./deploy.sh rollback
#
# 실행 전 조건:
# - 최초 1회 `sudo ./setup-deployment.sh`와 `./restart.sh`가 완료되어야 합니다.
# - 배포할 커밋이 현재 HEAD와 같고 작업 트리에 미커밋 변경이 없어야 합니다.
# - `.env.docker`가 존재하고 MariaDB와 Redis가 healthy 상태여야 합니다.
# - 저장소가 있는 디스크에 기본 4 GiB 이상의 여유 공간이 있어야 합니다.
#
# 배포 동작:
# - 현재 비활성 색상(Blue 8001 또는 Green 8002)에 새 이미지의 Web을 올립니다.
# - Web readiness와 smoke test 성공 후 Nginx를 새 색상으로 원자적으로 전환합니다.
# - 새 Celery가 준비되면 기존 Celery를 정상 종료합니다.
# - 기존 Web은 즉시 롤백할 수 있도록 다음 배포 전까지 실행 상태로 둡니다.
#
# 주의 사항:
# - 미적용 Django 마이그레이션이 있으면 아무 스키마도 변경하지 않고 종료 코드 20으로
#   거부합니다. 이 경우 `./restart.sh`를 사용합니다.
# - 전환 후 검사가 실패하면 Nginx와 Celery를 기존 색상으로 자동 복구합니다.
# - 이 스크립트는 데이터베이스 스키마와 데이터를 변경하지 않습니다.
# - rollback은 DB를 되돌리지 않으므로 마이그레이션을 적용한 배포 복구에는 사용하지 않습니다.

# 명령 실패, 미정의 변수, 파이프 중간 실패를 즉시 배포 실패로 처리합니다.
set -Eeuo pipefail

readonly SCRIPT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=deploy/lib.sh
source "$SCRIPT_ROOT/deploy/lib.sh"

# Nginx 전환 여부를 기록해 EXIT 트랩이 자동 롤백 범위를 판단합니다.
traffic_switched=0
target_colour=''
original_colour=''

cleanup_failed_deploy() {
    local exit_code=$?
    # 정상 종료라면 복구 작업 없이 끝냅니다.
    if ((exit_code == 0)); then
        return
    fi
    log "Zero-downtime deployment failed"
    # 트래픽까지 전환한 뒤 실패했다면 기존 Celery와 Nginx 경로를 먼저 복구합니다.
    if ((traffic_switched == 1)) && [[ -n "$original_colour" ]]; then
        compose up -d --no-deps "celery-$original_colour" >/dev/null 2>&1 \
            || log "ERROR: previous Celery could not be restarted"
        switch_nginx "$original_colour" || log "ERROR: automatic Nginx rollback failed"
    fi
    # 실패한 후보 컨테이너는 다음 배포에 영향을 주지 않도록 중지합니다.
    if [[ -n "$target_colour" ]]; then
        compose stop "web-$target_colour" "celery-$target_colour" >/dev/null 2>&1 || true
    fi
    exit "$exit_code"
}
# 함수 내부를 포함한 어느 단계에서 실패해도 위 복구 함수를 실행합니다.
trap cleanup_failed_deploy EXIT

rollback_release() {
    # 최초 중단 배포로 생성된 상태와 직전 색상이 모두 있어야 롤백할 수 있습니다.
    load_state || die "no deployment state; run restart.sh for the first managed deployment"
    [[ -n "$PREVIOUS_COLOR" ]] || die "no previous colour is recorded"
    local current=$ACTIVE_COLOR previous=$PREVIOUS_COLOR previous_release
    original_colour=$current
    target_colour=$previous
    # 직전 색상에 저장된 이미지의 RELEASE_ID를 readiness 검증 기준으로 사용합니다.
    if [[ "$previous" == blue ]]; then
        previous_release=$SKOJ_BLUE_RELEASE
    else
        previous_release=$SKOJ_GREEN_RELEASE
    fi

    # 이전 Web과 Celery를 먼저 준비하고 둘 다 정상일 때만 트래픽을 되돌립니다.
    log "Starting previous Celery and Web colour $previous"
    compose up -d --no-deps "web-$previous" "celery-$previous"
    wait_for_web "$previous" "$previous_release" || die "previous Web failed readiness check"
    wait_for_service_health "celery-$previous" || die "previous Celery failed readiness check"
    switch_nginx "$previous"
    traffic_switched=1
    # 새로 활성화된 이전 Celery가 준비된 뒤 현재 Celery를 warm shutdown합니다.
    stop_service_gracefully "celery-$current"

    # 롤백한 방향도 다시 되돌릴 수 있도록 현재·직전 색상을 서로 교환해 저장합니다.
    PREVIOUS_COLOR=$current
    ACTIVE_COLOR=$previous
    persist_loaded_state
    traffic_switched=0
    log "Rollback complete: active colour is $ACTIVE_COLOR ($previous_release)"
}

main() {
    # 인자를 생략하면 현재 HEAD를 사용하며, 특정 SHA 또는 rollback 하나만 추가로 허용합니다.
    [[ $# -le 1 ]] || die "usage: ./deploy.sh [git-sha]|rollback"
    # 필수 명령, 환경 파일, Nginx helper, 중복 배포 잠금을 확인합니다.
    prepare_runtime

    local requested
    requested=${1:-$(git -C "$SCRIPT_ROOT" rev-parse HEAD)}
    if [[ "$requested" == rollback ]]; then
        rollback_release
        return
    fi

    # 일반 배포는 최초 restart.sh가 만든 관리 상태를 기반으로만 실행합니다.
    load_state || die "no managed deployment state; run ./restart.sh $requested for the first deployment"
    platform_preflight
    local release image migration_plan
    release=$(validate_release "$requested")
    image=$(build_release_image "$release")
    # 현재 활성 색상의 반대편을 이번 후보 배포 슬롯으로 선택합니다.
    original_colour=$ACTIVE_COLOR
    target_colour=$(other_colour "$ACTIVE_COLOR")

    # 성공 전에는 state.env를 쓰지 않고 현재 프로세스 환경에만 후보 정보를 설정합니다.
    set_colour_release "$target_colour" "$image" "$release"
    export_compose_state

    # 모델 변경에 대응하는 migration 파일 자체가 빠진 경우 배포를 즉시 거부합니다.
    log "Checking for model changes without migration files"
    compose run --rm --no-deps "web-$target_colour" python manage.py makemigrations --check --dry-run

    # 운영 DB에 미적용 migration이 있으면 Web/Nginx/DB를 바꾸기 전에 종료 코드 20으로 끝냅니다.
    log "Checking the live database for pending migrations"
    migration_plan=$(compose run --rm --no-deps "web-$target_colour" python manage.py showmigrations --plan)
    if grep -Eq '^\[ \]' <<<"$migration_plan"; then
        printf '%s\n' "$migration_plan" >&2
        printf 'Blue/Green deployment rejected: pending database migrations detected.\n' >&2
        printf 'Run: ./restart.sh\n' >&2
        exit 20
    fi

    # 롤백 시에도 기존 자산이 남도록 RELEASE_ID별 정적 파일 경로에 결과를 생성합니다.
    log "Collecting release-specific static files"
    compose run --rm --no-deps "web-$target_colour" \
        python manage.py compilejsi18n --verbosity 0
    compose run --rm --no-deps "web-$target_colour" \
        python manage.py collectstatic --noinput --verbosity 0

    # 비활성 Web을 먼저 띄워 DB·Redis·릴리스 ID와 로그인 경로를 검증합니다.
    compose up -d --no-deps "web-$target_colour"
    wait_for_web "$target_colour" "$release" || die "candidate Web failed readiness check"
    smoke_candidate "$target_colour" || die "candidate Web smoke test failed"

    # 후보 검증이 끝난 뒤에만 Nginx 트래픽을 원자적으로 새 색상으로 전환합니다.
    switch_nginx "$target_colour"
    traffic_switched=1
    # 루프백 검증과 별개로 실제 공개 HTTPS 경로가 정상인지 다시 확인합니다.
    smoke_public || die "public HTTPS smoke test failed"

    # Web 전환 후 새 Celery를 검증하고 기존 Celery만 정상 종료합니다.
    # 기존 Web은 빠른 롤백을 위해 실행 상태로 유지합니다.
    compose up -d --no-deps "celery-$target_colour"
    wait_for_service_health "celery-$target_colour" || die "candidate Celery failed readiness check"
    stop_service_gracefully "celery-$original_colour"

    # 모든 검사가 끝난 마지막 단계에서만 활성·직전 색상을 영구 상태로 기록합니다.
    PREVIOUS_COLOR=$original_colour
    ACTIVE_COLOR=$target_colour
    persist_loaded_state
    traffic_switched=0
    log "Deployment complete: active colour is $ACTIVE_COLOR ($release)"
}

main "$@"

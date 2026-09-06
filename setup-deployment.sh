#!/usr/bin/env bash

# Blue/Green 배포에 필요한 Nginx 설정과 제한된 전환 명령을 설치하는 스크립트입니다.
#
# 최초 설치 방법:
#   cd /home/songg9572/SKOJ
#   sudo ./setup-deployment.sh
#
# sudo로 실행한 사용자가 실제 배포 계정과 다를 때:
#   sudo DEPLOY_USER=<배포계정> ./setup-deployment.sh
#
# 다시 실행해야 하는 경우:
# - 저장소의 `deploy/nginx/` 템플릿 또는 `deploy/skoj-nginx-switch`가 변경된 경우
# - 일반 애플리케이션 배포에서는 다시 실행할 필요가 없습니다.
#
# 설치 동작:
# - 기존 SKOJ Nginx 설정을 `/etc/nginx/skoj-backup-<UTC 시각>/`에 백업합니다.
# - Blue(8001), Green(8002), Legacy(8000), Maintenance route를 설치합니다.
# - `/usr/local/sbin/skoj-nginx-switch`와 배포 계정 전용 sudoers 규칙을 설치합니다.
# - `nginx -t`가 성공한 경우에만 Nginx를 reload합니다.
# - 최초 설치 직후에는 Legacy(8000)를 유지하고, 재설치 때는 현재 route를 유지합니다.
#
# 실패 처리:
# - root 권한 없이 실행하면 종료 코드 77로 중단합니다.
# - 설치나 Nginx 검사에 실패하면 백업한 설정을 자동 복원합니다.

# 설치 중 한 단계라도 실패하면 ERR 트랩으로 기존 설정 복원을 시도합니다.
set -Eeuo pipefail

# 설치 원본과 root 소유 대상 경로를 고정해 임의 위치에 쓰지 않도록 합니다.
readonly SCRIPT_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
readonly NGINX_SOURCE="$SCRIPT_ROOT/deploy/nginx"
readonly NGINX_TARGET=/etc/nginx/skoj
readonly VHOST_TARGET=/etc/nginx/conf.d/nginx.conf
readonly SWITCH_TARGET=/usr/local/sbin/skoj-nginx-switch
readonly SUDOERS_TARGET=/etc/sudoers.d/skoj-nginx-switch

# Nginx와 sudoers를 변경하므로 root 실행만 허용합니다.
[[ ${EUID:-$(id -u)} -eq 0 ]] || { printf 'run with sudo: sudo ./setup-deployment.sh\n' >&2; exit 77; }
# sudo를 호출한 일반 계정을 이후 배포 명령의 소유자로 선택합니다.
deploy_user=${DEPLOY_USER:-${SUDO_USER:-}}
[[ -n "$deploy_user" && "$deploy_user" != root ]] || { printf 'DEPLOY_USER or SUDO_USER must name the non-root deploy user\n' >&2; exit 64; }
id "$deploy_user" >/dev/null 2>&1 || { printf 'unknown deploy user: %s\n' "$deploy_user" >&2; exit 67; }

# 재설치 때는 현재 선택된 route를 보존합니다. active.conf가 없는 최초 설치는
# 기존 서비스가 중단되지 않도록 포트 8000의 Legacy route에서 시작합니다.
active_route=legacy
if [[ -L "$NGINX_TARGET/active.conf" ]]; then
    active_name=$(basename "$(readlink "$NGINX_TARGET/active.conf")" .conf)
    case "$active_name" in
        blue|green|maintenance|legacy) active_route=$active_name ;;
    esac
fi

# 기존 vhost, route, helper, sudoers를 한 디렉터리에 묶어 복원 가능하게 백업합니다.
timestamp=$(date -u '+%Y%m%dT%H%M%SZ')
backup_dir="/etc/nginx/skoj-backup-$timestamp"
mkdir -p "$backup_dir"
if [[ -f "$VHOST_TARGET" ]]; then
    cp -a "$VHOST_TARGET" "$backup_dir/nginx.conf"
fi
if [[ -d "$NGINX_TARGET" ]]; then
    cp -a "$NGINX_TARGET" "$backup_dir/skoj"
fi
if [[ -f "$SWITCH_TARGET" ]]; then
    cp -a "$SWITCH_TARGET" "$backup_dir/skoj-nginx-switch"
fi
if [[ -f "$SUDOERS_TARGET" ]]; then
    cp -a "$SUDOERS_TARGET" "$backup_dir/sudoers"
fi

restore_previous() {
    # 설치 실패 시 존재했던 파일은 복사해 되돌리고 새로 생긴 파일은 제거합니다.
    if [[ -f "$backup_dir/nginx.conf" ]]; then
        cp -a "$backup_dir/nginx.conf" "$VHOST_TARGET"
    else
        rm -f "$VHOST_TARGET"
    fi
    if [[ -d "$backup_dir/skoj" ]]; then
        if [[ -e "$NGINX_TARGET" ]]; then
            mv "$NGINX_TARGET" "$backup_dir/failed-skoj"
        fi
        cp -a "$backup_dir/skoj" "$NGINX_TARGET"
    elif [[ -e "$NGINX_TARGET" ]]; then
        mv "$NGINX_TARGET" "$backup_dir/failed-skoj"
    fi
    if [[ -f "$backup_dir/skoj-nginx-switch" ]]; then
        cp -a "$backup_dir/skoj-nginx-switch" "$SWITCH_TARGET"
    else
        rm -f "$SWITCH_TARGET"
    fi
    if [[ -f "$backup_dir/sudoers" ]]; then
        cp -a "$backup_dir/sudoers" "$SUDOERS_TARGET"
    else
        rm -f "$SUDOERS_TARGET"
    fi
    # 복원된 설정도 유효한 경우에만 Nginx에 다시 반영합니다.
    if nginx -t >/dev/null 2>&1; then
        systemctl reload nginx >/dev/null 2>&1 || true
    fi
}
# 아래 설치 명령 중 하나라도 실패하면 기존 설정을 복원합니다.
trap 'restore_previous' ERR

# Nginx 본문, Maintenance 페이지, 네 가지 고정 route와 전환 helper를 root 소유로 설치합니다.
install -d -m 0755 "$NGINX_TARGET" "$NGINX_TARGET/routes"
install -m 0644 "$NGINX_SOURCE/skoj.conf" "$VHOST_TARGET"
install -m 0644 "$NGINX_SOURCE/maintenance.html" "$NGINX_TARGET/maintenance.html"
for route in blue green legacy maintenance; do
    install -m 0644 "$NGINX_SOURCE/routes/$route.conf" "$NGINX_TARGET/routes/$route.conf"
done
install -m 0755 "$SCRIPT_ROOT/deploy/skoj-nginx-switch" "$SWITCH_TARGET"

# 최초 설치는 8000을 유지하고 이후 템플릿 갱신은 현재 활성 색상을 유지합니다.
ln -sfn "$NGINX_TARGET/routes/$active_route.conf" "$NGINX_TARGET/active.conf"

# 배포 계정에는 임의 root 명령이 아니라 고정된 전환 helper 실행 권한만 부여합니다.
sudoers_tmp=$(mktemp /etc/sudoers.d/skoj-nginx-switch.XXXXXX)
printf '%s ALL=(root) NOPASSWD: %s *\n' "$deploy_user" "$SWITCH_TARGET" >"$sudoers_tmp"
chmod 0440 "$sudoers_tmp"
# 잘못된 sudoers가 설치되지 않도록 visudo 검증을 통과한 파일만 최종 경로로 옮깁니다.
visudo -cf "$sudoers_tmp" >/dev/null
mv -f "$sudoers_tmp" "$SUDOERS_TARGET"

# 모든 파일 설치 후 Nginx 전체 설정을 검증하고 무중단 reload합니다.
nginx -t
systemctl reload nginx
# 성공했으므로 ERR 복원 트랩을 해제하고 백업 위치를 출력합니다.
trap - ERR
printf 'SKOJ Nginx automation installed. Backup: %s\n' "$backup_dir"

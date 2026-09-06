#!/bin/sh

# Django 이미지의 Web, Celery, init 컨테이너가 시작될 때 자동 실행하는 entrypoint입니다.
#
# 사용 방법:
# - 운영자가 직접 실행하지 않습니다. Dockerfile의 ENTRYPOINT를 통해 자동 호출됩니다.
# - 컨테이너에 전달된 실제 명령은 준비 작업이 끝난 뒤 `exec "$@"`로 실행됩니다.
#
# 담당 역할:
# - RELEASE_ID별 정적 파일 디렉터리를 만들어 Blue/Green과 롤백 시 정적 파일이
#   서로 덮어쓰이지 않도록 합니다.
# - 문제 데이터가 저장될 `/problems` 디렉터리가 존재하도록 보장합니다.

set -eu

# 이전 Web 색상이 롤백 중에도 자신의 릴리스와 일치하는 정적 파일을 제공하도록
# 정적 파일 경로를 RELEASE_ID 단위로 분리합니다.
mkdir -p "/app/site/tmp/static/releases/${RELEASE_ID:-development}" /problems

exec "$@"

#!/bin/sh

set -eu

mkdir -p /app/site/tmp/static /problems

exec "$@"

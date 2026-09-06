#!/bin/bash

# 로컬 tmux 세션에서 Judge 1~3을 시작하는 운영 보조 스크립트입니다.
#
# 사용 방법:
#   cd /home/songg9572/SKOJ
#   ./site/judge/start_judges_1_3.sh
#
# 실행 전 `tmux`, DMOJ 실행 파일, `site/judge/configs/skoj-judge*.yml`이 필요합니다.
# DMOJ 위치가 기본값과 다르면 `DMOJ_BIN=/경로/dmoj` 환경 변수로 지정합니다.
# 같은 범위의 기존 tmux 세션은 종료하고 새 세션으로 교체합니다.
# 실행 후 확인: `tmux attach -t dmoj_judge_1_3`

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)"
DMOJ_BIN="${DMOJ_BIN:-$PROJECT_ROOT/.local/bin/dmoj}"

if [ ! -x "$DMOJ_BIN" ]; then
  echo "DMOJ 실행 파일을 찾을 수 없습니다: $DMOJ_BIN" >&2
  exit 1
fi

# 기존 tmux 세션 종료
tmux kill-session -t dmoj_judge 2>/dev/null || true
tmux kill-session -t dmoj_judge_multi 2>/dev/null || true
tmux kill-session -t dmoj_judge_1_3 2>/dev/null || true

# 새로운 tmux 세션 생성
tmux new-session -d -s dmoj_judge_1_3

# 채점기 1~3 실행
for i in {1..3}; do
  if [ $i -eq 1 ]; then
    judge_name="skoj-judge"
  else
    judge_name="skoj-judge-$i"
  fi

  if [ $i -gt 1 ]; then
    tmux new-window -t dmoj_judge_1_3
  fi

  tmux rename-window -t dmoj_judge_1_3 "$judge_name"

  echo "Starting judge ($judge_name)..."
  tmux send-keys -t dmoj_judge_1_3 "cd \"$SCRIPT_DIR\" && \"$DMOJ_BIN\" -c configs/$judge_name.yml localhost $judge_name" C-m
done

echo "채점기 1-3이 모두 시작되었습니다."
echo "채점기 1-3 세션: tmux attach -t dmoj_judge_1_3"
echo "상태 확인: https://skoj.site/status/"

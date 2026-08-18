#!/bin/bash

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
echo "상태 확인: https://litmus.jbnu.ac.kr/status/"

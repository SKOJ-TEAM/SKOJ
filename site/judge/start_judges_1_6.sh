#!/bin/bash

# `/home/ubuntu` 환경의 tmux 세션에서 Judge 1~6을 시작하는 보조 스크립트입니다.
#
# 사용 방법:
#   ./site/judge/start_judges_1_6.sh
#
# 실행 전 `tmux`, `/home/ubuntu/.local/bin/dmoj`, `/home/ubuntu/site/judge/configs/`
# 아래의 Judge 설정 파일이 필요합니다. 같은 범위의 기존 tmux 세션은 종료됩니다.
# 실행 후 확인: `tmux attach -t dmoj_judge_1_6`
# 현재 SKOJ 운영 경로가 `/home/songg9572/SKOJ`라면 경로 독립적인
# `start_judges_1_3.sh` 또는 Compose Judge 구성을 우선 사용합니다.

# 기존 tmux 세션 종료
tmux kill-session -t dmoj_judge 2>/dev/null || true
tmux kill-session -t dmoj_judge_multi 2>/dev/null || true
tmux kill-session -t dmoj_judge_1_6 2>/dev/null || true

# 새로운 tmux 세션 생성
tmux new-session -d -s dmoj_judge_1_6

# 채점기 1~6 실행
for i in {1..6}; do
  if [ $i -eq 1 ]; then
    judge_name="skoj-judge"
  else
    judge_name="skoj-judge-$i"
  fi

  if [ $i -gt 1 ]; then
    tmux new-window -t dmoj_judge_1_6
  fi

  tmux rename-window -t dmoj_judge_1_6 "$judge_name"

  echo "Starting judge ($judge_name)..."
  tmux send-keys -t dmoj_judge_1_6 "cd /home/ubuntu/site/judge && /home/ubuntu/.local/bin/dmoj -c configs/$judge_name.yml localhost $judge_name" C-m
done

echo "채점기 1-6이 모두 시작되었습니다."
echo "채점기 1-6 세션: tmux attach -t dmoj_judge_1_6"
echo "상태 확인: https://skoj.site/status/"

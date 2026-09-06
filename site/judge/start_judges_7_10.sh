#!/bin/bash

# `/home/ubuntu` 환경의 tmux 세션에서 Judge 7~10을 시작하는 보조 스크립트입니다.
#
# 사용 방법:
#   ./site/judge/start_judges_7_10.sh
#
# 실행 전 `tmux`, `/home/ubuntu/.local/bin/dmoj`, `/home/ubuntu/site/judge/configs/`
# 아래의 `skoj-judge-7.yml`~`skoj-judge-10.yml`이 필요합니다.
# 같은 이름의 기존 tmux 세션은 종료하고 새 세션으로 교체합니다.
# 실행 후 확인: `tmux attach -t dmoj_judge_7_10`

# 기존 tmux 세션 종료
tmux kill-session -t dmoj_judge_7_10 2>/dev/null || true

# 새로운 tmux 세션 생성
tmux new-session -d -s dmoj_judge_7_10

# 채점기(7-10)를 위한 창 분할 및 실행
for i in {7..10}; do
  judge_name="skoj-judge-$i"

  # 첫 번째 창 이후로는 새 창 생성
  if [ $i -gt 7 ]; then
    tmux new-window -t dmoj_judge_7_10
  fi

  # 창 이름 설정
  tmux rename-window -t dmoj_judge_7_10 "$judge_name"

  echo "Starting judge ($judge_name)..."
  tmux send-keys -t dmoj_judge_7_10 "cd /home/ubuntu/site/judge && /home/ubuntu/.local/bin/dmoj -c configs/$judge_name.yml localhost $judge_name" C-m
done

echo "채점기 7-10이 모두 시작되었습니다."
echo "채점기 7-10 세션: tmux attach -t dmoj_judge_7_10"
echo "상태 확인: https://skoj.site/status/"

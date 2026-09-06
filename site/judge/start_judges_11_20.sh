#!/bin/bash

# `/home/ubuntu` 환경의 tmux 세션에서 Judge 11~20을 시작하는 보조 스크립트입니다.
#
# 사용 방법:
#   ./site/judge/start_judges_11_20.sh
#
# 실행 전 `tmux`, `/home/ubuntu/.local/bin/dmoj`, `/home/ubuntu/site/judge/configs/`
# 아래의 `skoj-judge-11.yml`~`skoj-judge-20.yml`이 필요합니다.
# 같은 이름의 기존 tmux 세션은 종료하고 새 세션으로 교체합니다.
# 실행 후 확인: `tmux attach -t dmoj_judge_11_20`

# 기존 tmux 세션 종료
tmux kill-session -t dmoj_judge_11_20 2>/dev/null || true

# 새로운 tmux 세션 생성
tmux new-session -d -s dmoj_judge_11_20

# 각 추가 채점기(11-20)를 위한 창 분할 및 실행
for i in {11..20}; do
  judge_name="skoj-judge-$i"
  
  # 첫 번째 창 이후로는 새 창 생성
  if [ $i -gt 11 ]; then
    tmux new-window -t dmoj_judge_11_20
  fi
  
  # 창 이름 설정
  tmux rename-window -t dmoj_judge_11_20 "$judge_name"
  
  # 채점기 실행 명령어 - 수정된 경로 사용
  echo "Starting new judge ($judge_name)..."
  tmux send-keys -t dmoj_judge_11_20 "cd /home/ubuntu/site/judge && /home/ubuntu/.local/bin/dmoj -c configs/$judge_name.yml localhost $judge_name" C-m
done

echo "채점기 11-20이 모두 시작되었습니다."
echo "채점기 11-20 세션: tmux attach -t dmoj_judge_11_20"
echo "상태 확인: https://skoj.site/status/"

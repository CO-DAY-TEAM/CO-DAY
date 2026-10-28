#!/usr/bin/env bash
# 최초 설치·인증 설정은 README에서 한 번 준비
# 실행: bash evals/reviewbench/run.sh --set test --pr 0
# 평가 범위(--set test|full 또는 --pr <인덱스>)를 지정하고 공식 스크립트로 전달
set -e

if [[ $# -lt 2 || ( "$1" != "--set" && "$1" != "--pr" ) ]]; then
  printf '사용법: bash evals/reviewbench/run.sh --set test|full 또는 --pr <인덱스>\n' >&2
  exit 2
fi

# 1. 스크립트 위치를 기준으로 경로 설정. .cache/work는 재사용하고 결과 폴더는 매번 생성
eval_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$eval_dir/../.."

reviewbench="$eval_dir/.cache/ReviewBench"
work="$eval_dir/.cache/work"

run="$eval_dir/runs/$(date +%Y%m%d-%H%M%S)"
image="coday-reviewbench:$(basename "$run")"

# 2. 리뷰용 키·모델과 심사 인증 방식은 .env, 심사 모델은 models.json에서 설정
# set -a로 .env의 값을 이후 명령에 환경변수로 전달
set -a
. "$eval_dir/.env"
set +a

export PI_CODING_AGENT_DIR="$eval_dir/.cache/pi"
mkdir -p "$PI_CODING_AGENT_DIR" "$run/scoring"
cp "$eval_dir/models.json" "$PI_CODING_AGENT_DIR/models.json"
judge_provider=${JUDGE_PROVIDER:-openai-codex}
judge_model=$(jq -r --arg provider "$judge_provider" '.providers[$provider].models[0].id' "$eval_dir/models.json")

# 3. 현재 CO-DAY 코드와 프롬프트로 공식 실행 플랫폼인 linux/amd64 이미지 빌드
docker build \
  --platform linux/amd64 \
  -f "$eval_dir/Dockerfile" \
  -t "$image" \
  .

# 공식 점수 파일에 없는 코드 버전·리뷰 모델·이미지 정보 보관
# jq의 $ARGS.named로 --arg의 이름과 값을 JSON 필드로 생성
jq -n \
  --arg coday_revision "$(git rev-parse HEAD)" \
  --arg reviewbench_revision "$(git -C "$reviewbench" rev-parse HEAD)" \
  --arg review_model "$RB_CONFIG_MODEL" \
  --arg image_tag "$image" \
  '$ARGS.named' > "$run/run.json"

# 4. 공식 스크립트로 PR별 컨테이너 실행 및 findings 형식 검증
# 실패하면 set -e로 중단하여 채점 생략
(
  cd "$run" &&
  TRY_AGENT_WORK="$work" bash "$reviewbench/scripts/try-agent.sh" \
    "$image" "$@" \
    -e OPENAI_API_KEY \
    -e RB_CONFIG_MODEL \
    -e RB_AGENT=coday
)

# 5. CO-DAY 원본 리뷰를 실행 결과의 raw-reviews/에 PR별 JSON 파일로 보관
# 같은 PR을 다시 평가해도 이전 실행의 원본 리뷰는 runs/에 유지
mkdir -p "$run/raw-reviews"

for finding in "$run"/findings/*.json; do
  key=$(basename "$finding" .json)
  cp "$work/out/$key/raw-review.json" "$run/raw-reviews/$key.json"
done

# 6. 공식 채점기로 매칭·분류·점수 계산
# 지적이 0개인 정상 리뷰도 집계하도록 공식 --allow-empty 옵션 사용
(
  cd "$reviewbench" &&
  npm run judge -- \
    --candidate "$run/findings" \
    --provider "$judge_provider" \
    --model "$judge_model" \
    --allow-empty \
    --output "$run/scoring/results.json" \
    --repo-dir "$eval_dir/.cache/judge-repos"
)

printf '평가 결과: %s\n' "$run"

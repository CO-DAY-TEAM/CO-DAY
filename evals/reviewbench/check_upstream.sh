#!/usr/bin/env bash
# ReviewBench 공식 main에 기준 커밋 이후 새 커밋이 있는지 확인하고 업데이트 PR 본문 작성
# 실행: bash evals/reviewbench/check_upstream.sh <PR 본문 저장 경로>
# 새 커밋이 없으면 본문 파일을 만들지 않고 종료
set -euo pipefail

if [[ $# -ne 1 ]]; then
  printf '사용법: bash evals/reviewbench/check_upstream.sh <PR 본문 저장 경로>\n' >&2
  exit 2
fi

body="$1"
eval_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_url="https://github.com/review-bench/ReviewBench"
current=$(< "$eval_dir/REVIEWBENCH_COMMIT")

# 1. 파일 내용 없이 커밋 기록만 받아 공식 main 최신 커밋 확인
upstream=$(mktemp -d)
trap 'rm -rf "$upstream"' EXIT
git clone -q --filter=blob:none --no-checkout "$repo_url.git" "$upstream"
latest=$(git -C "$upstream" rev-parse origin/main)

if [[ "$latest" == "$current" ]]; then
  printf '새 커밋 없음: %s\n' "$current"
  exit 0
fi

# 2. 변경 파일 중 CO-DAY 평가 점수나 실행 방식에 영향이 있는 경로만 선택
# 정답 데이터, 채점기와 실행 스크립트, 의존성, 입출력 규약, 채점 문서가 해당
# Harbor 실행용 스크립트는 사용하지 않으므로 제외
changed=$(git -C "$upstream" diff --name-only "$current" "$latest")
impact=$(printf '%s\n' "$changed" |
  grep -E '^(golden/|corpus/|scripts/|package\.json$|package-lock\.json$|AGENT_CONTRACT\.md$|docs/JUDGING(_INPUT)?\.md$)' |
  grep -v '^scripts/harbor/' || true)
# 경로 기준이 놓친 변경도 확인할 수 있도록 나머지 파일도 본문에 표시
others=$(printf '%s\n' "$changed" | grep -vxF -f <(printf '%s\n' "$impact") || true)
changed_count=$(printf '%s' "$changed" | grep -c . || true)
impact_count=$(printf '%s' "$impact" | grep -c . || true)
others_count=$(printf '%s' "$others" | grep -c . || true)
commit_count=$(git -C "$upstream" rev-list --count "$current..$latest")
latest_date=$(git -C "$upstream" log -1 --format=%cs "$latest")

# 3. PR 본문 작성
{
  printf '## 변경 요약\n\n'
  printf 'ReviewBench 기준 커밋을 `%s`에서 공식 main의 최신 커밋 `%s`(%s)으로 올립니다. ' \
    "${current:0:7}" "${latest:0:7}" "$latest_date"
  printf '그사이 공식 저장소에 커밋 %s개가 추가되었습니다.\n\n' "$commit_count"
  printf '> [!NOTE]\n'
  printf '> 업데이트 확인 워크플로가 자동으로 만들고 갱신하는 PR입니다. '
  printf '평가 결과 영향 표시와 변경 파일 목록을 확인해 merge 또는 close합니다.\n\n'

  if [[ "$impact_count" -gt 0 ]]; then
    printf '### 평가 결과 영향: 있음\n\n'
    printf '정답 데이터, 채점기, 실행 스크립트, 의존성, 입출력 규약 중 변경 파일이 %s개 있습니다. ' "$impact_count"
    printf 'merge하면 이전 버전 점수와 직접 비교할 수 없고, 팀원 모두 ReviewBench를 다시 설치해야 합니다.\n\n'
  else
    printf '### 평가 결과 영향: 없음\n\n'
    printf '자동 판단 기준(정답 데이터, 채점기, 실행 스크립트, 의존성, 입출력 규약)에 해당하는 변경이 없습니다. '
    printf '기준에 없는 경로도 평가 결과에 영향을 줄 수 있으므로 아래 파일 목록을 확인합니다.\n\n'
  fi

  printf '<details>\n<summary>변경 파일 %s개 (평가 관련 %s개, 기타 %s개)</summary>\n\n' \
    "$changed_count" "$impact_count" "$others_count"
  printf '**평가 관련 파일**\n\n'
  if [[ "$impact_count" -gt 0 ]]; then
    printf '%s\n' "$impact" | sed 's/.*/- `&`/'
  else
    printf -- '- 없음\n'
  fi
  printf '\n**기타 파일**\n\n'
  if [[ "$others_count" -gt 0 ]]; then
    printf '%s\n' "$others" | sed 's/.*/- `&`/'
  else
    printf -- '- 없음\n'
  fi
  printf '\n</details>\n\n'

  printf '<details>\n<summary>커밋 %s개</summary>\n\n' "$commit_count"
  git -C "$upstream" log --reverse --format="- [\`%h\`]($repo_url/commit/%H) %s" "$current..$latest"
  printf '\n</details>\n'
} > "$body"

printf '새 커밋 %s개, 평가 관련 파일 %s개: %s -> %s\n' \
  "$commit_count" "$impact_count" "${current:0:7}" "${latest:0:7}"

# GitHub Actions에서 다음 단계가 쓸 값 전달
if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  printf 'latest=%s\n' "$latest" >> "$GITHUB_OUTPUT"
fi

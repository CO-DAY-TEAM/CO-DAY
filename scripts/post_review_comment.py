# 테스트용 스크립트 파일 
import json
from urllib.request import Request, urlopen
from coday_core.config import github_app_id, github_private_key_path
from coday_core.github import create_app_jwt

app_jwt = create_app_jwt(
    app_id=github_app_id,
    private_key_path=github_private_key_path,
)

print("App JWT 생성 완료")

request = Request(
    url="https://api.github.com/app",
    headers={
        "Authorization": f"Bearer {app_jwt}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "CO-DAY-Act",
    },
    method="GET",
)

with urlopen(request, timeout=10) as response:
    app_info = json.load(response)

print("인증된 App:", app_info["slug"])

installation_request = Request(
    url="https://api.github.com/repos/CO-DAY-TEAM/CO-WORK/installation",
    headers={
        "Authorization": f"Bearer {app_jwt}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "CO-DAY-Act",
    },
    method="GET",
)

with urlopen(installation_request, timeout=10) as response:
    installation_info = json.load(response)

installation_id = installation_info["id"]

print("Installation ID:", installation_id)
print(
    "PR 권한:",
    installation_info["permissions"].get("pull_requests", "없음"),
)

token_request = Request(
    url=(
        "https://api.github.com/app/installations/"
        f"{installation_id}/access_tokens"
    ),
    headers={
        "Authorization": f"Bearer {app_jwt}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "CO-DAY-Act",
        "Content-Type": "application/json",
    },
    data=json.dumps({
        "repositories": ["CO-WORK"],
        "permissions": {"pull_requests": "write"},
    }).encode("utf-8"),
    method="POST",
)

with urlopen(token_request, timeout=10) as response:
    token_info = json.load(response)

installation_token = token_info["token"]

print("설치 토큰 발급 완료")
print("만료 시각:", token_info["expires_at"])

pr_request = Request(
    url="https://api.github.com/repos/CO-DAY-TEAM/CO-WORK/pulls/5",
    headers={
        "Authorization": f"Bearer {installation_token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "CO-DAY-Act",
    },
    method="GET",
)

with urlopen(pr_request, timeout=10) as response:
    pr_info = json.load(response)

head_sha = pr_info["head"]["sha"]

print("PR 상태:", pr_info["state"])
print("현재 Head SHA:", head_sha)
print(
    "예상 커밋과 일치:",
    head_sha == "2886297d73e182a4207c431e1c805ac789b70dab",
)

files_request = Request(
    url=(
        "https://api.github.com/repos/CO-DAY-TEAM/CO-WORK"
        "/pulls/5/files?per_page=100"
    ),
    headers={
        "Authorization": f"Bearer {installation_token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "CO-DAY-Act",
    },
    method="GET",
)

with urlopen(files_request, timeout=10) as response:
    changed_files = json.load(response)

target_path = "테스트/codeRabbit/pr-bot-test.js"

target_file = next(
    (file for file in changed_files if file["filename"] == target_path),
    None,
)

if target_file is None:
    raise SystemExit("조회한 목록에서 대상 파일을 찾지 못해 게시를 중단합니다.")
else:
    print("파일:", target_file["filename"])
    print("변경 유형:", target_file["status"])
    print("Diff:")
    print(target_file.get("patch") or "patch가 제공되지 않았습니다.")

# 사람이 diff를 확인한 뒤 파일의 실제 줄 번호를 입력한다.
# 자동 라인 매핑은 하지 않으며, 시작과 끝은 같은 측으로 제한한다.
while True:
    try:
        start_line = int(input("시작 줄 번호: "))
        end_line = int(input("끝 줄 번호 (한 줄이면 시작 줄과 동일): "))
    except ValueError:
        print("줄 번호는 정수로 입력해 주세요.")
        continue

    if not 1 <= start_line <= end_line:
        print("1 ≤ 시작 줄 ≤ 끝 줄 조건에 맞게 다시 입력해 주세요.")
        continue
    break

while True:
    side = input("코멘트 측 LEFT/RIGHT (Enter: RIGHT): ").strip().upper() or "RIGHT"
    if side in ("LEFT", "RIGHT"):
        break
    print("LEFT 또는 RIGHT를 입력해 주세요.")

comment_payload = {
    "commit_id": head_sha,
    "path": target_path,
    "line": end_line,
    "side": side,
    "body": "테스트: CO-DAY Act 모듈의 인라인 리뷰 코멘트입니다.",
}

# GitHub는 끝 줄을 end_line이 아닌 line으로 받는다.
# 단일 줄 요청에서는 시작 위치 필드를 보내지 않는다.
if start_line < end_line:
    comment_payload["start_line"] = start_line
    comment_payload["start_side"] = side

print(f"게시 범위: {side} {start_line}~{end_line}번 줄")
print("게시할 코멘트 요청:")
print(json.dumps(comment_payload, ensure_ascii=False, indent=2))

confirmation = input("PR #5에 코멘트 1건을 등록하려면 POST를 입력하세요: ")

if confirmation == "POST":
    comment_request = Request(
        url=(
            "https://api.github.com/repos/CO-DAY-TEAM/CO-WORK"
            "/pulls/5/comments"
        ),
        headers={
            "Authorization": f"Bearer {installation_token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "CO-DAY-Act",
            "Content-Type": "application/json",
        },
        data=json.dumps(comment_payload).encode("utf-8"),
        method="POST",
    )

    with urlopen(comment_request, timeout=10) as response:
        status_code = response.status
        comment_info = json.load(response)

    print("응답 상태:", status_code)
    print("코멘트 ID:", comment_info["id"])
    print("코멘트 URL:", comment_info["html_url"])
else:
    print("게시하지 않았습니다.")

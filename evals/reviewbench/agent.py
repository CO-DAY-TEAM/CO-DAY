"""ReviewBench 컨테이너 입출력을 기존 CO-DAY 분석/리뷰 함수에 연결"""

import asyncio
import json
import os
import subprocess
from pathlib import Path, PurePosixPath

from agents import set_default_openai_client, set_tracing_disabled
from coday_contracts.review_result import Finding
from coday_contracts.settings import ReviewSettings
from coday_core.config import Settings
from coday_pipeline.analyze.chunker import chunks
from coday_pipeline.analyze.diff_parser import parse_header, parse_patch
from coday_pipeline.analyze.file_filter import decode, exclusion
from coday_pipeline.judge.service import judge
from openai import AsyncOpenAI


def git(repo: Path, *args: str) -> bytes:
    # -C로 실행할 저장소를 지정하고, 파일명의 특수 문자도 패턴이 아닌 문자 그대로 취급한다.
    # safe.directory는 컨테이너에 마운트된 저장소의 소유자가 달라도 Git이 신뢰하도록 지정한다.
    # *args에는 diff, show 같은 하위 명령을 받고, 결과는 바이트로 반환한다.
    return subprocess.run(
        [
            "git",
            "--literal-pathspecs",
            "-c",
            f"safe.directory={repo}",
            "-C",
            str(repo),
            *args,
        ],
        check=True,
        capture_output=True,
    ).stdout


def changed_files(repo: Path, base: str, head: str) -> list[tuple[str, str, str]]:
    # -z는 공백·줄바꿈이 있는 파일명도 구분할 수 있도록 널 문자로 항목을 나눈다.
    fields = git(repo, "diff", "--name-status", "-z", "--find-renames", f"{base}...{head}")
    entries = iter(fields.decode("utf-8").rstrip("\0").split("\0") if fields else [])
    result = []

    for status in entries:
        old = next(entries)
        # 이름 변경(R)·복사(C)는 이전/이후 경로가 모두 나오고, 나머지는 경로가 하나다.
        new = next(entries) if status[0] in "RC" else old
        result.append((status[0], old, new))

    return result


def related_files(repo, head, changes, settings, patterns):
    """운영 collector와 같은 파일명/디렉터리 우선순위로 Git 객체에서 문맥을 읽는다."""

    changed = {path for _, _, path in changes}
    stems = {PurePosixPath(p).stem.removeprefix("test_").removesuffix(".test") for p in changed}
    directories = {str(PurePosixPath(p).parent) for p in changed}
    candidates = []

    for entry in git(repo, "ls-tree", "-rlz", "--full-tree", head).split(b"\0"):
        if not entry:
            continue

        meta, raw_path = entry.split(b"\t", 1)
        mode, kind, oid, size = meta.decode().split()
        path = raw_path.decode("utf-8")
        p = PurePosixPath(path)

        # 일반 파일만 문맥에 포함한다. 지침 파일 제외는 기존 CO-DAY 수집 정책을 따른다.
        if (
            kind != "blob"
            or mode not in {"100644", "100755"}
            or path in changed
            or exclusion(path, patterns)
            or p.name.upper() in {"AGENTS.MD", "CLAUDE.MD", "GEMINI.MD"}
            or int(size) > settings.chunk_chars
        ):
            continue

        # 파일명이 연관된 코드를 먼저, 같은 디렉터리의 코드를 다음 순위로 선택한다.
        related = any(stem and stem.lower() in p.stem.lower() for stem in stems)
        if related or str(p.parent) in directories:
            candidates.append((0 if related else 1, path, oid))

    result = {}

    # 운영 collector처럼 후보 수를 먼저 제한하고, HEAD의 객체 ID로 내용을 읽는다.
    for _, path, oid in sorted(candidates)[: settings.related_file_count]:
        content = decode(git(repo, "cat-file", "blob", oid))
        if content is not None:
            result[path] = content

    return result


def head_location(finding: Finding, hunks, line_count: int) -> tuple[int, int] | None:
    """ReviewBench는 HEAD 좌표만 받는다. 삭제 줄은 인접한 HEAD 줄로 연결한다."""

    if not line_count:
        return None  # 삭제된 파일/빈 파일에는 유효한 HEAD 위치가 없다.

    if finding.side == "RIGHT":
        return finding.start_line or finding.line, finding.line

    for hunk in hunks:
        cursor = parse_header(hunk.header).new_start
        for line in hunk.lines:
            if line.kind == "removed" and line.old_line == finding.line:
                # 삭제된 줄이 있던 HEAD 지점을 찾아 실제 파일의 줄 범위 안으로 맞춘다.
                anchor = min(max(cursor, 1), line_count)
                return anchor, anchor

            if line.new_line is not None:
                cursor = line.new_line + 1

    raise ValueError("삭제 전 줄에 대한 지적 위치를 변경 내역에서 찾을 수 없습니다.")


async def review() -> None:
    # 공식 러너가 전달한 PR 커밋, 마운트 경로, 리뷰 모델을 읽는다.
    base, head = os.environ["RB_BASE"], os.environ["RB_HEAD"]
    repo = Path(os.environ.get("RB_REPO", "/work/repo"))
    pr = json.loads(Path(os.environ.get("RB_PR_JSON", "/work/pr/pr.json")).read_text())
    model = os.environ["RB_CONFIG_MODEL"]

    # CO-DAY 기본 설정에 실행용 키·모델을 적용한다. 컨테이너의 .env는 읽지 않는다.
    settings = Settings(
        _env_file=None,
        openai_model=model,
        openai_api_key=os.environ["OPENAI_API_KEY"],
    )

    # Agents SDK 추적은 끄고, CO-DAY의 리뷰 호출에 사용할 OpenAI 클라이언트를 지정한다.
    set_tracing_disabled(True)
    client = AsyncOpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.environ.get("RB_MODEL_BASE_URL") or "https://api.openai.com/v1",
        # 운영 워커와 동일하게 재시도는 Agents SDK에 맡기고 요청 제한은 180초로 둔다.
        max_retries=0,
        timeout=180,
    )
    set_default_openai_client(client, use_for_tracing=False)
    print(f"CO-DAY 리뷰 모델={model}", flush=True)

    # 변경·관련 코드를 모으고, CO-DAY의 입력 크기 및 호출 횟수 제한을 적용한다.
    changes = changed_files(repo, base, head)
    patterns = ReviewSettings().exclude_patterns
    context = related_files(repo, head, changes, settings, patterns)
    total_bytes = sum(len(text.encode()) for text in context.values())
    attempts = 0

    # 기존 judge()가 AI 요청과 내부 재시도 전에 호출한다. PR 전체의 호출 한도를 계산한다.
    async def reserve():
        nonlocal attempts
        attempts += 1

        if attempts > settings.max_ai_calls:
            raise RuntimeError("CO-DAY의 AI 호출 횟수 한도를 초과했습니다.")

    # 공식 출력, 변환 전 리뷰, HEAD 좌표가 없어 제외한 지적을 각각 모은다.
    findings, original, omitted = [], [], 0
    statuses = {
        "A": "added",
        "D": "removed",
        "R": "renamed",
        "C": "copied",
        "M": "modified",
    }
    producer = os.environ.get("RB_AGENT", "coday")

    try:
        for status, old, path in changes:
            if exclusion(path, patterns):
                continue

            # 외부 diff 도구나 텍스트 변환 없이 PR의 원본 변경 내역을 읽는다.
            raw = git(
                repo,
                "diff",
                "--no-ext-diff",
                "--no-textconv",
                "--no-color",
                "--find-renames",
                f"{base}...{head}",
                "--",
                old,
                path,
            )

            total_bytes += len(raw)
            if len(raw) > settings.max_file_bytes or total_bytes > settings.max_input_bytes:
                raise RuntimeError("CO-DAY의 입력 크기 한도를 초과했습니다.")

            patch = decode(raw)
            if patch is None:
                continue

            hunks = parse_patch(patch)
            parts = chunks(path, statuses.get(status, "changed"), hunks, settings.chunk_chars)

            # HEAD의 줄 수는 삭제 전 지적을 현재 파일의 유효한 좌표로 옮길 때 사용한다.
            content = b"" if status == "D" else git(repo, "show", f"{head}:{path}")
            line_count = content.count(b"\n") + int(bool(content) and not content.endswith(b"\n"))

            for chunk in parts:
                # CO-DAY의 리뷰 생성 함수다. ReviewBench 채점은 컨테이너 밖에서 수행한다.
                # 추가 리뷰 지시문은 사용하지 않으므로 세 번째 인자에 빈 문자열을 전달한다.
                result = await judge(chunk, context, "", settings, reserve)

                for finding in result.findings:
                    original.append(finding.model_dump())
                    location = head_location(finding, hunks, line_count)
                    if location is None:
                        omitted += 1
                        continue

                    message = "\n".join(
                        [
                            finding.title,
                            f"발생 조건: {finding.condition}",
                            f"코드 근거: {finding.evidence}",
                            f"수정 방향: {finding.recommendation}",
                        ]
                    )

                    if finding.side == "LEFT":
                        message = (
                            f"삭제 전 {finding.start_line or finding.line}–{finding.line}행: "
                            + message
                        )

                    if finding.suggestion:
                        message += f"\n```suggestion\n{finding.suggestion}\n```"

                    findings.append(
                        {
                            "file": finding.path,
                            "start_line": location[0],
                            "end_line": location[1],
                            "message": message,
                            "producer": producer,
                        }
                    )

        out = Path(os.environ["RB_OUT"])
        out.parent.mkdir(parents=True, exist_ok=True)

        # 좌표 변환·제외 여부를 확인할 수 있도록 CO-DAY 원본 결과도 함께 보관한다.
        (out.parent / "raw-review.json").write_text(
            json.dumps(
                {
                    "findings": original,
                    "omitted_without_head_location": omitted,
                    "model": model,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        # 공식 러너와 채점기가 읽는 ReviewBench findings 형식으로 저장한다.
        out.write_text(
            json.dumps(
                {
                    "pr": {key: pr[key] for key in ("repo", "pr_number", "base", "head")},
                    "agent": producer,
                    "findings": findings,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        print(f"CO-DAY 지적={len(findings)}건, HEAD 좌표가 없어 제외된 지적={omitted}건")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(review())

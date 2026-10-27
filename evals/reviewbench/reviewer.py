"""ReviewBench 컨테이너 입출력을 기존 CO-DAY 분석/리뷰 함수에 연결한다."""

import asyncio
import json
import os
import subprocess
import time
from pathlib import Path, PurePosixPath

from agents import set_default_openai_client
from coday_contracts.review_result import Finding
from coday_contracts.settings import ReviewSettings
from coday_core.config import Settings
from coday_pipeline.analyze.chunker import chunks
from coday_pipeline.analyze.diff_parser import parse_header, parse_patch
from coday_pipeline.analyze.file_filter import decode, exclusion
from coday_pipeline.judge.service import judge
from coday_pipeline.langfuse import setup_langfuse
from langfuse import get_client
from openai import AsyncOpenAI


def git(repo: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", "--literal-pathspecs", "-c", f"safe.directory={repo}", "-C", str(repo), *args],
        check=True,
        capture_output=True,
    ).stdout


def changed_files(repo: Path, base: str, head: str) -> list[tuple[str, str, str]]:
    fields = git(repo, "diff", "--name-status", "-z", "--find-renames", f"{base}...{head}")
    entries = iter(fields.decode("utf-8").rstrip("\0").split("\0") if fields else [])
    result = []
    for status in entries:
        old = next(entries)
        new = next(entries) if status[0] in "RC" else old
        result.append((status[0], old, new))
    return result


def related_files(repo, head, changes, settings, patterns):
    """운영 collector와 같은 파일명/디렉터리 우선순위로 Git 객체에서 문맥을 읽는다."""
    changed = {path for _, old, new in changes for path in (old, new)}
    stems = {PurePosixPath(p).stem.removeprefix("test_").removesuffix(".test") for p in changed}
    directories = {str(PurePosixPath(p).parent) for p in changed}
    candidates = []
    for entry in git(repo, "ls-tree", "-rz", "--full-tree", head).split(b"\0"):
        if not entry:
            continue
        meta, raw_path = entry.split(b"\t", 1)
        mode, kind, oid = meta.decode().split()
        path = raw_path.decode("utf-8")
        p = PurePosixPath(path)
        if (
            kind != "blob"
            or mode not in {"100644", "100755"}
            or path in changed
            or exclusion(path, patterns)
            or p.name.upper() in {"AGENTS.MD", "CLAUDE.MD", "GEMINI.MD"}
        ):
            continue
        related = any(stem and stem.lower() in p.stem.lower() for stem in stems)
        if related or str(p.parent) in directories:
            candidates.append((0 if related else 1, path, oid))
    result = {}
    for _, path, oid in sorted(candidates):
        if len(result) >= settings.related_file_count:
            break
        if int(git(repo, "cat-file", "-s", oid)) <= settings.chunk_chars:
            content = decode(git(repo, "cat-file", "blob", oid))
            if content is not None:
                result[path] = content
    return result


def head_location(finding: Finding, hunks, line_count: int) -> tuple[int, int] | None:
    """ReviewBench는 HEAD 좌표만 받는다. 삭제 줄은 인접한 HEAD 줄로 연결한다."""
    if not line_count:
        return None  # 삭제된 파일/빈 파일에는 유효한 HEAD 위치가 없다.
    if finding.side == "RIGHT":
        start, end = finding.start_line or finding.line, finding.line
        if end > line_count:
            raise ValueError("Finding exceeds HEAD file length")
        return start, end
    for hunk in hunks:
        cursor = parse_header(hunk.header).new_start
        for line in hunk.lines:
            if line.kind == "removed" and line.old_line == finding.line:
                anchor = min(max(cursor, 1), line_count)
                return anchor, anchor
            if line.new_line is not None:
                cursor = line.new_line + 1
    raise ValueError("Deleted finding has no corresponding diff location")


async def review() -> None:
    started = time.monotonic()
    required = ("RB_NWO", "RB_PR_NUMBER", "RB_BASE", "RB_HEAD", "RB_OUT", "OPENAI_API_KEY")
    for key in required:
        if not os.environ.get(key):
            raise ValueError(f"Missing {key}")
    base, head = os.environ["RB_BASE"], os.environ["RB_HEAD"]
    repo = Path(os.environ.get("RB_REPO", "/work/repo"))
    pr = json.loads(Path(os.environ.get("RB_PR_JSON", "/work/pr/pr.json")).read_text())
    model = os.environ.get("RB_CONFIG_MODEL", os.environ.get("REVIEW_MODEL", ""))
    if not model:
        raise ValueError("A review model is required")
    settings = Settings(
        _env_file=None, openai_model=model, openai_api_key=os.environ["OPENAI_API_KEY"]
    )
    # 기존 워커와 같은 프롬프트 조회 경로를 사용한다. 트레이싱은 기본값(false)이다.
    setup_langfuse(settings)
    prompt = get_client().get_prompt("prompt")
    prompt_info = {"name": prompt.name, "version": prompt.version}
    client = AsyncOpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.environ.get("RB_MODEL_BASE_URL") or "https://api.openai.com/v1",
    )
    set_default_openai_client(client, use_for_tracing=False)
    print(f"CO-DAY model={model} prompt={prompt.name} version={prompt.version}", flush=True)
    changes = changed_files(repo, base, head)
    patterns = ReviewSettings().exclude_patterns
    context = related_files(repo, head, changes, settings, patterns)
    total_bytes = sum(len(text.encode()) for text in context.values())
    attempts = 0

    async def reserve():
        nonlocal attempts
        attempts += 1
        if attempts > settings.max_ai_calls:
            raise RuntimeError("CO-DAY max_ai_calls exceeded")

    findings, original, omitted = [], [], 0
    statuses = {"A": "added", "D": "removed", "R": "renamed", "C": "copied", "M": "modified"}
    producer = os.environ.get("RB_AGENT", "coday")
    try:
        for status, old, path in changes:
            if exclusion(path, patterns):
                continue
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
                raise RuntimeError("CO-DAY input size limit exceeded")
            patch = decode(raw)
            if patch is None:
                continue
            hunks = parse_patch(patch)
            parts = chunks(path, statuses.get(status, "changed"), hunks, settings.chunk_chars)
            content = b"" if status == "D" else git(repo, "show", f"{head}:{path}")
            line_count = content.count(b"\n") + int(bool(content) and not content.endswith(b"\n"))
            for chunk in parts:
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
        (out.parent / "coday.json").write_text(
            json.dumps(
                {
                    "findings": original,
                    "omitted_without_head_location": omitted,
                    "model": model,
                    "prompt": prompt_info,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        out.write_text(
            json.dumps(
                {
                    "pr": {key: pr[key] for key in ("repo", "pr_number", "base", "head")},
                    "agent": producer,
                    "findings": findings,
                    "usage": {"time_in_ms": round((time.monotonic() - started) * 1000)},
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"CO-DAY findings={len(findings)} omitted_without_head_location={omitted}")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(review())

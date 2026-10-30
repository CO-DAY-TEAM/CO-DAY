# GitHub의 PR patch와 관련 코드를 수집
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from coday_contracts.analyzed_chunk import FileStatus
from coday_contracts.review_job import ReviewJob
from coday_contracts.settings import ReviewSettings
from coday_core.errors import ServiceError
from coday_core.github import GitHub, repo_path

from coday_pipeline.analyze.file_filter import decode, exclusion


@dataclass(frozen=True)
class FilePatch:
    path: str
    status: FileStatus
    patch: str
    additions: int
    deletions: int


@dataclass
class CollectedFiles:
    files: list[FilePatch] = field(default_factory=list)
    excluded_files: dict[str, str] = field(default_factory=dict)
    related_files: dict[str, str] = field(default_factory=dict)


async def collect(
    job: ReviewJob, settings: ReviewSettings, github: GitHub, token: str, guard
) -> CollectedFiles:
    name = f"{job.owner}/{job.repo}"
    root = repo_path(name)
    await guard()
    pr = await github.request(token, "GET", f"{root}/pulls/{job.pr_number}")
    files = await github.pages(token, f"{root}/pulls/{job.pr_number}/files")
    if len(files) != pr["changed_files"]:
        raise ServiceError("incomplete_diff", "GitHub에서 전체 변경 파일을 가져오지 못했습니다.")
    output = CollectedFiles()
    total = 0
    for file in files:
        await guard()
        path = file["filename"]
        reason = exclusion(path, settings.exclude_patterns)
        if reason:
            output.excluded_files[path] = reason
            continue
        if file["changes"] == 0:
            output.excluded_files[path] = "텍스트 변경 없음"
            continue
        patch = file.get("patch")
        if not patch:
            raise ServiceError(
                "incomplete_diff", f"GitHub에서 {path}의 patch를 가져오지 못했습니다."
            )
        patch_size = len(patch.encode("utf-8"))
        if patch_size > github.settings.max_file_bytes:
            raise ServiceError("file_limit", "파일의 patch 크기가 처리 한도를 넘었습니다.")
        total += patch_size
        if total > github.settings.max_input_bytes:
            raise ServiceError(
                "input_limit",
                "전체 입력 처리 한도를 넘었습니다. 운영 설정 또는 제외 경로를 확인해 주세요.",
            )
        output.files.append(
            FilePatch(path, file["status"], patch, file["additions"], file["deletions"])
        )
    await guard()
    if not output.files or github.settings.related_file_count == 0:
        return output
    # 관련 구현·타입·테스트를 정해진 범위에서 읽기만 하며, 지침 파일은 문맥에 포함하지 않는다.
    tree = await github.request(
        token, "GET", f"{root}/git/trees/{job.head_sha}", params={"recursive": 1}
    )
    if tree.get("truncated"):
        raise ServiceError(
            "incomplete_tree",
            "관련 코드 탐색용 파일 목록이 잘렸습니다. 전체 목록을 확보하지 못했습니다.",
        )
    changed = {f["filename"] for f in files}
    stems = {
        PurePosixPath(path).stem.removeprefix("test_").removesuffix(".test") for path in changed
    }
    directories = {str(PurePosixPath(path).parent) for path in changed}
    candidates = []
    for item in tree["tree"]:
        path = item["path"]
        p = PurePosixPath(path)
        if (
            item["type"] != "blob"
            or path in changed
            or exclusion(path, settings.exclude_patterns)
            or p.name.upper() in {"AGENTS.MD", "CLAUDE.MD", "GEMINI.MD"}
            or item.get("size", 0) > github.settings.chunk_chars
        ):
            continue
        related = any(stem and stem.lower() in p.stem.lower() for stem in stems)
        nearby = str(p.parent) in directories
        if related or nearby:
            candidates.append((0 if related else 1, path))
    for _, path in sorted(candidates)[: github.settings.related_file_count]:
        await guard()
        content = decode(await github.file(token, name, path, job.head_sha))
        if content is not None:
            total += len(content.encode())
            if total > github.settings.max_input_bytes:
                raise ServiceError("input_limit", "관련 코드를 포함한 입력 처리 한도를 넘었습니다.")
            output.related_files[path] = content
    return output

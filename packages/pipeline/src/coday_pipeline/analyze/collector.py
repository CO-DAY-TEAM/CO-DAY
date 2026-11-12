# GitHub의 PR patch와 관련 코드를 수집
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from coday_contracts import FileStatus, ReviewJob, ReviewSettings
from coday_core.errors import ServiceError
from coday_core.github import GitHub, repo_path

from coday_pipeline.analyze.configuration import (
    CONFIG_SUFFIXES,
    configuration_priorities,
    patch_source,
)
from coday_pipeline.analyze.file_filter import decode, exclusion
from coday_pipeline.analyze.imports import (
    SOURCE_SUFFIXES,
    eligible_context,
    import_priorities,
    related_candidates,
)


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
    metadata = {
        item["path"]: item
        for item in tree["tree"]
        if item["type"] == "blob" and item.get("mode", "100644") in {"100644", "100755"}
    }
    paths = set(metadata)
    imports = {}
    configurations = {}
    source_bytes = 0
    for file in output.files:
        if file.status == "removed" and PurePosixPath(file.path).suffix in CONFIG_SUFFIXES:
            configurations[file.path] = patch_source(file.patch, "old")
        item = metadata.get(file.path)
        if (
            item is None
            or PurePosixPath(file.path).suffix not in SOURCE_SUFFIXES | CONFIG_SUFFIXES
            or item.get("size", 0) > github.settings.max_file_bytes
            or source_bytes + item.get("size", 0) > github.settings.max_input_bytes
        ):
            continue
        await guard()
        raw = await github.file(token, name, file.path, job.head_sha)
        source_bytes += len(raw)
        source = decode(raw)
        if source is None or source_bytes > github.settings.max_input_bytes:
            continue
        if PurePosixPath(file.path).suffix in CONFIG_SUFFIXES:
            configurations[file.path] = source
        for path, rank in import_priorities(file.path, source, file.patch, paths).items():
            imports[path] = min(rank, imports.get(path, rank))
    for path, rank in configuration_priorities(
        changed, configurations, paths, f"https://github.com/{name}"
    ).items():
        imports[path] = min(rank, imports.get(path, rank))
    eligible = {
        path
        for path, item in metadata.items()
        if eligible_context(
            path,
            item.get("mode", "100644"),
            item.get("size", 0),
            github.settings.max_related_file_bytes,
            settings.exclude_patterns,
        )
    }
    candidates = related_candidates(changed, eligible, imports)
    reads = 0
    for path in candidates:
        if (
            len(output.related_files) >= github.settings.related_file_count
            or reads >= 2 * github.settings.related_file_count
        ):
            break
        if metadata[path].get("size", 0) > github.settings.max_input_bytes - total:
            continue
        await guard()
        raw = await github.file(token, name, path, job.head_sha)
        reads += 1
        if not raw or len(raw) > min(
            github.settings.max_related_file_bytes, github.settings.max_input_bytes - total
        ):
            continue
        content = decode(raw)
        if content is not None:
            total += len(content.encode())
            output.related_files[path] = content
    return output

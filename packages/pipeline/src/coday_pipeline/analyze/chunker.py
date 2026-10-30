# hunk → AnalyzedChunk 목록
from coday_contracts.analyzed_chunk import AnalyzedChunk, DiffLine, FileStatus
from coday_core.errors import ServiceError

from coday_pipeline.analyze.diff_parser import ParsedHunk


def chunks(
    path: str, status: FileStatus, hunks: list[ParsedHunk], limit: int
) -> list[AnalyzedChunk]:
    result = []
    lines: list[DiffLine] = []
    header, size = "", 0

    def flush():
        nonlocal lines, size
        if lines and any(line.kind != "context" for line in lines):
            result.append(
                AnalyzedChunk(
                    file_path=path,
                    status=status,
                    hunk_header=header,
                    lines=tuple(lines),
                )
            )
        lines, size = [], 0

    for hunk in hunks:
        header = hunk.header
        for line in hunk.lines:
            # patch의 +, -, 공백 기호까지 포함해 기존과 같은 기준으로 크기를 센다.
            line_size = len(line.content) + 1
            if line_size > limit:
                raise ServiceError(
                    "line_limit",
                    "한 줄의 코드가 chunk 크기 한도를 넘었습니다. 생성된 파일인지 확인하거나 운영 설정을 확인해 주세요.",
                )
            if lines and size + line_size > limit:
                flush()
            lines.append(line)
            size += line_size
        flush()
    return result

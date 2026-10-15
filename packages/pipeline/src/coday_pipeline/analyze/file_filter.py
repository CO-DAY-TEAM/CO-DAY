# 리뷰할 파일인지 판단
from fnmatch import fnmatchcase
from pathlib import PurePosixPath

BINARY_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".webp",
    ".pdf",
    ".zip",
    ".gz",
    ".7z",
    ".woff",
    ".woff2",
    ".ttf",
    ".mp3",
    ".mp4",
    ".mov",
    ".exe",
    ".dll",
    ".so",
    ".pyc",
}


def exclusion(path: str, patterns: list[str]) -> str | None:
    if PurePosixPath(path).suffix.lower() in BINARY_EXTENSIONS:
        return "바이너리 파일"
    for pattern in patterns:
        pattern = pattern.strip()
        if pattern and (
            fnmatchcase(path, pattern)
            or (pattern.startswith("**/") and fnmatchcase(path, pattern[3:]))
        ):
            return f"제외 경로: {pattern}"
    return None


def decode(content: bytes) -> str | None:
    if b"\0" in content:
        return None
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return None

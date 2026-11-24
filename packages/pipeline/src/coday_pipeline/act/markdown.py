"""GitHub 리뷰에 표시할 Markdown을 구성한다."""

import re
import string
from html import escape
from urllib.parse import urlsplit

BADGE_BASE_URL = "https://raw.githubusercontent.com/CO-DAY-TEAM/CO-DAY/main/assets/badges"

SEVERITY_BADGES = {
    "Critical": ("critical", "Critical"),
    "High": ("high", "High"),
    "Medium": ("medium", "Medium"),
    "Low": ("low", "Low"),
}
CATEGORY_BADGES = {
    "bug": ("bug", "Bug"),
    "security": ("security", "Security"),
    "performance": ("performance", "Performance"),
    "maintainability": ("maintainability", "Maintainability"),
    "style": ("style", "Style"),
}


def render_review_badges(severity: str, category: str, *, base_url: str = BADGE_BASE_URL) -> str:
    if not re.fullmatch(
        r"https://[a-zA-Z0-9.-]+(?::[0-9]+)?(?:/[a-zA-Z0-9._~!$&'()+;=/-]*)?", base_url
    ):
        raise ValueError("뱃지 경로는 인증 정보가 없는 HTTPS URL이어야 합니다.")
    url = urlsplit(base_url)
    if (
        not url.hostname
        or not all(
            re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
            for label in url.hostname.split(".")
        )
        or url.port == 0
    ):
        raise ValueError("뱃지 URL의 호스트 또는 포트가 올바르지 않습니다.")

    try:
        severity_badge = SEVERITY_BADGES[severity]
        category_badge = CATEGORY_BADGES[category]
    except KeyError as exc:
        raise ValueError("지원하지 않는 리뷰 뱃지입니다.") from exc

    return " ".join(
        _badge_picture(f"{base_url.rstrip('/')}/{group}/{prefix}", label)
        for group, (prefix, label) in (("severity", severity_badge), ("category", category_badge))
    )


def _badge_picture(url_prefix: str, label: str) -> str:
    dark = escape(f"{url_prefix}-dark.svg", quote=True)
    light = escape(f"{url_prefix}-light.svg", quote=True)
    return (
        "<picture>"
        f'<source media="(prefers-color-scheme: dark)" srcset="{dark}">'
        f'<source media="(prefers-color-scheme: light)" srcset="{light}">'
        f'<img src="{light}" alt="{escape(label, quote=True)}" height="18" align="texttop">'
        "</picture>"
    )


def excluded_file_row(path: str, reason: str) -> str:
    # 줄바꿈과 탭이 파일 목록의 Markdown 구조에 영향을 주지 않게 표시한다.
    controls = str.maketrans({"\r": r"\r", "\n": r"\n", "\t": r"\t"})
    path = path.translate(controls)
    fence = "`" * (1 + max((len(run) for run in re.findall(r"`+", path)), default=0))
    if path.startswith(("`", " ")) or path.endswith(("`", " ")):
        path = f" {path} "
    # 설정에서 온 제외 패턴은 링크, 강조, HTML, 멘션처럼 해석될 수 있다.
    reason = reason.translate(controls).replace("@", "@\u200b")
    literal = reason.translate(
        str.maketrans({char: f"&#{ord(char)};" for char in string.punctuation})
    )
    return f"- {fence}{path}{fence} — {literal}"


def escape_prose_tildes(text: str) -> str:
    # GitHub는 ~~뿐 아니라 ~text~도 취소선으로 처리한다.
    # backtick 개수가 같은 코드 구간과 기존 backslash escape는 그대로 둔다.
    output: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\\" and index + 1 < len(text):
            output.append(text[index : index + 2])
            index += 2
            continue
        if char == "`":
            end = index + 1
            while end < len(text) and text[end] == "`":
                end += 1
            closing = next(
                (
                    match
                    for match in re.finditer(r"`+", text[end:])
                    if len(match.group()) == end - index
                ),
                None,
            )
            if closing is not None:
                end += closing.end()
            output.append(text[index:end])
            index = end
            continue
        output.append("\\~" if char == "~" else char)
        index += 1
    return "".join(output)

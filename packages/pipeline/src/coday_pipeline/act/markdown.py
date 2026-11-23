"""GitHub 리뷰에 표시할 Markdown을 구성한다."""

import re
import string


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

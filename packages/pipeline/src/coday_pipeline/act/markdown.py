"""GitHub 설명문에서 취소선 구분자만 escape한다. 코드 내용은 보존한다."""

import re


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

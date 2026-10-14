# patch 문자열 → hunk와 줄 번호

import re
from pydantic import BaseModel
from typing import NamedTuple
from coday_contracts import DiffLine

# diffLine은 coday_contracts/analyzed_chunk.py 에 있는 DiffLine 클래스를 사용한다.

class ParsedHunk(BaseModel):
    header: str     # @@ -10,4 +10,5 @@ def add
    lines: list[DiffLine]

class SplitHeader(NamedTuple):
    old_start: int    # -10
    old_count: int    # 4
    new_start: int    # +10
    new_count: int    # 4


# patch 전체를 hunk 목록으로 나누고, 각 줄에 변경 전/후 줄 번호를 붙인다.
# 입력: patch 문자열
# 출력: hunk 목록 (header, lines(diffLine 목록))
# "patch": "@@ -10,4 +10,5 @@ def add\n def add(a, b):\n-    return a+b\n+..."
def parse_patch(patch: str) -> list[ParsedHunk]:
    # 1. patch 문자열을 줄 단위로 나눈다.
    # splitlines() 메서드는 문자열을 줄 단위로 나누어 리스트로 반환한다.
    # split("\n")은 문자열을 "\n"을 기준으로 나누어 리스트로 반환한다. 단, 맨 끝 줄바꿈이 있다면 ['a', 'b', ''] 처럼 빈 문자열이 하나 더 생김
    # c소스나 일부 텍스트 파일에 \f나 \u2028 같은 문자가 있는 경우, splitlines()는 실제로 한 줄인 것을 두 줄로 잘라서 줄 번호 계산이 어긋남.
    # 그래서 split("\n")을 쓴다
    
    # 전체 끝의 \n부터 제거
    clean_patch = patch.rstrip("\n")
    lines = clean_patch.split("\n")

    hunks = []
    current_hunk = None

    # 2. header 영역 나누기
    for line in lines:
        if line.startswith("@@"):
            header_info = parse_header(line)
            old_no = header_info.old_start
            new_no = header_info.new_start

            # lines가 빈 리스트인 ParsedHunk를 새로 만들고, header를 원본 줄 그대로 넣는다.
            current_hunk = ParsedHunk(header=line, lines=[])
            hunks.append(current_hunk)
        elif current_hunk is not None:
            diff_line = to_diff_line(line, old_no, new_no)
            if diff_line is not None:
                # 변경 전 파일에 있는 줄이면 old를, 변경 후 파일에 있는 줄이면 new를 올린다.
                if diff_line.old_line is not None:
                    old_no += 1
                if diff_line.new_line is not None:
                    new_no += 1
                current_hunk.lines.append(diff_line)
    return hunks

# hunk header에서 시작 줄과 줄 수 4개를 정규식으로 꺼낸다. 줄 수가 생략되면 1로 본다.
# 입력: header 한 줄 ("@@ -5,33 +5,97 @@")
# 출력: SplitHeader(5, 33, 5, 97)
def parse_header(header: str) -> SplitHeader:
    pattern = r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@"
    m = re.match(pattern, header)
    if m is None:
        raise ValueError(f"잘못된 hunk header: {header}")
    
    # 줄 수(group 2, 4)는 생략되면 None이므로 or로 1을 넣는다.
    old_start = int(m.group(1))
    old_count = int(m.group(2) or 1)
    new_start = int(m.group(3))
    new_count = int(m.group(4) or 1)

    return SplitHeader(old_start, old_count, new_start, new_count)

# diff 한 줄을 첫 기호(+, -, 공백)로 구분해 DiffLine으로 바꾼다. 코드가 아닌 줄(\ 등)은 None.
# 입력: "-b", 지금 줄 번호(old_no, new_no)
# 출력: DiffLine(kind="removed", content="b", old_line=6)
def to_diff_line(line: str, old_no: int, new_no: int) -> DiffLine | None:
    # 빈 줄이 들어올 수 있어서 line[0] 대신 line[:1] 을 사용
    match line[:1]:
        case "+":
            return DiffLine(kind="added", content=line[1:], new_line=new_no)
        case "-":
            return DiffLine(kind="removed", content=line[1:], old_line=old_no)
        case "" | " ":
            return DiffLine(kind="context", content=line[1:], old_line=old_no, new_line=new_no)

        case _:
            return None

from difflib import unified_diff

from coday_pipeline.analyze.chunker import chunks
from coday_pipeline.analyze.diff_parser import parse_patch


# diff를 여러 chunk로 나눠도 추가·삭제 줄 번호가 빠짐없이 유지되는지 확인한다.
def test_full_diff_line_mapping_and_chunk_coverage():
    before = "\n".join(f"old_{i}" for i in range(50))
    after = "\n".join(f"new_{i}" for i in range(50))
    patch = "\n".join(unified_diff(before.splitlines(), after.splitlines(), n=5, lineterm=""))
    result = chunks("a.py", "modified", parse_patch(patch), 100)
    assert len(result) > 1
    assert [
        line.new_line for chunk in result for line in chunk.lines if line.kind == "added"
    ] == list(range(1, 51))
    assert [
        line.old_line for chunk in result for line in chunk.lines if line.kind == "removed"
    ] == list(range(1, 51))

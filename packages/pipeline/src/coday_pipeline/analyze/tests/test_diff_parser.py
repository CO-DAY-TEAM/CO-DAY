from difflib import unified_diff

from coday_pipeline.analyze.diff_parser import parse_patch


# patch에서 추가·삭제 줄 번호가 빠짐없이 유지되는지 확인한다.
def test_full_diff_line_mapping():
    before = "\n".join(f"old_{i}" for i in range(50))
    after = "\n".join(f"new_{i}" for i in range(50))
    patch = "\n".join(unified_diff(before.splitlines(), after.splitlines(), n=5, lineterm=""))
    result = parse_patch(patch)
    assert [
        line.new_line for hunk in result for line in hunk.lines if line.kind == "added"
    ] == list(range(1, 51))
    assert [
        line.old_line for hunk in result for line in hunk.lines if line.kind == "removed"
    ] == list(range(1, 51))

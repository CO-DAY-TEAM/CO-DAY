import pytest
from coday_contracts import AnalyzedFile, DiffLine, ParsedHunk, ReviewInput, ReviewResult
from coday_core.db.models import Review
from coday_pipeline.act.service import build_publication


def finding_data(**updates):
    return {
        "category": "security",
        "severity": "P1",
        "title": "URL scheme 검증 누락",
        "condition": "사용자가 작성한 링크를 클릭하면 발생합니다.",
        "evidence": "`href`에 허용하지 않은 URL scheme도 들어갈 수 있습니다.",
        "recommendation": "허용한 URL scheme에 해당하는 링크만 생성하세요.",
        "path": "links.ts",
        "line": 1,
        "side": "RIGHT",
        "start_line": None,
        "suggestion": None,
        **updates,
    }


# 댓글의 설명 문단을 구성하고, suggestion이 있을 때만 교체 코드를 한 번 표시하는지 확인한다.
@pytest.mark.parametrize(
    "suggestion", [None, "const parsed = new URL(href);\nreturn parsed.protocol;"]
)
def test_server_renders_sections_and_only_one_suggestion(suggestion):
    result = ReviewResult.model_validate({"findings": [finding_data(suggestion=suggestion)]})
    batches = build_publication(
        Review(id="test", head_sha="head"),
        result,
        ReviewInput(
            files=[
                AnalyzedFile(
                    file_path="links.ts",
                    status="added",
                    hunks=[
                        ParsedHunk(
                            header="@@ -0,0 +1 @@",
                            lines=[DiffLine(kind="added", content="const href = url;", new_line=1)],
                        )
                    ],
                )
            ]
        ),
    )
    body = batches[0]["comments"][0]["body"]
    assert all(label in body for label in ("발생 조건", "코드 근거", "수정 방향"))
    assert "`href`" in body
    assert "suggestion: null" not in body
    assert body.count("```suggestion") == (0 if suggestion is None else 1)
    if suggestion:
        assert body.count(suggestion) == 1


@pytest.mark.parametrize("importance,severity", [("important", "P1"), ("minor", "P3")])
def test_legacy_importance_is_read_without_changing_new_schema(importance, severity):
    from coday_contracts import Finding

    data = finding_data()
    data.pop("severity")
    data["importance"] = importance
    finding = Finding.model_validate(data)
    assert finding.severity == severity
    assert "importance" not in finding.model_dump()
    assert "importance" not in Finding.model_json_schema()["properties"]


def test_overlapping_suggestions_keep_priority_and_preserve_findings():
    from itertools import permutations

    from coday_pipeline.suggestion_conflicts import resolve_suggestion_conflicts

    data = [
        finding_data(title="wide", severity="P2", start_line=1, line=5, suggestion="wide"),
        finding_data(title="high", severity="P1", start_line=3, line=7, suggestion="high"),
        finding_data(title="short", severity="P1", start_line=4, line=4, suggestion="short"),
        finding_data(title="adjacent", severity="P2", start_line=8, line=9, suggestion=""),
        finding_data(title="other", path="other.ts", start_line=4, line=4, suggestion="other"),
    ]
    for order in permutations(data):
        result = ReviewResult.model_validate({"findings": list(order)})
        before = result.model_dump()
        resolved = resolve_suggestion_conflicts(result)
        assert {f.title for f in resolved.findings if f.suggestion is not None} == {
            "short", "adjacent", "other"
        }
        assert result.model_dump() == before
        for original, updated in zip(result.findings, resolved.findings, strict=True):
            assert original.model_dump(exclude={"suggestion"}) == updated.model_dump(exclude={"suggestion"})
    batch = build_publication(Review(id="conflicts", head_sha="head"), result, ReviewInput())[0]
    assert len(batch["comments"]) == 5
    assert sum("```suggestion" in c["body"] for c in batch["comments"]) == 3


@pytest.mark.parametrize("severity", ["P0", "P1", "P2", "P3"])
def test_performance_severity_controls_publication(severity):
    result = ReviewResult.model_validate({"findings": [finding_data(category="performance", severity=severity)]})
    batch = build_publication(Review(id="severity", head_sha="head"), result, ReviewInput())[0]
    body = batch["body"] if severity == "P3" else batch["comments"][0]["body"]
    assert "[성능]" in body
    assert f"({severity})" in body
    assert len(batch["comments"]) == (0 if severity == "P3" else 1)

import pytest
from coday_contracts import (
    AnalyzedFile,
    DiffLine,
    ParsedHunk,
    ReviewInput,
    ReviewResult,
    ReviewSettings,
)
from coday_core.db.models import Review
from coday_pipeline.act.service import build_publication
from coday_pipeline.analyze.diff_parser import parse_patch
from coday_pipeline.analyze.file_filter import exclusion


def finding_data(**updates):
    return {
        "category": "security",
        "severity": "High",
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
    publication = build_publication(
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
    body = publication["comments"][0]["body"]
    assert all(label in body for label in ("발생 조건", "코드 근거", "수정 방향"))
    assert "`href`" in body
    assert "suggestion: null" not in body
    assert body.count("```suggestion") == (0 if suggestion is None else 1)
    if suggestion:
        assert body.count(suggestion) == 1


def test_overlapping_suggestions_keep_priority_and_preserve_findings():
    from itertools import permutations

    from coday_pipeline.suggestion_conflicts import resolve_suggestion_conflicts

    data = [
        finding_data(title="wide", severity="Medium", start_line=1, line=5, suggestion="wide"),
        finding_data(title="high", severity="High", start_line=3, line=7, suggestion="high"),
        finding_data(title="short", severity="High", start_line=4, line=4, suggestion="short"),
        finding_data(title="adjacent", severity="Medium", start_line=8, line=9, suggestion=""),
        finding_data(title="other", path="other.ts", start_line=4, line=4, suggestion="other"),
    ]
    for order in permutations(data):
        result = ReviewResult.model_validate({"findings": list(order)})
        before = result.model_dump()
        resolved = resolve_suggestion_conflicts(result)
        assert {f.title for f in resolved.findings if f.suggestion is not None} == {
            "short",
            "adjacent",
            "other",
        }
        assert result.model_dump() == before
        for original, updated in zip(result.findings, resolved.findings, strict=True):
            assert original.model_dump(exclude={"suggestion"}) == updated.model_dump(
                exclude={"suggestion"}
            )
    publication = build_publication(Review(id="conflicts", head_sha="head"), result, ReviewInput())
    assert len(publication["comments"]) == 5
    assert sum("```suggestion" in c["body"] for c in publication["comments"]) == 3


@pytest.mark.parametrize("severity", ["Critical", "High", "Medium", "Low"])
def test_every_severity_is_published_inline(severity):
    result = ReviewResult.model_validate(
        {"findings": [finding_data(category="performance", severity=severity)]}
    )
    publication = build_publication(Review(id="severity", head_sha="head"), result, ReviewInput())
    assert len(publication["comments"]) == 1
    body = publication["comments"][0]["body"]
    assert "[성능]" in body
    assert f"[{severity}]" in body
    assert f"[{severity}]" not in publication["body"]


SUMMARY_CASES = [
    ("all", (1, 2, 3, 2), 12, ()),
    ("some-zero", (0, 2, 1, 0), 5, ()),
    ("low-only", (0, 0, 0, 3), 5, ()),
    ("no-findings", (0, 0, 0, 0), 8, ()),
    ("no-reviewable-files", (0, 0, 0, 0), 0, ("uv.lock", "assets/logo.png", "dist/app.js")),
    ("findings-and-exclusions", (0, 1, 2, 1), 10, ("uv.lock", "assets/logo.png")),
    ("no-findings-with-exclusions", (0, 0, 0, 0), 8, ("uv.lock", "assets/logo.png")),
]
SEVERITIES = ("Critical", "High", "Medium", "Low")


def summary_inputs(counts, file_count, excluded_paths):
    hunks = parse_patch("@@ -0,0 +1 @@\n+const href = url;\n")
    files = [
        AnalyzedFile(file_path=f"src/links{number}.ts", status="added", hunks=hunks)
        for number in range(1, file_count + 1)
    ]
    excluded_files = {}
    patterns = ReviewSettings().exclude_patterns
    for path in excluded_paths:
        reason = exclusion(path, patterns)
        assert reason is not None
        excluded_files[path] = reason
    severities = [
        severity for severity, count in zip(SEVERITIES, counts, strict=True) for _ in range(count)
    ]
    result = ReviewResult.model_validate(
        {
            "findings": [
                finding_data(severity=severity, path=file.file_path)
                for severity, file in zip(severities, files)
            ]
        }
    )
    review = Review(id="issue-63-preview", head_sha="a1b2c3d4e5f67890")
    return review, result, ReviewInput(files=files, excluded_files=excluded_files)


@pytest.mark.parametrize(
    "counts,file_count,excluded_paths",
    [pytest.param(*case[1:], id=case[0]) for case in SUMMARY_CASES],
)
def test_review_body_states(counts, file_count, excluded_paths):
    publication = build_publication(*summary_inputs(counts, file_count, excluded_paths))
    body = publication["body"]
    assert body.startswith("## CO-DAY 리뷰\n\n분석 커밋: `a1b2c3d4e5f6`\n\n")
    assert f"분석 파일 **{file_count}개** · 제외 파일 **{len(excluded_paths)}개**" in body
    assert body.endswith("\n\n<!-- coday:review:issue-63-preview -->")
    total = sum(counts)
    assert len(publication["comments"]) == len(publication["findings"]) == total
    if total:
        rows = [
            f"| {severity} | {count} |" for severity, count in zip(SEVERITIES, counts, strict=True)
        ]
        assert (
            "\n".join(["### 📊 Review Summary", "", "| Severity | Count |", "|---|---:|", *rows])
            in body
        )
        assert f"| **Total** | **{total}** |\n\n총 {total}건" in body
        assert "인라인 리뷰 댓글을 확인해 주세요." in body
        assert finding_data()["title"] not in body
        for severity, count in zip(SEVERITIES, counts, strict=True):
            assert (
                sum(f"[{severity}]" in comment["body"] for comment in publication["comments"])
                == count
            )
    else:
        assert "Review Summary" not in body
        assert "| Severity |" not in body
        if file_count:
            assert "분석 범위에서 게시할 문제를 발견하지 못했습니다." in body
            assert "리뷰 대상 파일이 없습니다." not in body
        else:
            assert "이번 PR에는 리뷰 대상 파일이 없습니다." in body
            assert "게시할 문제를 발견하지 못했습니다." not in body
    if excluded_paths:
        assert f"<details>\n<summary>제외 파일 ({len(excluded_paths)}개)</summary>\n\n" in body
        assert body.count("\n- `") == len(excluded_paths)
        assert "\n\n</details>" in body
        for path in excluded_paths:
            assert f"- `{path}` — " in body
    else:
        assert "<details" not in body


def test_review_body_counts_only_distinct_inline_findings():
    review, result, inputs = summary_inputs((0, 1, 0, 1), 2, ())
    result.findings.append(result.findings[0].model_copy())
    publication = build_publication(review, result, inputs)
    assert len(publication["comments"]) == len(publication["findings"]) == 2
    assert "| High | 1 |" in publication["body"]
    assert "| Low | 1 |" in publication["body"]
    assert "| **Total** | **2** |" in publication["body"]


def test_excluded_file_markup_stays_literal():
    review, result, inputs = summary_inputs((0, 0, 0, 0), 1, ())
    path = "assets/`x`</details>\nlogo.png"
    reason = "제외 경로: **x** & <tag> [a](https://example.com) @user\r\n"
    inputs.excluded_files[path] = reason
    body = build_publication(review, result, inputs)["body"]
    assert r"- ``assets/`x`</details>\nlogo.png`` — " in body
    assert "&#42;&#42;x&#42;&#42; &#38; &#60;tag&#62;" in body
    assert "&#91;a&#93;&#40;https&#58;" in body
    assert "&#64;\u200buser&#92;r&#92;n" in body
    assert body.count("\n</details>") == 1
    assert "<details open" not in body

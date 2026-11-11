from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from coday_contracts.review_input import ReviewInput
from coday_contracts.review_result import ReviewResult
from coday_core.db.models import Review
from coday_pipeline.act import service
from coday_pipeline.act.markdown import escape_prose_tildes
from coday_pipeline.act.service import build_publication

# GitHub에서 읽기 전용으로 확인한 실제 댓글의 evidence.
# https://github.com/choyekyo/PR-BOT-TEST/pull/1#discussion_r4366577870
# body_html은 65<del>67행 ... 이후 44</del>49행으로 렌더링되어 있었다.
DISPOSE_EVIDENCE = (
    "dispose는 65~67행에서 타이머와 캐시만 정리합니다. 진행 중인 search는 이후 "
    "44~49행의 성공 또는 실패 경로에서 onChange를 계속 호출하므로 64행의 알림 방지 계약을 위반합니다."
)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("65~67행과 44~49행", r"65\~67행과 44\~49행"),
        ("~~문장~~", r"\~\~문장\~\~"),
        ("65~67행\n44~49행", "65\\~67행\n44\\~49행"),
        ("`~mask`와 `~~value`", "`~mask`와 `~~value`"),
        ("``a`~b``와 65~67행", "``a`~b``와 65\\~67행"),
        ("`a\n~b`와 44~49행", "`a\n~b`와 44\\~49행"),
        (r"65\~67행과 44\~49행", r"65\~67행과 44\~49행"),
        (r"\\~text~", r"\\\~text\~"),
        (r"\`65~67행과 44~49행", r"\`65\~67행과 44\~49행"),
        ("`닫히지 않음 65~67행과 44~49행", "`닫히지 않음 65\\~67행과 44\\~49행"),
    ],
)
def test_escape_tildes_preserves_code_and_existing_escapes(source, expected):
    assert escape_prose_tildes(source) == expected
    assert escape_prose_tildes(expected) == expected


@pytest.mark.parametrize("severity", ["P0", "P1", "P2", "P3"])
@pytest.mark.parametrize("field", ["title", "condition", "evidence", "recommendation"])
def test_publication_preserves_suggestion_and_escapes_prose(severity, field):
    explanation = DISPOSE_EVIDENCE + "\n~~설명~~ `~mask`와 ``a`~b``"
    code = '    const mask = ~~value;\n    const range = "65~67행과 44~49행";'
    data = {
        "category": "bug",
        "severity": severity,
        "title": "dispose 문제",
        "condition": "검색 중 dispose 호출",
        "evidence": DISPOSE_EVIDENCE,
        "recommendation": "폐기 상태를 확인하세요.",
        "path": "prBotAsyncReviewFixture.ts",
        "line": 68,
        "side": "RIGHT",
        "start_line": 64,
        "suggestion": code,
    }
    data[field] = explanation
    result = ReviewResult.model_validate({"findings": [data]})
    batch = build_publication(
        Review(id="markdown-test", head_sha="head"),
        result,
        ReviewInput(),
    )[0]
    if severity == "P3":
        assert batch["comments"] == []
        body = batch["body"]
        assert "```suggestion" not in body
    else:
        assert len(batch["comments"]) == 1
        comment = batch["comments"][0]
        assert (comment["line"], comment["start_line"], comment["side"]) == (68, 64, "RIGHT")
        body = comment["body"]
        assert f"```suggestion\n{code}\n```" in body
    assert escape_prose_tildes(explanation) in body
    assert r"65\~67행" in body and r"44\~49행" in body
    assert "`~mask`와 ``a`~b``" in body
    assert result.findings[0].model_dump() == data


@pytest.mark.parametrize("severity", ["P0", "P1", "P2", "P3"])
async def test_act_sends_escaped_body_to_github_without_network(monkeypatch, severity):
    result = ReviewResult.model_validate(
        {
            "findings": [
                {
                    "category": "bug",
                    "severity": severity,
                    "title": "dispose 문제",
                    "condition": "검색 중 dispose 호출",
                    "evidence": DISPOSE_EVIDENCE,
                    "recommendation": "`~mask`를 유지하고 ~~설명~~을 확인하세요.",
                    "path": "prBotAsyncReviewFixture.ts",
                    "line": 68,
                    "side": "RIGHT",
                    "start_line": 64,
                    "suggestion": "    const mask = ~~value;",
                }
            ]
        }
    )
    review = Review(
        id="markdown-test",
        repository_id=1,
        pr_number=1,
        head_sha="head",
        publication=None,
        result=result.model_dump(),
        input=ReviewInput().model_dump(),
    )

    @contextmanager
    def transaction():
        yield SimpleNamespace(get=lambda *args: review, scalars=lambda *args: [])

    monkeypatch.setattr(service, "transaction", transaction)
    recorded = Mock()
    monkeypatch.setattr(service, "record_publication", recorded)
    github = SimpleNamespace(
        pages=AsyncMock(return_value=[]),
        request=AsyncMock(return_value={"id": 123}),
        settings=SimpleNamespace(bot_login="test[bot]"),
    )
    await service.act(github, "test-token", "owner/test", review.id, AsyncMock())
    args, kwargs = github.request.call_args
    assert args[1:] == ("POST", "/repos/owner/test/pulls/1/reviews")
    payload = kwargs["data"]
    body = payload["body"] if severity == "P3" else payload["comments"][0]["body"]
    assert escape_prose_tildes(DISPOSE_EVIDENCE) in body
    assert r"`~mask`를 유지하고 \~\~설명\~\~" in body
    if severity == "P3":
        assert payload["comments"] == []
    else:
        assert "```suggestion\n    const mask = ~~value;\n```" in body
    recorded.assert_called_once_with(review.id, 0, 123)

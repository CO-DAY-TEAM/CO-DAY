import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from coday_contracts import ReviewResult
from coday_contracts.review_input import FunctionContext


@pytest.fixture
def agent(monkeypatch, tmp_path):
    path = Path(__file__).resolve().parents[1] / "evals/reviewbench/agent.py"
    spec = importlib.util.spec_from_file_location("reviewbench_eval", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    monkeypatch.setenv("RB_BASE", "base")
    monkeypatch.setenv("RB_HEAD", "head")
    monkeypatch.setenv("RB_REPO", str(tmp_path))
    monkeypatch.setenv("RB_PR_JSON", str(tmp_path / "pr.json"))
    monkeypatch.setenv("RB_OUT", str(tmp_path / "findings.json"))
    monkeypatch.setenv("RB_CONFIG_MODEL", "test-model")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(module, "AsyncOpenAI", lambda **kwargs: SimpleNamespace(close=AsyncMock()))
    monkeypatch.setattr(module, "set_default_openai_client", lambda *args, **kwargs: None)
    monkeypatch.setattr(module, "set_tracing_disabled", lambda *args: None)
    monkeypatch.setattr(module, "judge", AsyncMock(return_value=ReviewResult()))
    return module


@pytest.mark.parametrize(
    "metadata",
    [
        {"title": "한글🙂" * 200, "body": "## 변경 목적\n\n" + "- 한글 🧑‍💻\n" * 5000},
        {},
        {"title": None, "body": None},
    ],
    ids=["markdown", "missing", "null"],
)
async def test_reviewbench_passes_pr_context_to_shared_judge(
    agent, monkeypatch, tmp_path, metadata
):
    pr = {"repo": "https://github.com/example/repo", "pr_number": 1, "base": "base", "head": "head"}
    (tmp_path / "pr.json").write_text(
        json.dumps(
            {**pr, **metadata, "expected_findings": ["reference-only"], "score": "grading-only"},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    function = FunctionContext(path="helper.py", head_sha="head", start_line=1, end_line=2)

    def related_files(*args, function_context, **kwargs):
        function_context.append(function)
        return {"helper.py": "x = 1"}

    def git(repo, command, *args):
        return b"@@ -0,0 +1 @@\n+x = 1\n" if command == "diff" else b"x = 1\n"

    monkeypatch.setattr(agent, "changed_files", lambda *args: [("A", "a.py", "a.py")])
    monkeypatch.setattr(agent, "related_files", related_files)
    monkeypatch.setattr(agent, "git", git)

    await agent.review()

    agent.judge.assert_awaited_once()
    inputs, instructions, settings, _ = agent.judge.call_args.args
    assert instructions == ""
    assert settings.openai_model == "test-model"
    assert [file.file_path for file in inputs.files] == ["a.py"]
    assert inputs.files[0].hunks[0].lines[0].content == "x = 1"
    assert inputs.related_files == {"helper.py": "x = 1"}
    assert inputs.function_context == [function]
    assert inputs.pr_title == (metadata.get("title") or "")[:512]
    assert inputs.pr_body == (metadata.get("body") or "")
    serialized_inputs = inputs.model_dump_json()
    assert "reference-only" not in serialized_inputs
    assert "grading-only" not in serialized_inputs


async def test_reviewbench_skips_judge_without_changed_files(agent, monkeypatch, tmp_path):
    pr = {"repo": "https://github.com/example/repo", "pr_number": 1, "base": "base", "head": "head"}
    (tmp_path / "pr.json").write_text(
        json.dumps({**pr, "title": "문맥", "body": "본문"}), encoding="utf-8"
    )
    monkeypatch.setattr(agent, "changed_files", lambda *args: [])
    monkeypatch.setattr(agent, "related_files", lambda *args, **kwargs: {})

    await agent.review()

    agent.judge.assert_not_awaited()
    result = json.loads((tmp_path / "findings.json").read_text(encoding="utf-8"))
    assert result["findings"] == []

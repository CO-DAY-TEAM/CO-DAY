from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from coday_contracts import ReviewJob, ReviewSettings
from coday_core.config import Settings
from coday_pipeline.analyze.collector import collect
from coday_pipeline.analyze.imports import (
    eligible_context,
    import_priorities,
    related_candidates,
)


def test_js_import_bindings_and_fallback_priority():
    source = """
import { check as validate } from "../auth/token.js";
import type { User } from "../types";
import { unused } from "../other";
import React from "react";
import { alias } from "@/alias";
// import { fake } from "../fake";
const example = "import { fake } from '../fake'";
validate(value);
"""
    paths = {"auth/token.ts", "types/index.ts", "other.ts", "fake.ts", "alias.ts"}
    ranks = import_priorities("routes/page.ts", source, "+validate(value);", paths)
    assert ranks == {"auth/token.ts": 0, "types/index.ts": 1, "other.ts": 1}
    ordered = related_candidates(
        {"routes/page.ts"}, paths | {"routes/sibling.ts", "page.test.ts"}, ranks
    )
    assert ordered == [
        "auth/token.ts",
        "other.ts",
        "types/index.ts",
        "page.test.ts",
        "routes/sibling.ts",
    ]


def test_js_multiline_namespace_require_and_ambiguous_paths():
    source = """
import {
  value,
} from "./values";
import * as ns from "./namespace";
import "./setup";
const x = require("./common.cjs");
const later = import("./dynamic");
object.require("./fake");
"""
    paths = {
        "src/values.ts",
        "src/values.js",
        "src/namespace.ts",
        "src/setup.js",
        "src/common.cts",
        "src/dynamic.ts",
        "src/fake.ts",
    }
    assert import_priorities("src/main.ts", source, "+ns.run();", paths) == {
        "src/namespace.ts": 0,
        "src/setup.js": 1,
        "src/common.cts": 1,
    }


def test_python_absolute_relative_and_src_package_imports():
    paths = {
        "src/app/__init__.py",
        "src/app/routes/__init__.py",
        "src/app/routes/page.py",
        "src/app/auth/__init__.py",
        "src/app/auth/tokens.py",
        "src/app/routes/local.py",
    }
    source = """
from ..auth.tokens import check as validate
from . import local
from app.auth import tokens
import app.auth.tokens as auth
import external_library
"""
    assert import_priorities("src/app/routes/page.py", source, "+validate(value)", paths) == {
        "src/app/auth/tokens.py": 0,
        "src/app/routes/local.py": 1,
    }


def test_invalid_sources_external_aliases_and_path_escape_are_ignored():
    paths = {"secret.ts", "app/tokens.py"}
    assert import_priorities("src/page.ts", 'import x from "../../secret";', "+x()", paths) == {}
    assert import_priorities("app/page.py", "from .tokens import (", "+x()", paths) == {}
    assert import_priorities("src/readme.md", 'import x from "../secret";', "+x()", paths) == {}
    assert import_priorities("app/page.py", "from ...tokens import check", "+check()", paths) == {}


def test_context_filters_still_apply_to_imported_files():
    assert not eligible_context("src/generated.ts", "100644", 10, 100, ["**/generated.ts"])
    assert not eligible_context("AGENTS.md", "100644", 10, 100, [])
    assert not eligible_context("src/link.ts", "120000", 10, 100, [])
    assert not eligible_context("src/large.ts", "100644", 101, 100, [])
    assert related_candidates({"src/main.ts"}, {"src/main.ts"}, {"src/main.ts": 0}) == []


@pytest.mark.parametrize("related_count", [0, 1])
async def test_collector_reads_head_imports_and_keeps_limits(related_count):
    source = 'import { validate } from "../auth/tokens";\nvalidate(value);\n'
    patch = (
        '@@ -1,2 +1,2 @@\n import { validate } from "../auth/tokens";\n-old();\n+validate(value);'
    )
    tree = [
        {"path": "src/page.ts", "type": "blob", "mode": "100644", "size": len(source)},
        {"path": "auth/tokens.ts", "type": "blob", "mode": "100644", "size": 20},
        {"path": "src/page.test.ts", "type": "blob", "mode": "100644", "size": 20},
    ]

    async def request(*args, **kwargs):
        return {"tree": tree} if "/git/trees/" in args[2] else {"changed_files": 1}

    async def file(token, repo, path, sha):
        assert sha == "head"
        return source.encode() if path == "src/page.ts" else b"export const validate = () => true;"

    github = SimpleNamespace(
        settings=Settings(_env_file=None, related_file_count=related_count),
        request=AsyncMock(side_effect=request),
        file=AsyncMock(side_effect=file),
        pages=AsyncMock(
            return_value=[
                {
                    "filename": "src/page.ts",
                    "status": "modified",
                    "changes": 2,
                    "additions": 1,
                    "deletions": 1,
                    "patch": patch,
                }
            ]
        ),
    )
    result = await collect(
        ReviewJob(owner="o", repo="r", pr_number=1, head_sha="head"),
        ReviewSettings(),
        github,
        "token",
        AsyncMock(),
    )
    assert list(result.related_files) == (["auth/tokens.ts"] if related_count else [])
    assert github.file.await_count == (2 if related_count else 0)


def test_reviewbench_uses_head_imports_and_the_same_candidate_limit(monkeypatch):
    import importlib.util
    from pathlib import Path

    root = next(
        p for p in Path(__file__).resolve().parents if (p / "evals/reviewbench/agent.py").exists()
    )
    spec = importlib.util.spec_from_file_location(
        "import_ranking_eval", root / "evals/reviewbench/agent.py"
    )
    agent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(agent)
    source = b'import { validate } from "../auth/tokens";\nvalidate(value);\n'
    patch = (
        b'@@ -1,2 +1,2 @@\n import { validate } from "../auth/tokens";\n-old();\n+validate(value);'
    )
    tree = (
        b"\0".join(
            [
                b"100644 blob main 65\tsrc/page.ts",
                b"100644 blob dependency 20\tauth/tokens.ts",
                b"100644 blob test 20\tsrc/page.test.ts",
            ]
        )
        + b"\0"
    )

    def git(repo, *args):
        if args[0] == "ls-tree":
            return tree
        if args[0] == "diff":
            assert "base...head" in args
            return patch
        if args == ("cat-file", "blob", "main"):
            return source
        if args == ("cat-file", "blob", "dependency"):
            return b"export const validate = () => true;"
        raise AssertionError(args)

    monkeypatch.setattr(agent, "git", git)
    settings = Settings(_env_file=None, related_file_count=1)
    result = agent.related_files(
        Path("unused"), "head", [("M", "src/page.ts", "src/page.ts")], settings, [], base="base"
    )
    assert result == {"auth/tokens.ts": "export const validate = () => true;"}

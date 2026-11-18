from types import SimpleNamespace
from unittest.mock import AsyncMock

from coday_contracts import ReviewJob, ReviewSettings
from coday_core.config import Settings
from coday_pipeline.analyze.collector import collect
from coday_pipeline.analyze.configuration import configuration_priorities

REPO = "https://github.com/example/service"
PATHS = {
    "deploy/chart/Chart.yaml",
    "deploy/chart/values.yaml",
    "deploy/chart/templates/deployment.yaml",
    "deploy/chart/templates/service.yaml",
    "unrelated/Chart.yaml",
    "unrelated/values.yaml",
    "unrelated/templates/deployment.yaml",
}


def test_local_chart_edits_include_consumers_and_defaults_but_not_other_charts():
    assert configuration_priorities({"deploy/chart/values.yaml"}, {}, PATHS, REPO) == {
        "deploy/chart/templates/deployment.yaml": 0,
        "deploy/chart/templates/service.yaml": 0,
        "deploy/chart/values.yaml": 1,
    }
    assert configuration_priorities({"deploy/chart/README.md"}, {}, PATHS, REPO) == {}


def test_application_explicit_external_values_path_can_match_deleted_file():
    source = f"""
kind: Application
spec:
  source:
    repoURL: {REPO}.git
    path: deploy/chart
    helm:
      valueFiles: [../../overrides/service.yaml]
"""
    changed = {"applications.yaml", "overrides/service.yaml"}
    assert "deploy/chart/templates/deployment.yaml" in configuration_priorities(
        changed, {"applications.yaml": source}, PATHS, REPO
    )
    assert (
        configuration_priorities(
            {"applications.yaml", "other.yaml"}, {"applications.yaml": source}, PATHS, REPO
        )
        == {}
    )
    assert (
        configuration_priorities(
            changed,
            {"applications.yaml": source.replace(REPO, "https://github.com/other/repo")},
            PATHS,
            REPO,
        )
        == {}
    )


def application_set():
    return f"""
kind: ApplicationSet
spec:
  generators:
    - git:
        repoURL: {REPO}.git
        directories:
          - path: overrides/*
  template:
    spec:
      source:
        repoURL: {REPO}.git
        path: deploy/chart
        helm:
          valueFiles:
            - '../../overrides/{{{{.path.basename}}}}/values.yaml'
"""


def test_directory_generator_matches_exact_local_binding_and_rejects_guesses():
    source = application_set()
    changes = {"applications.yaml", "overrides/payments/values.yaml"}
    sources = {"applications.yaml": source}
    assert "deploy/chart/templates/service.yaml" in configuration_priorities(
        changes, sources, PATHS, REPO
    )
    for changed in ["overrides/payments/nested/values.yaml", "elsewhere/payments/values.yaml"]:
        assert configuration_priorities({changed}, sources, PATHS, REPO) == {}
    for modified in [
        source.replace(".path.basename", ".unsupported"),
        source.replace("- path: overrides/*", "- path: overrides/*\n            exclude: true"),
        source.replace(
            "repoURL: " + REPO + ".git", "repoURL: https://github.com/foreign/chart.git", 1
        ),
    ]:
        assert configuration_priorities(changes, {"applications.yaml": modified}, PATHS, REPO) == {}


def test_root_chart_and_untrusted_malformed_yaml():
    paths = {"Chart.yaml", "values.yaml", "templates/service.yaml"}
    assert configuration_priorities({"values.yaml"}, {}, paths, REPO) == {
        "templates/service.yaml": 0,
        "values.yaml": 1,
    }
    for source in ["kind: [invalid", "!!python/object/apply:os.system ['echo unsafe']", "[]"]:
        assert (
            configuration_priorities(
                {"applications.yaml"}, {"applications.yaml": source}, paths, REPO
            )
            == {}
        )


async def test_collector_skips_candidates_that_do_not_fit_and_fills_with_smaller_file():
    source = "export const page = 1;\n"
    patch = "@@ -1 +1 @@\n-old();\n+page();"
    calls = []
    tree = [
        {"path": "src/page.ts", "type": "blob", "size": len(source)},
        {"path": "src/page-a.ts", "type": "blob", "size": 990},
        {"path": "src/page-b.ts", "type": "blob", "size": 20},
        {"path": "src/page-empty.ts", "type": "blob", "size": 0},
    ]

    async def request(*args, **kwargs):
        return {"tree": tree} if "/git/trees/" in args[2] else {"changed_files": 1}

    async def file(token, repo, path, sha):
        calls.append(path)
        assert sha == "head"
        return source.encode() if path == "src/page.ts" else b"export const x = 1;\n"

    github = SimpleNamespace(
        settings=Settings(_env_file=None, max_input_bytes=1000, related_file_count=2),
        request=AsyncMock(side_effect=request),
        file=AsyncMock(side_effect=file),
        pages=AsyncMock(
            return_value=[
                dict(
                    filename="src/page.ts",
                    status="modified",
                    changes=2,
                    additions=1,
                    deletions=1,
                    patch=patch,
                )
            ]
        ),
    )
    result = await collect(
        ReviewJob(owner="example", repo="service", pr_number=1, head_sha="head"),
        ReviewSettings(),
        github,
        "token",
        AsyncMock(),
    )
    assert list(result.related_files) == ["src/page-b.ts"]
    assert "src/page-a.ts" not in calls and "src/page-empty.ts" not in calls
    assert len(patch.encode()) + sum(len(s.encode()) for s in result.related_files.values()) <= 1000


async def test_production_and_adapter_select_same_explicit_chart_context(monkeypatch):
    import importlib.util
    from pathlib import Path

    root = next(
        p for p in Path(__file__).resolve().parents if (p / "evals/reviewbench/agent.py").exists()
    )
    spec = importlib.util.spec_from_file_location(
        "configuration_eval", root / "evals/reviewbench/agent.py"
    )
    agent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(agent)
    source = application_set()
    values = "service:\n  port: 1234\n"
    changes = [
        dict(
            filename="applications.yaml",
            status="modified",
            changes=2,
            additions=1,
            deletions=1,
            patch="@@ -1 +1 @@\n-old\n+new",
        ),
        dict(
            filename="overrides/payments/values.yaml",
            status="removed",
            changes=2,
            additions=0,
            deletions=2,
            patch="@@ -1,2 +0,0 @@\n-service:\n-  port: 1234",
        ),
    ]
    content = {p: "kind: Deployment\n" for p in PATHS}
    content["applications.yaml"] = source
    content["deploy/chart/values.yaml"] = values
    content["deploy/chart/Chart.yaml"] = "apiVersion: v2\n"
    tree = [
        dict(path=p, type="blob", mode="100644", size=len(s.encode())) for p, s in content.items()
    ]
    patches = {f["filename"]: f["patch"] for f in changes}

    async def request(*args, **kwargs):
        return {"tree": tree} if "/git/trees/" in args[2] else {"changed_files": 2}

    async def file(token, repo, path, sha):
        assert sha == "head"
        return content[path].encode()

    settings = Settings(_env_file=None, related_file_count=2)
    github = SimpleNamespace(
        settings=settings,
        request=AsyncMock(side_effect=request),
        file=AsyncMock(side_effect=file),
        pages=AsyncMock(return_value=changes),
    )
    result = await collect(
        ReviewJob(owner="example", repo="service", pr_number=1, head_sha="head"),
        ReviewSettings(),
        github,
        "token",
        AsyncMock(),
    )

    def git(repo, *args):
        if args[0] == "ls-tree":
            return (
                b"\0".join(
                    f"100644 blob {p} {len(s.encode())}\t{p}".encode() for p, s in content.items()
                )
                + b"\0"
            )
        if args[0] == "diff":
            return patches[args[-1]].encode()
        if args[:2] == ("cat-file", "blob"):
            return content[args[2]].encode()
        raise AssertionError(args)

    monkeypatch.setattr(agent, "git", git)
    actual = agent.related_files(
        Path("unused"),
        "head",
        [
            ("M", "applications.yaml", "applications.yaml"),
            ("D", "overrides/payments/values.yaml", "overrides/payments/values.yaml"),
        ],
        settings,
        [],
        base="base",
        repository=REPO,
    )
    assert result.related_files == actual
    assert list(actual) == [
        "deploy/chart/templates/deployment.yaml",
        "deploy/chart/templates/service.yaml",
    ]

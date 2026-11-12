"""Resolve explicit local Helm configuration consumers without rendering templates."""

import posixpath
import re
from fnmatch import fnmatchcase
from itertools import islice
from pathlib import PurePosixPath

import yaml

CONFIG_SUFFIXES = {".yaml", ".yml"}


def patch_source(patch: str, side: str) -> str:
    """Visible old/new YAML only; incomplete hunks are not a full-file substitute."""
    prefix = "-" if side == "old" else "+"
    return "\n".join(
        line[1:]
        for line in patch.splitlines()
        if line.startswith((prefix, " ")) and not line.startswith(("---", "+++"))
    )


def _mapping(value):
    return value if isinstance(value, dict) else {}


def _local(base: str, value) -> str | None:
    if not isinstance(value, str) or not value or re.search(r"[\\$:{}\x00]", value):
        return None
    if value.startswith("/"):
        return None
    path = posixpath.normpath(posixpath.join(base, value))
    return None if path in {".", ".."} or path.startswith("../") else path


def _same_repo(value, repository: str) -> bool:
    def normalize(url):
        if not isinstance(url, str):
            return None
        if url.startswith("git@github.com:"):
            url = "https://github.com/" + url[len("git@github.com:") :]
        return url.rstrip("/").removesuffix(".git")

    return bool(repository) and normalize(value) == normalize(repository)


def _directory_match(path: str, pattern: str) -> bool:
    parts, glob = path.split("/"), pattern.split("/")
    return (
        not pattern.startswith("/")
        and ".." not in glob
        and "**" not in glob
        and len(parts) == len(glob)
        and all(fnmatchcase(part, rule) for part, rule in zip(parts, glob))
    )


def _documents(source: str):
    try:
        return list(islice(yaml.safe_load_all(source), 32))
    except (yaml.YAMLError, RecursionError, ValueError):
        return []


def configuration_priorities(
    changed: set[str], sources: dict[str, str], paths: set[str], repository: str
) -> dict[str, int]:
    """0: explicit chart consumers; 1: defaults. No filename-only chart inference.

    Support local chart edits and Argo Application/ApplicationSet directory generators
    whose valueFiles explicitly resolve to a changed file, including a deleted override.
    External repos, $values/multi-repo references and unknown template variables are skipped.
    """
    charts = {
        "" if str(PurePosixPath(p).parent) == "." else str(PurePosixPath(p).parent)
        for p in paths
        if PurePosixPath(p).name == "Chart.yaml"
    }
    linked = set()
    for chart in charts:
        for path in changed:
            if path in {
                posixpath.join(chart, "values.yaml"),
                posixpath.join(chart, "Chart.yaml"),
            } or path.startswith(posixpath.join(chart, "templates") + "/"):
                linked.add(chart)
    for filename, source in sources.items():
        if PurePosixPath(filename).suffix not in CONFIG_SUFFIXES:
            continue
        for document in _documents(source):
            doc = _mapping(document)
            spec = _mapping(doc.get("spec"))
            if doc.get("kind") == "Application":
                configurations = [(spec, [{}])]
            elif doc.get("kind") == "ApplicationSet":
                configurations = []
                generators = spec.get("generators", [])
                if not isinstance(generators, list):
                    continue
                bindings = []
                for generator in generators:
                    git = _mapping(_mapping(generator).get("git"))
                    if not _same_repo(git.get("repoURL"), repository):
                        continue
                    directories = git.get("directories", [])
                    if not isinstance(directories, list):
                        continue
                    # Exclusions require full generator semantics; skip rather than guess.
                    if any(_mapping(d).get("exclude") for d in directories):
                        continue
                    for item in directories:
                        pattern = _mapping(item).get("path")
                        if not isinstance(pattern, str):
                            continue
                        for path in changed:
                            parent = str(PurePosixPath(path).parent)
                            if _directory_match(parent, pattern):
                                bindings.append(
                                    {
                                        ".path.basename": PurePosixPath(parent).name,
                                        ".path.path": parent,
                                    }
                                )
                configurations.append(
                    (_mapping(_mapping(spec.get("template")).get("spec")), bindings)
                )
            else:
                continue
            for config, bindings in configurations:
                origin = _mapping(config.get("source"))
                if not _same_repo(origin.get("repoURL"), repository):
                    continue
                chart = "" if origin.get("path") == "." else _local("", origin.get("path"))
                if chart not in charts:
                    continue
                values = _mapping(origin.get("helm")).get("valueFiles", [])
                if not isinstance(values, list):
                    continue
                for value in values:
                    if not isinstance(value, str):
                        continue
                    for binding in bindings:
                        resolved = re.sub(
                            r"{{\s*([.\w]+)\s*}}",
                            lambda match: binding.get(match[1], match[0]),
                            value,
                        )
                        if _local(chart, resolved) in changed:
                            linked.add(chart)
    priorities = {}
    for chart in sorted(linked):
        for path in paths:
            if path.startswith(posixpath.join(chart, "templates") + "/"):
                priorities[path] = 0
        defaults = posixpath.join(chart, "values.yaml")
        if defaults in paths:
            priorities[defaults] = 1
    return priorities

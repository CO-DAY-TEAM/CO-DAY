"""Resolve explicitly configured local paths without executing build configs.

Only the nearest tsconfig/jsconfig, repository-local baseUrl, and unambiguous
single-target paths mappings are supported. Inherited configurations are skipped.
"""

import json
import posixpath
import re
from pathlib import PurePosixPath

_JSON_TOKENS = re.compile(
    r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*[\s\S]*?\*/|\s+'
    r"|true|false|null|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|.",
    re.DOTALL,
)


def nearest_config(path: str, paths: set[str]) -> str | None:
    for parent in PurePosixPath(path).parents:
        for name in ("tsconfig.json", "jsconfig.json"):
            candidate = (parent / name).as_posix()
            if candidate in paths:
                return candidate
    return None


def config_candidates(changed: set[str], paths: set[str]) -> list[str]:
    return sorted({c for p in changed if (c := nearest_config(p, paths))})


def parse_config(path: str, source: str) -> dict:
    # JSONC comments/trailing commas are removed as tokens, never inside strings.
    tokens = [
        m.group()
        for m in _JSON_TOKENS.finditer(source)
        if not m.group().isspace() and not m.group().startswith(("//", "/*"))
    ]
    cleaned = " ".join(
        t
        for i, t in enumerate(tokens)
        if not (t == "," and i + 1 < len(tokens) and tokens[i + 1] in {"}", "]"})
    )
    data = json.loads(cleaned)
    if not isinstance(data, dict) or "extends" in data:
        raise ValueError("unsupported_config_inheritance_or_shape")
    options = data.get("compilerOptions", {})
    if not isinstance(options, dict):
        raise ValueError("invalid_compiler_options")
    base = options.get("baseUrl", ".")
    mappings = options.get("paths", {})
    if not isinstance(base, str) or not isinstance(mappings, dict):
        raise ValueError("invalid_paths_config")
    root = _local_path(str(PurePosixPath(path).parent), base)
    if root is None:
        raise ValueError("base_url_outside_repository")
    return dict(root=root, paths=mappings)


def _local_path(root: str, target: str) -> str | None:
    if target.startswith("/") or "\\" in target or ":" in target:
        return None
    result = posixpath.normpath(posixpath.join(root, target))
    return None if result == ".." or result.startswith("../") else result


def alias_target(importer: str, module: str, paths: set[str], configs: dict) -> str | None:
    config = configs.get(nearest_config(importer, paths))
    if config is None:
        return None
    mappings = config["paths"]
    if module in mappings:
        pattern, captured = module, ""
    else:
        matches = []
        for key in mappings:
            if not isinstance(key, str) or key.count("*") != 1:
                continue
            prefix, suffix = key.split("*")
            if (
                module.startswith(prefix)
                and module.endswith(suffix)
                and len(module) >= len(prefix) + len(suffix)
            ):
                matches.append(
                    (
                        len(prefix),
                        key,
                        module[len(prefix) : len(module) - len(suffix) if suffix else None],
                    )
                )
        if not matches:
            return None
        # TypeScript prefers the pattern with the longest prefix. Equal best
        # matches are left unresolved rather than guessing between mappings.
        best = max(m[0] for m in matches)
        selected = [m for m in matches if m[0] == best]
        if len(selected) != 1:
            return None
        _, pattern, captured = selected[0]
    targets = mappings[pattern]
    if (
        not isinstance(targets, list)
        or len(targets) != 1
        or not isinstance(targets[0], str)
        or targets[0].count("*") > 1
        or ("*" in targets[0] and "*" not in pattern)
        or any(part in {".", ".."} for part in captured.split("/"))
    ):
        return None
    return _local_path(config["root"], targets[0].replace("*", captured))


def configured_alias(importer: str, module: str, paths: set[str], configs: dict) -> bool:
    config = configs.get(nearest_config(importer, paths))
    if config is None:
        return False
    for pattern in config["paths"]:
        if not isinstance(pattern, str):
            continue
        if pattern == module:
            return True
        if pattern.count("*") == 1:
            prefix, suffix = pattern.split("*")
            if module.startswith(prefix) and module.endswith(suffix):
                return True
    return False

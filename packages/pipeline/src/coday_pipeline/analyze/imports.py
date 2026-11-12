"""Resolve direct local imports against PR HEAD paths; never execute project code."""

import ast
import posixpath
import re
from pathlib import PurePosixPath

from coday_pipeline.analyze.file_filter import exclusion

SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts"}
# Skip comments and strings as whole tokens, so examples in prose are not imports.
JS_TOKENS = re.compile(
    r"//[^\n]*|/\*[\s\S]*?\*/|`(?:\\[\s\S]|[^`\\])*`"
    r'|"(?:\\[\s\S]|[^"\\])*"|\'(?:\\[\s\S]|[^\'\\])*\''
    r"|[A-Za-z_$][\w$]*|[^\s]"
)


def eligible_context(path: str, mode: str, size: int, limit: int, patterns: list[str]) -> bool:
    return (
        mode in {"100644", "100755"}
        and 0 < size <= limit
        and not exclusion(path, patterns)
        and PurePosixPath(path).name.upper() not in {"AGENTS.MD", "CLAUDE.MD", "GEMINI.MD"}
    )


def _js_imports(source: str):
    tokens = [
        m.group() for m in JS_TOKENS.finditer(source) if not m.group().startswith(("//", "/*", "`"))
    ]
    for i, token in enumerate(tokens):
        if i and tokens[i - 1] in {".", "?."}:
            continue
        if token == "require" and tokens[i + 1 : i + 2] == ["("]:
            tail = tokens[i + 2 : i + 4]
            if len(tail) == 2 and tail[1] == ")" and tail[0].startswith(("'", '"')):
                # CommonJS bindings are optional; the dependency is still explicit.
                yield tail[0][1:-1], set()
        if token != "import" or i + 1 >= len(tokens) or tokens[i + 1] in {"(", "."}:
            continue  # Dynamic import and import.meta are intentionally unsupported.
        if tokens[i + 1].startswith(("'", '"')):
            yield tokens[i + 1][1:-1], set()
            continue
        names = set()
        for j in range(i + 1, min(len(tokens), i + 256)):
            value = tokens[j]
            if value in {";", "import", "export"}:
                break
            if value == "from":
                if j + 1 < len(tokens) and tokens[j + 1].startswith(("'", '"')):
                    yield tokens[j + 1][1:-1], names
                break
            if re.fullmatch(r"[A-Za-z_$][\w$]*", value) and value not in {"type", "as"}:
                names.add(value)


def _js_path(path: str, module: str, paths: set[str]) -> str | None:
    if not module.startswith(("./", "../")) or "\\" in module:
        return None
    target = posixpath.normpath(posixpath.join(posixpath.dirname(path), module))
    if target.startswith("../") or target.startswith("/"):
        return None
    if target in paths:
        return target
    suffix = PurePosixPath(target).suffix
    replacements = {".js": (".ts", ".tsx"), ".jsx": (".tsx",), ".mjs": (".mts",), ".cjs": (".cts",)}
    if suffix in replacements:
        candidates = [target[: -len(suffix)] + ext for ext in replacements[suffix]]
    elif not suffix:
        extensions = (".ts", ".tsx", ".js", ".jsx", ".mts", ".cts", ".mjs", ".cjs")
        candidates = [target + ext for ext in extensions]
        candidates += [target + "/index" + ext for ext in extensions]
    else:
        return None
    found = [candidate for candidate in candidates if candidate in paths]
    return found[0] if len(found) == 1 else None  # Do not guess ambiguous resolution.


def _python_roots(path: str, paths: set[str]) -> set[str]:
    roots = {""}
    parent = PurePosixPath(path).parent
    while str(parent) != "." and (parent / "__init__.py").as_posix() in paths:
        parent = parent.parent
    if str(parent) != ".":
        # Only establish a package root through actual __init__.py ancestors.
        if parent != PurePosixPath(path).parent:
            roots.add(parent.as_posix())
    return roots


def _python_module(module: str, roots: set[str], paths: set[str]) -> str | None:
    found = set()
    for root in roots:
        target = posixpath.join(root, module.replace(".", "/"))
        found.update(p for p in (target + ".py", target + "/__init__.py") if p in paths)
    return next(iter(found)) if len(found) == 1 else None


def _python_imports(path: str, source: str, paths: set[str]):
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return
    roots = _python_roots(path, paths)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = _python_module(alias.name, roots, paths)
                if target:
                    yield target, {alias.asname or alias.name.split(".")[0]}
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                package = PurePosixPath(path).parent
                for level in range(node.level):
                    if (package / "__init__.py").as_posix() not in paths:
                        break
                    if level < node.level - 1:
                        package = package.parent
                else:
                    local_roots = {"" if str(package.parent) == "." else package.parent.as_posix()}
                    module = ".".join([package.name, node.module or ""]).strip(".")
                    base = _python_module(module, local_roots, paths)
                    for alias in node.names:
                        target = _python_module(module + "." + alias.name, local_roots, paths)
                        if target or base:
                            yield target or base, {alias.asname or alias.name}
                continue
            local_roots, module = roots, node.module or ""
            base = _python_module(module, local_roots, paths)
            for alias in node.names:
                target = _python_module(module + "." + alias.name, local_roots, paths)
                if target or base:
                    yield target or base, {alias.asname or alias.name}


def import_priorities(path: str, source: str, patch: str, paths: set[str]) -> dict[str, int]:
    """0: binding mentioned on an added line; 1: other direct import."""
    suffix = PurePosixPath(path).suffix
    added = "\n".join(
        line[1:]
        for line in patch.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    identifiers = set(re.findall(r"[A-Za-z_$][\w$]*", added))
    priorities = {}
    if suffix == ".py":
        imports = _python_imports(path, source, paths)
    elif suffix in SOURCE_SUFFIXES:
        imports = (
            (target, names)
            for module, names in _js_imports(source)
            if (target := _js_path(path, module, paths))
        )
    else:
        return priorities
    for target, names in imports:
        rank = 0 if names & identifiers else 1
        priorities[target] = min(rank, priorities.get(target, rank))
    return priorities


def related_candidates(changed: set[str], eligible: set[str], imports: dict[str, int]) -> list[str]:
    stems = {PurePosixPath(p).stem.removeprefix("test_").removesuffix(".test") for p in changed}
    directories = {str(PurePosixPath(p).parent) for p in changed}
    candidates = []
    for path in eligible - changed:
        p = PurePosixPath(path)
        if path in imports:
            candidates.append((imports[path], path))
        elif any(stem and stem.lower() in p.stem.lower() for stem in stems):
            candidates.append((2, path))
        elif str(p.parent) in directories:
            candidates.append((3, path))
    return [path for _, path in sorted(candidates)]

"""Resolve direct local imports against PR HEAD paths; never execute project code."""

import ast
import posixpath
import re
from pathlib import PurePosixPath

from coday_pipeline.analyze.file_filter import exclusion
from coday_pipeline.analyze.function_context import js_tree
from coday_pipeline.analyze.import_aliases import alias_target, configured_alias

SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts"}


def eligible_context(path: str, mode: str, size: int, limit: int, patterns: list[str]) -> bool:
    return (
        mode in {"100644", "100755"}
        and 0 < size <= limit
        and not exclusion(path, patterns)
        and PurePosixPath(path).name.upper() not in {"AGENTS.MD", "CLAUDE.MD", "GEMINI.MD"}
    )


def _js_imports(source: str, suffix: str = ".ts"):
    raw = source.encode("utf-8")
    root = js_tree("module" + suffix, source)
    stack = [root]
    while stack:
        node = stack.pop()
        stack.extend(reversed(node.named_children))
        module, names, dynamic = None, set(), False
        if node.type == "import_statement" and not node.has_error:
            module = node.child_by_field_name("source")
            pending = [child for child in node.named_children if child.type == "import_clause"]
            while pending:
                child = pending.pop()
                if child.type in {"identifier", "type_identifier"}:
                    names.add(raw[child.start_byte : child.end_byte].decode("utf-8"))
                pending.extend(child.named_children)
        elif node.type == "call_expression" and not node.has_error:
            fn = node.child_by_field_name("function")
            args = node.child_by_field_name("arguments")
            if (
                fn is None
                or args is None
                or len(args.named_children) != 1
                or not (
                    fn.type == "import"
                    or (fn.type == "identifier" and raw[fn.start_byte : fn.end_byte] == b"require")
                )
            ):
                continue
            module = args.named_children[0]
            if fn.type == "import":
                dynamic = True
        if module is not None and module.type == "string":
            text = raw[module.start_byte : module.end_byte].decode("utf-8")
            if "\\" not in text:
                yield text[1:-1], names, dynamic


def _js_path(path: str, module: str, paths: set[str], configs: dict | None = None) -> str | None:
    if "\\" in module:
        return None
    target = (
        posixpath.normpath(posixpath.join(posixpath.dirname(path), module))
        if module.startswith(("./", "../"))
        else alias_target(path, module, paths, configs or {})
    )
    if target is None:
        return None
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


def import_priorities(
    path: str,
    source: str,
    patch: str,
    paths: set[str],
    configs: dict | None = None,
    audit: list | None = None,
) -> dict[str, int]:
    """0: binding mentioned on an added line; 1: other direct import."""
    suffix = PurePosixPath(path).suffix
    added = "\n".join(
        line[1:]
        for line in patch.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    identifiers = set(re.findall(r"[A-Za-z_$][\w$]*", added))
    changed_modules = (
        {module for module, _, _ in _js_imports(added, suffix)}
        if suffix in SOURCE_SUFFIXES - {".py"}
        else set()
    )
    priorities = {}
    if suffix == ".py":
        imports = _python_imports(path, source, paths)
    elif suffix in SOURCE_SUFFIXES:
        imports = []
        for module, names, dynamic in _js_imports(source, suffix):
            if dynamic and module not in changed_modules:
                continue  # Bound dynamic traversal to literal imports in this change.
            target = _js_path(path, module, paths, configs)
            if target:
                imports.append((target, names | ({module} if module in changed_modules else set())))
                if audit is not None:
                    audit.append(
                        dict(
                            path=path,
                            module=module,
                            target=target,
                            status="resolved",
                            reason="explicit_import",
                        )
                    )
            elif audit is not None and (
                module.startswith(("./", "../", "@/"))
                or configured_alias(path, module, paths, configs or {})
            ):
                audit.append(
                    dict(path=path, module=module, status="skipped", reason="unresolved_import")
                )
    else:
        return priorities
    for target, names in imports:
        rank = 0 if names & (identifiers | changed_modules) else 1
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

"""Bounded HEAD function context; never execute repository code.

Python uses its AST; JS/TS use concrete syntax trees, including arrow functions.
Only lines absent from the diff are emitted, with explicit fragment coordinates.
The fragments plus diff reconstruct the selected function; budget exclusions
never silently truncate it. Unsupported/invalid/oversized sources are recorded.
"""

import ast
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from coday_contracts.review_input import FunctionContext, FunctionFragment
from tree_sitter import Language, Parser

from coday_pipeline.analyze.diff_parser import parse_header, parse_patch

SUPPORTED_SUFFIXES = {".py", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"}
JS_FUNCTIONS = {
    "function_declaration",
    "function_expression",
    "generator_function_declaration",
    "generator_function",
    "arrow_function",
    "method_definition",
}


def contiguous_ranges(numbers) -> list[tuple[int, int]]:
    ranges = []
    for n in sorted(numbers):
        if ranges and n == ranges[-1][1] + 1:
            ranges[-1] = (ranges[-1][0], n)
        else:
            ranges.append((n, n))
    return ranges


def function_ranges(path: str, source: str) -> list[tuple[int, int]]:
    suffix = PurePosixPath(path).suffix
    if suffix == ".py":
        tree = ast.parse(source)
        return [
            (min([node.lineno, *[d.lineno for d in node.decorator_list]]), node.end_lineno)
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
    if suffix not in SUPPORTED_SUFFIXES:
        raise NotImplementedError
    root = js_tree(path, source)
    if root.has_error:
        raise SyntaxError("Source contains parser errors")
    ranges = []
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type in JS_FUNCTIONS:
            ranges.append((node.start_point.row + 1, node.end_point.row + 1))
        stack.extend(node.named_children)
    return ranges


def js_tree(path: str, source: str):
    suffix = PurePosixPath(path).suffix
    if suffix in {".ts", ".tsx", ".mts", ".cts"}:
        import tree_sitter_typescript as grammar

        language = grammar.language_tsx() if suffix == ".tsx" else grammar.language_typescript()
    else:
        import tree_sitter_javascript as grammar

        language = grammar.language()
    return Parser(Language(language)).parse(source.encode("utf-8")).root_node


@dataclass
class FunctionContextBuilder:
    head_sha: str
    remaining: int
    per_file_bytes: int
    file_limit: int
    contexts: list[FunctionContext] = field(default_factory=list)
    audit: list[dict] = field(default_factory=list)

    def skip(self, path: str, reason: str, **details) -> None:
        self.audit.append(
            dict(
                path=path,
                head_sha=self.head_sha,
                status="skipped",
                reason=reason,
                complete=False,
                **details,
            )
        )

    def add(self, path: str, source: str, patch: str) -> None:
        try:
            ranges = function_ranges(path, source)
        except NotImplementedError:
            self.skip(path, "unsupported_language")
            return
        except (SyntaxError, ValueError, RecursionError):
            self.skip(path, "parse_error")
            return
        hunks = parse_patch(patch)
        changed, deleted, visible = set(), set(), {}
        for hunk in hunks:
            cursor = parse_header(hunk.header).new_start
            for line in hunk.lines:
                if line.new_line is not None:
                    visible[line.new_line] = line.content
                if line.kind == "added":
                    changed.add(line.new_line)
                elif line.kind == "removed":
                    # A deletion is anchored only at the following HEAD line.
                    deleted.add(cursor)
                if line.new_line is not None:
                    cursor = line.new_line + 1
        selected = set()
        for line in sorted(changed | deleted):
            # A wholly deleted function must not select the next unchanged
            # function merely because its definition follows the deletion.
            enclosing = [
                r for r in ranges if r[0] <= line <= r[1] and (line in changed or r[0] < line)
            ]
            if enclosing:
                selected.add(min(enclosing, key=lambda r: (r[1] - r[0], r)))
        if not selected:
            self.skip(path, "no_enclosing_function")
            return
        # Merge overlapping/nested ranges, without swallowing adjacent functions.
        merged = []
        for start, end in sorted(selected):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
            else:
                merged.append((start, end))
        lines = source.split("\n")
        used = 0
        selected_files = {c.path for c in self.contexts}
        for start, end in merged:
            details = dict(start_line=start, end_line=end)
            if any(visible[n] != lines[n - 1] for n in range(start, end + 1) if n in visible):
                self.skip(path, "head_diff_mismatch", **details)
                continue
            if all(line in visible for line in range(start, end + 1)):
                self.skip(path, "already_in_diff", **details)
                continue
            context = FunctionContext(
                path=path,
                head_sha=self.head_sha,
                start_line=start,
                end_line=end,
                complete=False,
                complete_with_diff=True,
                fragments=[
                    FunctionFragment(start_line=s, end_line=e, code="\n".join(lines[s - 1 : e]))
                    for s, e in contiguous_ranges(set(range(start, end + 1)) - visible.keys())
                ],
                diff_ranges=contiguous_ranges(set(range(start, end + 1)) & visible.keys()),
            )
            # Include serialized metadata in the supplemental byte budget.
            size = len(context.model_dump_json(exclude_none=True).encode("utf-8"))
            reason = (
                "file_count_limit"
                if path not in selected_files and len(selected_files) >= self.file_limit
                else "file_byte_limit"
                if used + size > self.per_file_bytes
                else "input_byte_limit"
                if size > self.remaining
                else None
            )
            if reason:
                self.skip(path, reason, bytes=size, **details)
                continue
            self.contexts.append(context)
            selected_files.add(path)
            used += size
            self.remaining -= size
            self.audit.append(
                dict(
                    path=path,
                    head_sha=self.head_sha,
                    status="included",
                    reason="changed_function",
                    complete=False,
                    complete_with_diff=True,
                    deduplicated_lines=sum(e - s + 1 for s, e in context.diff_ranges),
                    bytes=size,
                    **details,
                )
            )

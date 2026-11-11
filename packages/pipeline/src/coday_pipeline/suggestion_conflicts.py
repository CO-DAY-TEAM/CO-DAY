"""Deterministic, PR-wide selection of non-overlapping suggested changes."""

import json

from coday_contracts.review_result import Finding, ReviewResult

SEVERITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def _start(finding: Finding) -> int:
    return finding.line if finding.start_line is None else finding.start_line


def _priority(finding: Finding) -> tuple[int, int, str, int, int, str]:
    # Finding has no persistent candidate ID. Canonical content breaks ties without
    # relying on chunk order, object identity, randomized hashes, or new fields.
    identity = json.dumps(finding.model_dump(mode="json"), sort_keys=True, ensure_ascii=True)
    return (
        SEVERITY_ORDER[finding.severity],
        finding.line - _start(finding) + 1,
        finding.path,
        _start(finding),
        finding.line,
        identity,
    )


def resolve_suggestion_conflicts(result: ReviewResult) -> ReviewResult:
    """Copy a complete PR result, suppressing only conflicting RIGHT suggestions.

    Greedy priority selection permits A and C when only A-B and B-C overlap.
    Returned findings retain their original order and all non-suggestion fields.
    Empty replacement text is a valid suggestion (deletion), not a missing one.
    """
    resolved = result.model_copy(deep=True)
    candidates = [
        finding
        for finding in resolved.findings
        if finding.side == "RIGHT" and finding.suggestion is not None
    ]
    for finding in candidates:
        # Judge already validates ranges. Reject corrupt persisted input rather
        # than silently correcting its location or publishing an unsafe plan.
        if not 1 <= _start(finding) <= finding.line:
            raise ValueError("Invalid suggested change range")

    retained: dict[str, list[tuple[int, int]]] = {}
    for finding in sorted(candidates, key=_priority):
        start, end = _start(finding), finding.line
        ranges = retained.setdefault(finding.path, [])
        if any(start <= other_end and other_start <= end for other_start, other_end in ranges):
            finding.suggestion = None
        else:
            ranges.append((start, end))
    return resolved

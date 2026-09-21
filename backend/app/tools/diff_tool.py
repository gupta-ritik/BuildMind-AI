"""
Unified diff computation.

Phase 1/2 stored a truncated copy of the new file content as `CodeChange.diff`,
which isn't an actual diff. This module computes real unified diffs so the
Code Reviewer agent, the human approval screen, and `/api/tasks/{id}/diff`
all show the same accurate, git-style diff — independent of whether the
workspace is a git repo yet (that's wired up properly in Phase 4).
"""
from __future__ import annotations

import difflib


def unified_diff(old_content: str, new_content: str, path: str) -> str:
    """Produce a git-style unified diff string for a single file."""
    old_lines = old_content.splitlines()
    new_lines = new_content.splitlines()
    diff_lines = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        lineterm="",
    )
    return "\n".join(diff_lines)


def diff_stats(diff_text: str) -> tuple[int, int]:
    """Return (lines_added, lines_removed) for a unified diff string."""
    added = removed = 0
    for line in diff_text.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return added, removed

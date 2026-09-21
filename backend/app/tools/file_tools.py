"""
Controlled file tools.

Every function takes an explicit `repo_root` and refuses to touch anything
outside it. Agents never get raw filesystem access — this module is the
only path from an agent to disk.
"""
from __future__ import annotations

import os
from pathlib import Path

# Directories we never want to walk into when listing/searching a repo.
_IGNORED_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", ".pytest_cache", ".mypy_cache",
}

MAX_FILE_READ_BYTES = 200_000  # guard against dumping huge files into context


class PathEscapeError(Exception):
    """Raised when a requested path resolves outside the repository root."""


def _safe_resolve(repo_root: str, relative_path: str) -> Path:
    root = Path(repo_root).resolve()
    candidate = (root / relative_path).resolve()
    if root not in candidate.parents and candidate != root:
        raise PathEscapeError(f"Path '{relative_path}' escapes repository root.")
    return candidate


def list_files(repo_root: str, subdirectory: str = ".", max_entries: int = 500) -> list[str]:
    """List files under `subdirectory`, relative to repo_root, skipping noise dirs."""
    start = _safe_resolve(repo_root, subdirectory)
    results: list[str] = []
    for dirpath, dirnames, filenames in os.walk(start):
        dirnames[:] = [d for d in dirnames if d not in _IGNORED_DIRS and not d.startswith(".")]
        for f in filenames:
            full = Path(dirpath) / f
            rel = full.relative_to(Path(repo_root).resolve())
            results.append(str(rel))
            if len(results) >= max_entries:
                return results
    return results


def read_file(repo_root: str, relative_path: str) -> str:
    """Read a text file's content, truncated to a safe size."""
    path = _safe_resolve(repo_root, relative_path)
    if not path.is_file():
        raise FileNotFoundError(f"No such file: {relative_path}")
    data = path.read_bytes()[:MAX_FILE_READ_BYTES]
    return data.decode("utf-8", errors="replace")


def write_file(repo_root: str, relative_path: str, content: str) -> str:
    """Write (create or overwrite) a file within the repo root. Returns the relative path written."""
    path = _safe_resolve(repo_root, relative_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

    # A new/changed file can add or remove a search hit, so the cached
    # directory listing in code_search.py must not outlive this write.
    from app.tools.code_search import invalidate_repo_cache  # local import: avoid a cycle
    invalidate_repo_cache(repo_root)

    return relative_path

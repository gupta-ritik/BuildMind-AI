"""
Per-task isolated workspace.

Spec §6: "Do not modify the user's original repository directly" and
"Each task should receive an isolated workspace." Phases 1-3 operated
directly on whatever path the caller passed in — a real gap, especially
now that Phase 4 adds git branch/commit/push. This module is the fix:
every task gets its own copy under `workspace_root/task-{id}/repository`,
and all agents operate only on that copy.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class WorkspaceError(Exception):
    pass


def _ignore_local_artifacts(_directory: str, names: list[str]) -> set[str]:
    ignored = {
        ".env",
        ".env.local",
        ".next",
        ".pytest_cache",
        ".venv",
        "node_modules",
        "venv",
        "__pycache__",
    }
    return {name for name in names if name in ignored or name.endswith(".pyc")}


def prepare_workspace(task_id: str, workspace_root: str, repository_path: str | None,
                       repository_url: str | None, clone_timeout_seconds: int = 120) -> str:
    """
    Create an isolated workspace for this task and return its path.

    Exactly one of repository_path / repository_url must be given.
    - repository_url: real `git clone` into the workspace (network access
      required; this is a genuine clone, not simulated).
    - repository_path: a full copy of the local directory into the
      workspace, so nothing downstream ever touches the original.
    """
    if bool(repository_path) == bool(repository_url):
        raise WorkspaceError("Provide exactly one of repository_path or repository_url.")

    root = Path(workspace_root) / f"task-{task_id}"
    root.mkdir(parents=True, exist_ok=True)
    dest = root / "repository"
    if dest.exists():
        raise WorkspaceError(f"Workspace already exists for task {task_id}.")

    if repository_url:
        try:
            subprocess.run(
                ["git", "clone", repository_url, str(dest)],
                capture_output=True, text=True, timeout=clone_timeout_seconds, check=True,
            )
        except subprocess.CalledProcessError as exc:
            raise WorkspaceError(f"git clone failed: {exc.stderr}") from exc
        except subprocess.TimeoutExpired as exc:
            raise WorkspaceError(f"git clone exceeded {clone_timeout_seconds}s timeout.") from exc
    else:
        source = Path(repository_path).expanduser().resolve()
        if not source.is_dir():
            raise WorkspaceError(f"Repository path not found: {source}")
        # Preserve source files and git history without copying generated
        # builds, dependencies, caches, or local secrets into the workspace.
        shutil.copytree(source, dest, ignore=_ignore_local_artifacts)

    return str(dest)


def cleanup_workspace(task_id: str, workspace_root: str) -> None:
    """Remove a task's isolated workspace entirely."""
    root = Path(workspace_root) / f"task-{task_id}"
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)

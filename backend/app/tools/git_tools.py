"""
Git operations.

All real `git` CLI calls via subprocess against the task's isolated
workspace — never the user's original repository. Credentials (GitHub
token) are only ever used here, to temporarily rewrite the push remote
URL; the LLM/agents never see them.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass


class GitError(Exception):
    pass


@dataclass
class GitResult:
    success: bool
    output: str


def _run(repo_root: str, args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=repo_root, capture_output=True, text=True, timeout=timeout,
    )


def is_git_repo(repo_root: str) -> bool:
    result = _run(repo_root, ["rev-parse", "--is-inside-work-tree"])
    return result.returncode == 0


def ensure_git_repo(repo_root: str) -> None:
    """
    Make sure `repo_root` is a git repository with at least one commit, so
    later diffs/branches/commits behave predictably. If it's already a git
    repo (e.g. cloned from a URL), this is a no-op aside from setting a
    default commit identity for the agent's own commits.
    """
    _run(repo_root, ["config", "user.email", "codepilot-agent@local"])
    _run(repo_root, ["config", "user.name", "CodePilot Agent"])

    if is_git_repo(repo_root):
        return

    init = _run(repo_root, ["init"])
    if init.returncode != 0:
        raise GitError(f"git init failed: {init.stderr}")
    _run(repo_root, ["config", "user.email", "codepilot-agent@local"])
    _run(repo_root, ["config", "user.name", "CodePilot Agent"])

    _run(repo_root, ["add", "-A"])
    # Only commit if there's actually something to commit (non-empty dir).
    diff_check = _run(repo_root, ["diff", "--cached", "--quiet"])
    if diff_check.returncode != 0:  # non-zero means there ARE staged changes
        _run(repo_root, ["commit", "-m", "Initial commit (pre-existing content)"])


def git_status(repo_root: str) -> list[str]:
    result = _run(repo_root, ["status", "--porcelain"])
    return [line for line in result.stdout.splitlines() if line.strip()]


def git_diff(repo_root: str, staged: bool = False) -> str:
    args = ["diff", "--cached"] if staged else ["diff"]
    result = _run(repo_root, args)
    return result.stdout


def create_branch(repo_root: str, branch_name: str) -> GitResult:
    result = _run(repo_root, ["checkout", "-b", branch_name])
    if result.returncode != 0:
        # Branch may already exist (e.g. resumed task) - fall back to switching to it.
        switch = _run(repo_root, ["checkout", branch_name])
        if switch.returncode != 0:
            return GitResult(success=False, output=result.stderr + switch.stderr)
        return GitResult(success=True, output=f"Switched to existing branch {branch_name}")
    return GitResult(success=True, output=result.stdout or f"Created branch {branch_name}")


def commit_all(repo_root: str, message: str) -> tuple[str | None, GitResult]:
    """Stage and commit all changes. Returns (commit_hash_or_None, result)."""
    _run(repo_root, ["add", "-A"])
    diff_check = _run(repo_root, ["diff", "--cached", "--quiet"])
    if diff_check.returncode == 0:
        return None, GitResult(success=True, output="Nothing to commit — working tree matches HEAD.")

    commit = _run(repo_root, ["commit", "-m", message])
    if commit.returncode != 0:
        return None, GitResult(success=False, output=commit.stderr)

    rev = _run(repo_root, ["rev-parse", "HEAD"])
    commit_hash = rev.stdout.strip() if rev.returncode == 0 else None
    return commit_hash, GitResult(success=True, output=commit.stdout)


def _remote_url(repo_root: str, remote: str = "origin") -> str | None:
    result = _run(repo_root, ["remote", "get-url", remote])
    return result.stdout.strip() if result.returncode == 0 else None


_HTTPS_GITHUB_RE = re.compile(r"^https://(?:[^@/]+@)?github\.com/(.+)$")


def push_branch(repo_root: str, branch_name: str, remote: str = "origin",
                 github_token: str | None = None) -> GitResult:
    """
    Push `branch_name` to `remote`. If no remote is configured, this is
    reported (not raised) as a non-fatal skip — plenty of local-only tasks
    have nothing to push to.

    If `github_token` is provided and the remote is a github.com HTTPS URL,
    the token is temporarily embedded in the push URL (never logged, never
    passed to the LLM) and the original remote URL is restored afterward
    regardless of success or failure.
    """
    original_url = _remote_url(repo_root, remote)
    if not original_url:
        return GitResult(success=False, output=f"No '{remote}' remote configured — skipping push.")

    push_url = original_url
    rewrote_url = False
    if github_token:
        match = _HTTPS_GITHUB_RE.match(original_url)
        if match:
            push_url = f"https://x-access-token:{github_token}@github.com/{match.group(1)}"
            rewrote_url = True

    try:
        if rewrote_url:
            _run(repo_root, ["remote", "set-url", remote, push_url])
        result = _run(repo_root, ["push", "-u", remote, branch_name], timeout=60)
        if result.returncode != 0:
            # Redact anything that looks like it could contain the token.
            stderr = result.stderr.replace(github_token, "***") if github_token else result.stderr
            return GitResult(success=False, output=stderr)
        return GitResult(success=True, output=result.stdout or "Pushed successfully.")
    finally:
        if rewrote_url:
            _run(repo_root, ["remote", "set-url", remote, original_url])

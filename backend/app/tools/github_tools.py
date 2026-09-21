"""
GitHub API integration.

Real REST calls to api.github.com via httpx — no simulated responses. The
token is read from settings/environment and used only in this module's
Authorization header; it is never included in any prompt or agent-visible
state.
"""
from __future__ import annotations

import re

import httpx

_API_BASE = "https://api.github.com"
_OWNER_REPO_RE = re.compile(r"github\.com[:/]([^/]+)/([^/.]+?)(?:\.git)?/?$")


class GitHubError(Exception):
    pass


def parse_owner_repo(repository_url: str) -> tuple[str, str]:
    """Extract (owner, repo) from a GitHub URL, e.g. https://github.com/foo/bar.git"""
    match = _OWNER_REPO_RE.search(repository_url)
    if not match:
        raise GitHubError(f"Could not parse owner/repo from: {repository_url}")
    return match.group(1), match.group(2)


def create_pull_request(
    owner: str,
    repo: str,
    head_branch: str,
    base_branch: str,
    title: str,
    body: str,
    token: str,
) -> dict:
    """Create a real pull request. Raises GitHubError with a redacted message on failure."""
    if not token:
        raise GitHubError("No GitHub token configured — cannot create a pull request.")

    url = f"{_API_BASE}/repos/{owner}/{repo}/pulls"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {"title": title, "head": head_branch, "base": base_branch, "body": body}

    try:
        response = httpx.post(url, json=payload, headers=headers, timeout=30)
    except httpx.HTTPError as exc:
        raise GitHubError(f"Network error creating PR: {exc}") from exc

    if response.status_code >= 400:
        # Never let the raw response (which could theoretically echo the
        # Authorization header back in an error trace) leak the token.
        detail = response.text.replace(token, "***")
        raise GitHubError(f"GitHub API error ({response.status_code}): {detail}")

    data = response.json()
    return {"url": data["html_url"], "number": data["number"], "state": data["state"]}


def get_pull_request_status(owner: str, repo: str, pr_number: int, token: str) -> dict:
    url = f"{_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    response = httpx.get(url, headers=headers, timeout=30)
    if response.status_code >= 400:
        detail = response.text.replace(token, "***")
        raise GitHubError(f"GitHub API error ({response.status_code}): {detail}")
    data = response.json()
    return {"state": data["state"], "merged": data.get("merged", False)}

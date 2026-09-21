"""
GitHub PR Agent.

Creates the pull request via the real GitHub API. Skips gracefully (not a
failure) when there's no repository_url or no GitHub token configured —
plenty of tasks are local-only and never intended to open a PR.
"""
from __future__ import annotations

import logging

from app.config import get_settings
from app.state import CodePilotState, TaskStatus, get_plan
from app.tools import github_tools

logger = logging.getLogger(__name__)


def github_pr_node(state: CodePilotState) -> dict:
    settings = get_settings()
    repository_url = state.get("repository_url")
    branch_name = state["branch_name"]
    plan = get_plan(state)
    logs = []

    if not repository_url:
        logs.append("[GitHubPR] No repository_url configured — skipping PR creation.")
        return {"status": TaskStatus.COMPLETED, "execution_logs": logs}

    if not settings.github_token:
        logs.append("[GitHubPR] No GITHUB_TOKEN configured — skipping PR creation.")
        return {"status": TaskStatus.COMPLETED, "execution_logs": logs}

    try:
        owner, repo = github_tools.parse_owner_repo(repository_url)
        title = f"CodePilot: {plan.goal}" if plan else f"CodePilot: {state['task']}"
        body = _build_pr_body(state)

        pr = github_tools.create_pull_request(
            owner=owner,
            repo=repo,
            head_branch=branch_name,
            base_branch="main",
            title=title,
            body=body,
            token=settings.github_token,
        )
        logs.append(f"[GitHubPR] Created PR #{pr['number']}: {pr['url']}")
        return {
            "pull_request_url": pr["url"],
            "status": TaskStatus.COMPLETED,
            "execution_logs": logs,
        }
    except github_tools.GitHubError as exc:
        logger.warning("PR creation failed: %s", exc)
        return {
            "status": TaskStatus.COMPLETED,
            "errors": [f"PR creation failed (code committed and pushed regardless): {exc}"],
            "execution_logs": logs + [f"[GitHubPR] ERROR: {exc}"],
        }


def _build_pr_body(state: CodePilotState) -> str:
    plan = get_plan(state)
    test_results = state.get("test_results", [])
    review = state.get("review_result")
    latest_test = test_results[-1] if test_results else None

    lines = ["## Summary", plan.goal if plan else state["task"], ""]
    if plan and plan.steps:
        lines += ["## Changes", *[f"- {s}" for s in plan.steps], ""]
    if latest_test:
        lines += ["## Tests", f"{latest_test.passed} passed, {latest_test.failed} failed", ""]
    if review:
        lines += ["## Code Review", f"Status: {review.status}"]
        if review.suggestions:
            lines += [f"- {s}" for s in review.suggestions]
    lines.append("\n_Opened automatically by CodePilot._")
    return "\n".join(lines)

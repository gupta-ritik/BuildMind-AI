"""
Git Manager Agent.

Runs only after human approval. Creates the task branch, commits the
approved changes, and pushes if a remote is configured. Never touches the
user's original repository — this operates on the isolated task workspace
prepared by tools/workspace.py.
"""
from __future__ import annotations

from app.config import get_settings
from app.state import CodePilotState, TaskStatus, get_plan
from app.tools import git_tools


def git_manager_node(state: CodePilotState) -> dict:
    settings = get_settings()
    repo_root = state["repository_path"]
    branch_name = state["branch_name"]
    plan = get_plan(state)
    logs = [f"[GitManager] Preparing branch '{branch_name}'."]

    branch_result = git_tools.create_branch(repo_root, branch_name)
    logs.append(f"[GitManager] {branch_result.output.strip()}")
    if not branch_result.success:
        return {
            "status": TaskStatus.FAILED,
            "errors": [f"Failed to create/switch branch: {branch_result.output}"],
            "execution_logs": logs,
        }

    commit_message = f"feat: {plan.goal}" if plan else f"feat: {state['task']}"
    commit_hash, commit_result = git_tools.commit_all(repo_root, commit_message)
    logs.append(f"[GitManager] {commit_result.output.strip()}")
    if not commit_result.success:
        return {
            "status": TaskStatus.FAILED,
            "errors": [f"Commit failed: {commit_result.output}"],
            "execution_logs": logs,
        }

    push_result = git_tools.push_branch(
        repo_root, branch_name, github_token=settings.github_token
    )
    logs.append(f"[GitManager] Push: {push_result.output.strip()}")

    return {
        "commit_hash": commit_hash,
        "status": TaskStatus.CREATING_PR,
        "execution_logs": logs,
        # Stashed for the PR agent to know whether a push actually succeeded.
        "errors": [] if push_result.success else [f"Push skipped/failed: {push_result.output}"],
    }

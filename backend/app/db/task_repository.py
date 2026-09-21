"""
Task persistence.

Replaces the in-memory `_TASKS` dict used in Phases 1-4 with real
PostgreSQL storage, so task history survives a backend restart — spec
§14/§25 Phase 5. The full CodePilotState is stored as a JSON snapshot for
exact round-tripping, plus normalized rows (AgentRun, TestRun, Review,
FileChange, PullRequest) for querying/analytics without deserializing the
whole blob every time.
"""
from __future__ import annotations

import json
from datetime import datetime

from app.db.models import AgentRun, FileChange, PullRequest, Review, Task, TestRun
from app.db.session import get_db
from app.state import status_value
from app.tools.diff_tool import diff_stats


def _json_default(obj):
    """Serialize enums / dataclasses / pydantic models that plain json can't handle."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "value"):  # Enum
        return obj.value
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


def _serializable_state(state: dict) -> dict:
    """Round-trip through JSON to get a plain-dict snapshot safe for the JSON column."""
    return json.loads(json.dumps(state, default=_json_default))


def save_task(task_id: str, state: dict, repository_id: str | None = None) -> None:
    """Upsert the task's full state snapshot plus normalized child rows."""
    snapshot = _serializable_state(state)
    plan = state.get("plan")

    with get_db() as db:
        task = db.get(Task, task_id)
        if task is None:
            task = Task(id=task_id, repository_id=repository_id, description=state.get("task", ""))
            db.add(task)

        task.description = state.get("task", task.description)
        task.branch_name = state.get("branch_name")
        task.status = status_value(state.get("status"))
        task.workspace_path = state.get("repository_path")
        task.commit_hash = state.get("commit_hash")
        task.pull_request_url = state.get("pull_request_url")
        task.final_report = state.get("final_report")
        task.state_snapshot = snapshot

        # Normalized rows: cheap to recompute from state each save, and kept
        # small by only inserting what's new since the last save.
        existing_test_runs = len(task.test_runs) if task.id else 0
        for t in state.get("test_results", [])[existing_test_runs:]:
            db.add(TestRun(
                task_id=task_id, status=t.status, passed=t.passed,
                failed=t.failed, duration_seconds=t.duration_seconds,
            ))

        existing_reviews = len(task.reviews) if task.id else 0
        review = state.get("review_result")
        if review and existing_reviews == 0:
            db.add(Review(
                task_id=task_id, status=review.status,
                issues=review.issues, suggestions=review.suggestions,
            ))

        existing_prs = len(task.pull_requests) if task.id else 0
        pr_url = state.get("pull_request_url")
        if pr_url and existing_prs == 0:
            db.add(PullRequest(task_id=task_id, url=pr_url))

        existing_agent_runs = {r.agent_name for r in task.agent_runs} if task.id else set()
        for agent_name, duration in state.get("node_durations", {}).items():
            if agent_name not in existing_agent_runs:
                db.add(AgentRun(
                    task_id=task_id, agent_name=agent_name,
                    status="completed", duration_seconds=duration,
                ))

        existing_file_changes = {f.path for f in task.file_changes} if task.id else set()
        for change in state.get("code_changes", []):
            if change.path not in existing_file_changes:
                added, removed = diff_stats(change.diff)
                db.add(FileChange(
                    task_id=task_id, path=change.path, change_type=change.change_type,
                    lines_added=added, lines_removed=removed, explanation=change.explanation,
                ))


def load_task_snapshot(task_id: str) -> dict | None:
    """Return the raw JSON state snapshot for a task, or None if not found."""
    with get_db() as db:
        task = db.get(Task, task_id)
        return task.state_snapshot if task else None


def task_exists(task_id: str) -> bool:
    with get_db() as db:
        return db.get(Task, task_id) is not None


def list_tasks(limit: int = 50) -> list[dict]:
    with get_db() as db:
        tasks = (
            db.query(Task)
            .order_by(Task.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "task_id": t.id,
                "description": t.description,
                "status": status_value(t.status),
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "pull_request_url": t.pull_request_url,
            }
            for t in tasks
        ]

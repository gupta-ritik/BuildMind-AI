"""
Phase 3 API surface.

POST /api/tasks kicks off a task synchronously up to whichever point it
first stops: the end of the graph, a FAILED status, or the human-approval
interrupt (status AWAITING_APPROVAL). From there:

  POST /api/tasks/{id}/approve         -> resumes with ApprovalStatus.APPROVED
  POST /api/tasks/{id}/reject          -> resumes with ApprovalStatus.REJECTED
  POST /api/tasks/{id}/request-changes -> resumes with CHANGES_REQUESTED,
                                           sends the workflow back to the Coder
  GET  /api/tasks/{id}/diff            -> the aggregated unified diff
  GET  /api/tasks/{id}                 -> full current state

Phase 6 replaces the synchronous response with WebSocket/SSE streaming of
agent_started/agent_completed/... events without changing this request shape.
"""
from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, model_validator

from app.cache.redis_client import get_events, publish_event, tail_events
from app.config import get_settings
from app.db.task_repository import list_tasks, load_task_snapshot, save_task, task_exists
from app.graph import codepilot_graph
from app.state import ApprovalStatus, TaskStatus, status_value
from app.tools import git_tools, workspace

router = APIRouter(prefix="/api", tags=["tasks"])

# Guards against double-invoking the same task_id concurrently (e.g. a
# double-click on Approve while the background thread from the initial
# create_task call is still running).
_running_tasks: set[str] = set()
_running_lock = threading.Lock()


def _mark_running(task_id: str) -> bool:
    with _running_lock:
        if task_id in _running_tasks:
            return False
        _running_tasks.add(task_id)
        return True


def _mark_done(task_id: str) -> None:
    with _running_lock:
        _running_tasks.discard(task_id)


class CreateTaskRequest(BaseModel):
    repository_path: str | None = None
    repository_url: str | None = None
    task: str
    branch_name: str | None = None

    @model_validator(mode="after")
    def _exactly_one_source(self):
        if bool(self.repository_path) == bool(self.repository_url):
            raise ValueError("Provide exactly one of repository_path or repository_url.")
        return self


class TaskResponse(BaseModel):
    task_id: str
    status: str
    plan: dict | None = None
    relevant_files: list[dict] = []
    code_changes: list[dict] = []
    test_results: list[dict] = []
    review_result: dict | None = None
    approval_status: str | None = None
    git_diff: str | None = None
    commit_hash: str | None = None
    pull_request_url: str | None = None
    final_report: str | None = None
    errors: list[str] = []
    execution_logs: list[str] = []
    node_durations: dict[str, float] = {}
    total_duration_seconds: float = 0.0


def _config(task_id: str) -> dict:
    return {"configurable": {"thread_id": task_id}}


def _serialize(task_id: str, state: dict) -> TaskResponse:
    plan = state.get("plan")
    review = state.get("review_result")
    approval = state.get("approval_status")
    durations = state.get("node_durations", {})

    def _dump(x):
        return x.model_dump() if hasattr(x, "model_dump") else x

    return TaskResponse(
        task_id=task_id,
        status=status_value(state.get("status")),
        plan=_dump(plan) if plan else None,
        relevant_files=[_dump(f) for f in state.get("relevant_files", [])],
        code_changes=[_dump(c) for c in state.get("code_changes", [])],
        test_results=[_dump(t) for t in state.get("test_results", [])],
        review_result=_dump(review) if review else None,
        approval_status=status_value(approval) if approval else None,
        git_diff=state.get("git_diff"),
        commit_hash=state.get("commit_hash"),
        pull_request_url=state.get("pull_request_url"),
        final_report=state.get("final_report"),
        errors=state.get("errors", []),
        execution_logs=state.get("execution_logs", []),
        node_durations=durations,
        total_duration_seconds=round(sum(durations.values()), 3),
    )


def _run_graph_in_background(task_id: str, initial_state: dict) -> None:
    """Executed in a background thread — see create_task()."""
    try:
        publish_event(task_id, "task_started", {})
        final_state = codepilot_graph.invoke(initial_state, config=_config(task_id))
        save_task(task_id, final_state)
        publish_event(task_id, "task_paused_or_completed", {"status": status_value(final_state.get("status"))})
    except Exception as exc:  # noqa: BLE001 - background thread must not crash silently
        publish_event(task_id, "task_error", {"error": str(exc)})
        error_state = dict(initial_state)
        error_state["status"] = TaskStatus.FAILED
        error_state["errors"] = [f"Unhandled error running task: {exc}"]
        save_task(task_id, error_state)
    finally:
        _mark_done(task_id)


def _resume_graph_in_background(task_id: str, decision: ApprovalStatus) -> None:
    try:
        publish_event(task_id, "task_resumed", {"decision": status_value(decision)})
        config = _config(task_id)
        codepilot_graph.update_state(config, {"approval_status": decision})
        final_state = codepilot_graph.invoke(None, config=config)
        save_task(task_id, final_state)
        publish_event(task_id, "task_paused_or_completed", {"status": status_value(final_state.get("status"))})
    except Exception as exc:  # noqa: BLE001
        publish_event(task_id, "task_error", {"error": str(exc)})
    finally:
        _mark_done(task_id)


@router.post("/tasks", response_model=TaskResponse)
def create_task(req: CreateTaskRequest) -> TaskResponse:
    settings = get_settings()
    task_id = str(uuid.uuid4())

    if req.repository_path:
        source = Path(req.repository_path).expanduser().resolve()
        if not source.is_dir():
            raise HTTPException(status_code=400, detail=f"Repository path not found: {source}")

    try:
        isolated_path = workspace.prepare_workspace(
            task_id=task_id,
            workspace_root=settings.workspace_root,
            repository_path=req.repository_path,
            repository_url=req.repository_url,
        )
        git_tools.ensure_git_repo(isolated_path)
    except workspace.WorkspaceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    initial_state = {
        "task_id": task_id,
        "task": req.task,
        "repository_path": isolated_path,
        "repository_url": req.repository_url,
        "branch_name": req.branch_name or f"codepilot/task-{task_id[:8]}",
        "status": TaskStatus.PLANNING,
        "relevant_files": [],
        "code_changes": [],
        "file_baselines": {},
        "test_results": [],
        "retry_count": 0,
        "review_cycles": 0,
        "debug_notes": [],
        "approval_status": ApprovalStatus.PENDING,
        "errors": [],
        "execution_logs": [f"[System] Task {task_id} created. Workspace: {isolated_path}"],
        "node_durations": {},
    }

    # Persist immediately so GET /api/tasks/{id} and the SSE stream both
    # work right away, before the graph has done any real work.
    save_task(task_id, initial_state)
    _mark_running(task_id)
    thread = threading.Thread(target=_run_graph_in_background, args=(task_id, initial_state), daemon=True)
    thread.start()

    return _serialize(task_id, initial_state)


@router.get("/tasks")
def list_all_tasks(limit: int = 50) -> dict:
    return {"tasks": list_tasks(limit=limit)}


@router.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: str) -> TaskResponse:
    snapshot = load_task_snapshot(task_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return _serialize(task_id, snapshot)


@router.get("/tasks/{task_id}/diff")
def get_task_diff(task_id: str) -> dict:
    snapshot = load_task_snapshot(task_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "task_id": task_id,
        "diff": snapshot.get("git_diff") or "",
        "files_changed": [
            {"path": c.get("path"), "change_type": c.get("change_type")}
            for c in snapshot.get("code_changes", [])
        ],
    }


@router.get("/tasks/{task_id}/logs")
def get_task_logs(task_id: str) -> dict:
    snapshot = load_task_snapshot(task_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task_id": task_id, "logs": snapshot.get("execution_logs", [])}


@router.get("/tasks/{task_id}/events")
def get_task_events(task_id: str) -> dict:
    """Non-streaming snapshot of events so far (Redis-backed, spec §13)."""
    if not task_exists(task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task_id": task_id, "events": get_events(task_id)}


@router.get("/tasks/{task_id}/stream")
def stream_task_events(task_id: str) -> StreamingResponse:
    """
    Real Server-Sent Events stream. Replays the full event history first
    (so a client connecting slightly late doesn't miss the start), then
    either closes immediately (if the task isn't currently running - e.g.
    it's sitting at AWAITING_APPROVAL or already finished) or tails live
    events for the run currently in progress by polling the durable Redis
    list (see tail_events docstring for why polling, not pub/sub).

    Important: "task_paused_or_completed" is published on EVERY pause,
    including the mid-task human-approval interrupt, not just true
    completion. Backlog replay never treats it as a stop condition -
    after an approve/resume, the backlog contains both the original
    approval-pause event and the subsequent completion event, and both
    must be replayed. Only a live-tailed event is used to end the stream,
    since only one run's worth of live events can arrive per subscription.
    """
    if not task_exists(task_id):
        raise HTTPException(status_code=404, detail="Task not found")

    def event_generator():
        # Check running-state BEFORE reading backlog: anything the
        # background thread publishes after this check is guaranteed to be
        # either in the backlog we're about to read (if published before
        # that read) or caught by tail_events' poll loop (which starts
        # exactly at len(backlog) and keeps polling while is_still_running
        # reports True) - there is no gap in which an event can vanish.
        was_running = task_id in _running_tasks

        backlog = get_events(task_id)
        for event in backlog:
            yield f"data: {json.dumps(event)}\n\n"

        if not was_running:
            return  # nothing was executing - backlog is everything

        for event in tail_events(task_id, start_index=len(backlog),
                                  is_still_running=lambda: task_id in _running_tasks):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def _resume(task_id: str, decision: ApprovalStatus) -> TaskResponse:
    snapshot = load_task_snapshot(task_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if snapshot.get("status") != TaskStatus.AWAITING_APPROVAL.value:
        raise HTTPException(
            status_code=409,
            detail=f"Task is not awaiting approval (current status: {snapshot.get('status')}).",
        )
    if not _mark_running(task_id):
        raise HTTPException(status_code=409, detail="Task is already running.")

    thread = threading.Thread(target=_resume_graph_in_background, args=(task_id, decision), daemon=True)
    thread.start()

    snapshot["approval_status"] = status_value(decision)
    return _serialize(task_id, snapshot)


@router.post("/tasks/{task_id}/approve", response_model=TaskResponse)
def approve_task(task_id: str) -> TaskResponse:
    return _resume(task_id, ApprovalStatus.APPROVED)


@router.post("/tasks/{task_id}/reject", response_model=TaskResponse)
def reject_task(task_id: str) -> TaskResponse:
    return _resume(task_id, ApprovalStatus.REJECTED)


@router.post("/tasks/{task_id}/request-changes", response_model=TaskResponse)
def request_changes(task_id: str) -> TaskResponse:
    return _resume(task_id, ApprovalStatus.CHANGES_REQUESTED)


@router.post("/tasks/{task_id}/create-pr", response_model=TaskResponse)
def create_pr_manually(task_id: str) -> TaskResponse:
    """
    Manually trigger PR creation for a task that reached COMPLETED without
    one (e.g. no GITHUB_TOKEN was configured when the workflow originally
    ran github_pr_node, but one is available now).
    """
    from app.agents.github_pr import github_pr_node  # local import: avoid a cycle at module load

    snapshot = load_task_snapshot(task_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if snapshot.get("pull_request_url"):
        raise HTTPException(status_code=409, detail="Pull request already created for this task.")
    if snapshot.get("status") not in (TaskStatus.COMPLETED.value, TaskStatus.CREATING_PR.value):
        raise HTTPException(
            status_code=409,
            detail=f"Task must be COMPLETED or CREATING_PR to create a PR (current: {snapshot.get('status')}).",
        )

    update = github_pr_node(snapshot)
    snapshot.update(update)
    save_task(task_id, snapshot)
    return _serialize(task_id, snapshot)


@router.post("/tasks/{task_id}/cancel", response_model=TaskResponse)
def cancel_task(task_id: str) -> TaskResponse:
    snapshot = load_task_snapshot(task_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Task not found")
    snapshot["status"] = TaskStatus.FAILED.value
    snapshot.setdefault("errors", []).append("Task cancelled by user.")
    save_task(task_id, snapshot)
    publish_event(task_id, "task_error", {"error": "Cancelled by user."})
    return _serialize(task_id, snapshot)


@router.get("/settings/public")
def get_public_settings() -> dict:
    """Non-secret configuration the frontend's Settings page can display."""
    settings = get_settings()
    return {
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "max_debug_retries": settings.max_debug_retries,
        "max_review_cycles": settings.max_review_cycles,
        "use_docker_sandbox": settings.use_docker_sandbox,
        "github_configured": bool(settings.github_token),
    }


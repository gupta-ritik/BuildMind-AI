"""
Strongly typed shared state for the CodePilot LangGraph workflow.

Structured data is passed between agents wherever possible instead of raw
strings, so downstream agents and the API layer can reason about the state
reliably.
"""
from __future__ import annotations

from enum import Enum
from typing import Annotated, Optional
from typing_extensions import TypedDict

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    EXPLORING = "exploring"
    CODING = "coding"
    TESTING = "testing"
    DEBUGGING = "debugging"
    REVIEWING = "reviewing"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    CREATING_PR = "creating_pr"
    COMPLETED = "completed"
    FAILED = "failed"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"


class Plan(BaseModel):
    goal: str
    steps: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class RelevantFile(BaseModel):
    path: str
    reason: str


class CodeChange(BaseModel):
    path: str
    change_type: str  # "created" | "modified" | "deleted"
    diff: str
    explanation: str


class TestResult(BaseModel):
    status: str  # "passed" | "failed" | "error"
    passed: int = 0
    failed: int = 0
    errors: list[str] = Field(default_factory=list)
    output: str = ""
    duration_seconds: float = 0.0


class ReviewResult(BaseModel):
    status: str  # "approved" | "changes_requested"
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


def _append_logs(existing: list[str], new: list[str]) -> list[str]:
    return existing + new


def get_plan(state: dict) -> "Plan | None":
    """
    Return state['plan'] as a real Plan object, coercing from a plain dict
    if needed. Normally the checkpointer round-trips it as an actual Plan
    (see app/db/checkpointer.py's msgpack allowlist), but this keeps every
    agent robust even if that ever falls back to a dict — a stricter
    langgraph-checkpoint release, a different checkpointer, or a state
    snapshot loaded straight from the JSON column in Postgres.
    """
    plan = state.get("plan")
    if plan is None or isinstance(plan, Plan):
        return plan
    return Plan(**plan)


def status_value(x) -> str:
    """
    Correctly convert a status-like value (TaskStatus/ApprovalStatus enum
    member, plain string, or None) to its plain string value everywhere in
    the codebase. str(SomeEnum.MEMBER) is NOT what we want here — for a
    regular `class X(str, Enum)`, Python's default Enum.__str__ returns
    "X.MEMBER" (e.g. "TaskStatus.PLANNING"), not the actual value
    ("planning") that gets stored in JSON/Postgres. Using bare str() on an
    enum was a real, previously-shipped bug in this codebase: it silently
    broke every status comparison against a loaded snapshot (routes.py's
    approve/reject/create-pr endpoints all returned 409 unconditionally)
    and produced ugly "TaskStatus.X" strings in API responses and SSE
    events. Always convert through this helper, never through str().
    """
    if x is None:
        return "unknown"
    value = x.value if hasattr(x, "value") else str(x)
    if value.startswith(("TaskStatus.", "ApprovalStatus.")):
        return value.split(".", 1)[1].lower()
    return value


class CodePilotState(TypedDict, total=False):
    # Task identity
    task_id: str
    task: str
    repository_path: str
    repository_url: Optional[str]
    branch_name: Optional[str]

    # Workflow status
    status: TaskStatus

    # Planner output
    plan: Optional[Plan]

    # Explorer output
    relevant_files: list[RelevantFile]
    repository_summary: Optional[str]

    # Coder output
    code_changes: list[CodeChange]
    git_diff: Optional[str]
    file_baselines: dict[str, str]

    # Test Agent output
    test_results: list[TestResult]

    # Debugger
    retry_count: int
    debug_notes: list[str]

    # Reviewer
    review_result: Optional[ReviewResult]
    review_cycles: int

    # Human approval
    approval_status: ApprovalStatus

    # Git / GitHub (Phase 4+)
    commit_hash: Optional[str]
    pull_request_url: Optional[str]
    final_report: Optional[str]

    # Errors + logs
    errors: list[str]
    execution_logs: Annotated[list[str], _append_logs]
    node_durations: dict[str, float]

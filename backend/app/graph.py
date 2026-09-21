"""
LangGraph workflow for CodePilot.

Phase 3 scope adds, after tests pass:

  Tester -> Reviewer
  Reviewer: approved            -> Human Approval  (graph PAUSES here)
            changes_requested   -> Coder -> Tester -> Reviewer (bounded by
                                    MAX_REVIEW_CYCLES; if exhausted, escalate
                                    to Human Approval anyway with the
                                    outstanding issues visible, rather than
                                    looping forever or silently failing)
  Human Approval: approved      -> END for now (Git/GitHub arrive in Phase 4)
                  rejected      -> END, status REJECTED
                  changes_requested -> Coder -> Tester -> Reviewer -> ...

The graph is compiled with `interrupt_before=["human_approval"]`: `invoke()`
returns as soon as it reaches that node, with status AWAITING_APPROVAL, and
does not proceed until the API layer resumes it with a decision (see
api/routes.py). This is real LangGraph human-in-the-loop, not a simulated
pause.
"""
from __future__ import annotations

import time
from functools import wraps

from langgraph.graph import END, StateGraph

from app.agents.coder import coder_node
from app.agents.debugger import debugger_node
from app.agents.explorer import explorer_node
from app.agents.final_report import final_report_node
from app.agents.git_manager import git_manager_node
from app.agents.github_pr import github_pr_node
from app.agents.human_approval import human_approval_node
from app.agents.planner import planner_node
from app.agents.reviewer import reviewer_node
from app.agents.tester import tester_node
from app.cache.redis_client import publish_event
from app.config import get_settings
from app.db.checkpointer import get_checkpointer
from app.state import ApprovalStatus, CodePilotState, TaskStatus, status_value

# Postgres-backed checkpointer (app/db/checkpointer.py): human-approval
# pauses, and the whole graph's resumability, now survive a backend
# restart — verified explicitly (see README Phase 5 notes) by killing and
# restarting the process mid-pause and resuming successfully.
_checkpointer = get_checkpointer()


def _timed(name: str, node_fn):
    """
    Wrap an agent node to record its wall-clock duration into
    state["node_durations"], log it, and publish real agent_started/
    agent_completed events to Redis (spec §13) for Phase 6's streaming
    endpoint to read from.
    """
    @wraps(node_fn)
    def wrapper(state: CodePilotState) -> dict:
        task_id = state.get("task_id", "unknown")
        publish_event(task_id, "agent_started", {"agent": name})

        start = time.monotonic()
        result = node_fn(state) or {}
        duration = round(time.monotonic() - start, 3)

        durations = dict(state.get("node_durations", {}))
        durations[name] = durations.get(name, 0.0) + duration

        logs = list(result.get("execution_logs", []))
        logs.append(f"[Timing] {name} took {duration}s")

        result["node_durations"] = durations
        result["execution_logs"] = logs

        publish_event(task_id, "agent_completed", {
            "agent": name, "duration_seconds": duration,
            "status": status_value(result.get("status", state.get("status"))),
        })
        return result

    return wrapper


def _route_after_node(state: CodePilotState) -> str:
    """Common routing: if a node marked the task FAILED, stop immediately."""
    if state.get("status") == TaskStatus.FAILED:
        return "end"
    return "continue"


def _give_up_node(state: CodePilotState) -> dict:
    """
    Reached when the Test Agent still fails after MAX_DEBUG_RETRIES.
    Marks the task FAILED with a clear error rather than silently ending
    with a stale in-progress status.
    """
    settings = get_settings()
    latest = state.get("test_results", [])
    summary = latest[-1].status if latest else "unknown"
    return {
        "status": TaskStatus.FAILED,
        "errors": [
            f"Exceeded max debug retries ({settings.max_debug_retries}) "
            f"without passing tests (last test status: {summary})."
        ],
        "execution_logs": [
            f"[System] Giving up after {settings.max_debug_retries} debug retries."
        ],
    }


def _route_after_tester(state: CodePilotState) -> str:
    """
    Tests passed -> Reviewer.
    Tests failed and retries remain -> Debugger.
    Tests failed and retries exhausted -> give up (marks FAILED).
    """
    if state.get("status") == TaskStatus.FAILED:
        return "end"

    latest = state.get("test_results", [])
    if latest and latest[-1].status == "passed":
        return "passed"

    settings = get_settings()
    if state.get("retry_count", 0) >= settings.max_debug_retries:
        return "give_up"
    return "debug"


def _route_after_reviewer(state: CodePilotState) -> str:
    """approved (or review cycles exhausted) -> Human Approval. Otherwise -> Coder."""
    if state.get("status") == TaskStatus.FAILED:
        return "end"
    if state.get("status") == TaskStatus.AWAITING_APPROVAL:
        return "approve"
    return "revise"


def _route_after_approval(state: CodePilotState) -> str:
    decision = state.get("approval_status", ApprovalStatus.PENDING)
    if decision == ApprovalStatus.APPROVED:
        return "approved"
    if decision == ApprovalStatus.CHANGES_REQUESTED:
        return "revise"
    if decision == ApprovalStatus.REJECTED:
        return "rejected"
    # Still PENDING means the API hasn't resumed with a decision yet — this
    # should be unreachable because of interrupt_before, but fail safe.
    return "rejected"


def _approved_node(state: CodePilotState) -> dict:
    return {
        "status": TaskStatus.APPROVED,
        "execution_logs": ["[System] Human approved. Proceeding to Git operations."],
    }


def _rejected_node(state: CodePilotState) -> dict:
    return {
        "status": TaskStatus.REJECTED,
        "execution_logs": ["[System] Human rejected the changes. Task ended."],
    }


def build_graph():
    graph = StateGraph(CodePilotState)

    graph.add_node("planner", _timed("planner", planner_node))
    graph.add_node("explorer", _timed("explorer", explorer_node))
    graph.add_node("coder", _timed("coder", coder_node))
    graph.add_node("tester", _timed("tester", tester_node))
    graph.add_node("debugger", _timed("debugger", debugger_node))
    graph.add_node("give_up", _give_up_node)
    graph.add_node("reviewer", _timed("reviewer", reviewer_node))
    graph.add_node("human_approval", _timed("human_approval", human_approval_node))
    graph.add_node("approved", _approved_node)
    graph.add_node("rejected", _rejected_node)
    graph.add_node("git_manager", _timed("git_manager", git_manager_node))
    graph.add_node("github_pr", _timed("github_pr", github_pr_node))
    graph.add_node("finalize_report", _timed("finalize_report", final_report_node))

    graph.set_entry_point("planner")

    graph.add_conditional_edges(
        "planner", _route_after_node, {"continue": "explorer", "end": END}
    )
    graph.add_conditional_edges(
        "explorer", _route_after_node, {"continue": "coder", "end": END}
    )
    graph.add_conditional_edges(
        "coder", _route_after_node, {"continue": "tester", "end": END}
    )
    graph.add_conditional_edges(
        "tester", _route_after_tester,
        {"passed": "reviewer", "debug": "debugger", "give_up": "give_up", "end": END},
    )
    graph.add_conditional_edges(
        "debugger", _route_after_node, {"continue": "coder", "end": END}
    )
    graph.add_conditional_edges(
        "reviewer", _route_after_reviewer,
        {"approve": "human_approval", "revise": "coder", "end": END},
    )
    graph.add_conditional_edges(
        "human_approval", _route_after_approval,
        {"approved": "approved", "revise": "coder", "rejected": "rejected"},
    )
    graph.add_edge("give_up", END)
    graph.add_edge("approved", "git_manager")
    graph.add_conditional_edges(
        "git_manager", _route_after_node, {"continue": "github_pr", "end": END}
    )
    graph.add_edge("github_pr", "finalize_report")
    graph.add_edge("finalize_report", END)
    graph.add_edge("rejected", END)

    return graph.compile(checkpointer=_checkpointer, interrupt_before=["human_approval"])


codepilot_graph = build_graph()



"""
Human Approval checkpoint.

The graph is compiled with `interrupt_before=["human_approval"]`, so
execution genuinely pauses here — this node's body only runs *after* the
API layer has resumed the graph with an approval decision already written
into state (see api/routes.py: approve_task / reject_task). The node itself
just logs and passes state through unchanged; `_route_after_approval` in
graph.py does the actual branching.
"""
from __future__ import annotations

from app.state import ApprovalStatus, CodePilotState


def human_approval_node(state: CodePilotState) -> dict:
    decision = state.get("approval_status", ApprovalStatus.PENDING)
    return {
        "execution_logs": [f"[HumanApproval] Resumed with decision: {decision}"],
    }

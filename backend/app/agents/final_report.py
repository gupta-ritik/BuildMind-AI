"""
Final Report Agent.

Assembles the human-readable task summary described in spec §20/§29 —
files changed, lines added/removed, test results, review outcome, PR link,
timing — from state that every prior agent already populated. No LLM call
needed; this is pure aggregation of structured data, which is the entire
point of keeping state structured rather than free text.
"""
from __future__ import annotations

from app.state import CodePilotState, TaskStatus
from app.tools.diff_tool import diff_stats


def final_report_node(state: CodePilotState) -> dict:
    code_changes = state.get("code_changes", [])
    test_results = state.get("test_results", [])
    review = state.get("review_result")
    durations = state.get("node_durations", {})
    total_duration = round(sum(durations.values()), 2)

    added = removed = 0
    for change in code_changes:
        a, r = diff_stats(change.diff)
        added += a
        removed += r

    latest_test = test_results[-1] if test_results else None
    lines = [
        f"Task: {state['task']}",
        f"Result: {'SUCCESS' if state.get('status') != TaskStatus.FAILED else 'FAILED'}",
        f"Duration: {total_duration}s",
        f"Files changed: {len(code_changes)}",
        f"Lines added: {added}",
        f"Lines removed: {removed}",
        f"Tests: {latest_test.passed}/{(latest_test.passed + latest_test.failed) or 1} passed" if latest_test else "Tests: none run",
        f"Debug attempts: {state.get('retry_count', 0)}",
        f"Review cycles: {state.get('review_cycles', 0)}",
        f"Code review: {review.status if review else 'not reviewed'}",
        f"Commit: {state.get('commit_hash') or 'none'}",
        f"Pull request: {state.get('pull_request_url') or 'none'}",
    ]
    report = "\n".join(lines)

    return {
        "final_report": report,
        "status": TaskStatus.COMPLETED,
        "execution_logs": [f"[FinalReport]\n{report}"],
    }

"""
Code Reviewer Agent.

Runs once tests pass. Evaluates the final diff against correctness,
security, maintainability, error handling, test coverage, performance, API
compatibility, regressions, and duplication. If it finds critical issues,
sends the workflow back to the Coding Agent — bounded by
MAX_REVIEW_CYCLES so this loop cannot run forever either.
"""
from __future__ import annotations

import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_settings
from app.llm.provider import get_chat_model
from app.state import CodePilotState, ReviewResult, TaskStatus, get_plan

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are the Code Reviewer Agent inside CodePilot. Tests \
have passed. Review the final diff against the original plan.

Evaluate: correctness, security, maintainability, error handling, test \
coverage, performance, API compatibility, potential regressions, and code \
duplication.

Respond with ONLY a JSON object (no markdown fences):
{
  "status": "approved" | "changes_requested",
  "issues": ["critical problems that must be fixed before this can ship"],
  "suggestions": ["non-blocking improvements worth mentioning"]
}

Only use "changes_requested" for issues that are actually critical (security
holes, correctness bugs, broken error handling). Style nitpicks belong in
suggestions, not issues, and should not block approval.
"""


def reviewer_node(state: CodePilotState) -> dict:
    settings = get_settings()
    plan = get_plan(state)
    code_changes = state.get("code_changes", [])
    test_results = state.get("test_results", [])
    review_cycles = state.get("review_cycles", 0)

    logs = [f"[Reviewer] Reviewing {len(code_changes)} changed files (cycle {review_cycles + 1})."]

    model = get_chat_model()
    diff_summary = "\n\n".join(
        f"--- {c.path} ({c.change_type}) ---\n{c.explanation}\n{c.diff[:1500]}"
        for c in code_changes
    )
    latest_test = test_results[-1] if test_results else None

    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=(
            f"Plan goal: {plan.goal}\n"
            f"Acceptance criteria: {plan.acceptance_criteria}\n"
            f"Test result: {latest_test.status if latest_test else 'unknown'} "
            f"({latest_test.passed if latest_test else 0} passed)\n\n"
            f"Diff:\n{diff_summary}"
        )),
    ]

    try:
        response = model.invoke(messages)
        cleaned = response.content.strip().strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned.split("\n", 1)[-1]
        review = ReviewResult(**json.loads(cleaned))
        logs.append(
            f"[Reviewer] status={review.status} issues={len(review.issues)} "
            f"suggestions={len(review.suggestions)}"
        )

        if review.status == "approved":
            next_status = TaskStatus.AWAITING_APPROVAL
        elif review_cycles + 1 >= settings.max_review_cycles:
            next_status = TaskStatus.AWAITING_APPROVAL
            logs.append(
                f"[Reviewer] Max review cycles ({settings.max_review_cycles}) reached "
                "with outstanding issues — escalating to human approval rather than "
                "looping further."
            )
        else:
            next_status = TaskStatus.CODING

        return {
            "review_result": review,
            "review_cycles": review_cycles + 1,
            "status": next_status,
            "execution_logs": logs,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Code Reviewer agent failed")
        return {
            "status": TaskStatus.FAILED,
            "errors": [f"Reviewer failed: {exc}"],
            "execution_logs": logs + [f"[Reviewer] ERROR: {exc}"],
        }

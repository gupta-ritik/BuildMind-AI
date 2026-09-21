"""
Debugger Agent.

When tests fail, this agent reads the traceback/output, inspects the
relevant source files, and produces a diagnosis + a minimal, concrete fix
description. It does NOT write files itself — per the spec's workflow
(Debugger -> Coding Agent -> Test Agent), it hands its diagnosis back to
the Coding Agent as a debug note, and the Coding Agent applies the fix.
Keeping "diagnose" and "apply" as separate agents/roles, both operating
through the same controlled file tools, keeps a single place responsible
for writes.

Retries are hard-bounded by MAX_DEBUG_RETRIES so the graph can never loop
forever on a task it can't fix.
"""
from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_settings
from app.llm.provider import get_chat_model
from app.state import CodePilotState, TaskStatus, get_plan
from app.tools.file_tools import read_file

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are the Debugger Agent inside CodePilot. Tests just \
failed. You are given the test output/traceback, the plan, and the current \
content of the files that were most recently changed.

1. Identify the most likely root cause of the failure.
2. State plainly whether the failure was introduced by the recent changes \
or is a pre-existing issue.
3. Describe a minimal, concrete fix — specific enough that another engineer \
could apply it without further investigation.

Respond with ONLY a JSON object (no markdown fences):
{
  "root_cause": "...",
  "introduced_by_recent_changes": true,
  "fix_description": "specific, actionable description of the fix to apply"
}
"""


def debugger_node(state: CodePilotState) -> dict:
    settings = get_settings()
    repo_root = state["repository_path"]
    plan = get_plan(state)
    test_results = state.get("test_results", [])
    code_changes = state.get("code_changes", [])
    retry_count = state.get("retry_count", 0)

    logs = [f"[Debugger] Attempt {retry_count + 1}/{settings.max_debug_retries}."]

    if retry_count >= settings.max_debug_retries:
        logs.append("[Debugger] Max debug retries exceeded — stopping.")
        return {
            "status": TaskStatus.FAILED,
            "errors": [f"Exceeded max debug retries ({settings.max_debug_retries}) without passing tests."],
            "execution_logs": logs,
        }

    latest_result = test_results[-1] if test_results else None
    if latest_result is None:
        logs.append("[Debugger] No test results to diagnose — stopping.")
        return {
            "status": TaskStatus.FAILED,
            "errors": ["Debugger invoked with no test results available."],
            "execution_logs": logs,
        }

    changed_file_contents = {}
    for change in code_changes:
        try:
            changed_file_contents[change.path] = read_file(repo_root, change.path)
        except FileNotFoundError:
            changed_file_contents[change.path] = "(file no longer exists)"

    model = get_chat_model()
    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=(
            f"Plan goal: {plan.goal}\n\n"
            f"Test status: {latest_result.status}, "
            f"passed={latest_result.passed}, failed={latest_result.failed}\n"
            f"Failed tests: {latest_result.errors}\n\n"
            f"Test output (tail):\n{latest_result.output[-3000:]}\n\n"
            f"Recently changed files:\n{changed_file_contents}"
        )),
    ]

    try:
        response = model.invoke(messages)
        import json
        cleaned = "".join(
            character for character in response.content.strip().strip("`")
            if character in "\n\r\t" or ord(character) >= 32
        )
        if cleaned.lower().startswith("json"):
            cleaned = cleaned.split("\n", 1)[-1]
        diagnosis = json.loads(cleaned)

        note = (
            f"[Debug attempt {retry_count + 1}] Root cause: {diagnosis.get('root_cause')} "
            f"| Fix to apply: {diagnosis.get('fix_description')}"
        )
        logs.append(f"[Debugger] {note}")

        prior_notes = state.get("debug_notes", [])
        return {
            "debug_notes": prior_notes + [note],
            "retry_count": retry_count + 1,
            "status": TaskStatus.CODING,
            "execution_logs": logs,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Debugger agent failed")
        return {
            "status": TaskStatus.FAILED,
            "errors": [f"Debugger failed: {exc}"],
            "execution_logs": logs + [f"[Debugger] ERROR: {exc}"],
        }

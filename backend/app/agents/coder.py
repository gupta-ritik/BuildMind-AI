"""
Coding Agent.

Implements the approved plan against the relevant files identified by the
Explorer. Produces a concise change plan first, then writes files through
the controlled file_tools layer only (never raw filesystem access from the
LLM's output).
"""
from __future__ import annotations

import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.llm.provider import get_chat_model
from app.state import CodeChange, CodePilotState, TaskStatus, get_plan
from app.tools.diff_tool import unified_diff
from app.tools.file_tools import read_file, write_file

logger = logging.getLogger(__name__)

_MAX_CONTEXT_CHARS = 12000
_MAX_SUPPORTING_FILE_CHARS = 1800
_DOCUMENTATION_FILES = ("readme.md", "contributing.md", "changelog.md", "license")

_SYSTEM_PROMPT = """You are the Coding Agent inside CodePilot. You implement \
an approved plan by modifying or creating files. Follow the existing \
project's conventions. Avoid unnecessary refactoring. Include tests for new \
functionality.

You will be given the plan, the current content of relevant files (empty \
string if the file does not yet exist), and any debugging notes from a \
previous failed attempt.

Respond with ONLY a JSON object (no markdown fences) containing a `changes` array \
of objects, one per file \
you are creating or modifying:

{"changes": [
    {
        "path": "relative/path.py",
        "change_type": "created" | "modified",
        "full_content": "the COMPLETE new file content",
        "explanation": "one or two sentences on what changed and why"
    }
]}

Always give the full file content, not a diff or a snippet.
"""


def coder_node(state: CodePilotState) -> dict:
    repo_root = state["repository_path"]
    plan = get_plan(state)
    relevant_files = state.get("relevant_files", [])
    debug_notes = state.get("debug_notes", [])
    baselines = dict(state.get("file_baselines", {}))
    logs = [f"[Coder] Implementing plan for {len(relevant_files)} relevant files."]

    file_contents = {}
    context_chars = 0
    for rf in relevant_files:
        try:
            content = read_file(repo_root, rf.path)
        except FileNotFoundError:
            content = ""
        file_contents[rf.path] = content
        # Capture the true pre-task content exactly once, so later debug
        # passes still diff against the original rather than the last fix.
        if rf.path not in baselines:
            baselines[rf.path] = content

        remaining = _MAX_CONTEXT_CHARS - context_chars
        is_documentation = rf.path.lower().endswith(_DOCUMENTATION_FILES)
        limit = min(len(content), remaining) if is_documentation else min(
            len(content), _MAX_SUPPORTING_FILE_CHARS, remaining
        )
        excerpt = content[:limit]
        if limit < len(content):
            excerpt += "\n\n[Context truncated; preserve the existing file structure outside this excerpt.]"
        file_contents[rf.path] = excerpt
        context_chars += len(excerpt)
        if context_chars >= _MAX_CONTEXT_CHARS:
            break

    model = get_chat_model().bind(response_format={"type": "json_object"})
    context = {
        "goal": plan.goal,
        "steps": plan.steps,
        "acceptance_criteria": plan.acceptance_criteria,
        "files": file_contents,
        "debug_notes": debug_notes[-3:],
    }
    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=json.dumps(context)),
    ]

    try:
        response = model.invoke(messages)
        cleaned = response.content.strip().strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned.split("\n", 1)[-1]
        parsed = json.loads(cleaned)
        raw_changes = parsed.get("changes", []) if isinstance(parsed, dict) else parsed

        changes: list[CodeChange] = []
        for item in raw_changes:
            old_content = baselines.get(item["path"], "")
            write_file(repo_root, item["path"], item["full_content"])
            diff_text = unified_diff(old_content, item["full_content"], item["path"])
            changes.append(CodeChange(
                path=item["path"],
                change_type=item.get("change_type", "modified"),
                diff=diff_text,
                explanation=item.get("explanation", ""),
            ))
            logs.append(f"[Coder] Wrote {item['path']} ({item.get('change_type')}).")

        aggregated_diff = "\n\n".join(c.diff for c in changes)
        prior_changes = {c.path: c for c in state.get("code_changes", [])}
        prior_changes.update({c.path: c for c in changes})

        return {
            "code_changes": list(prior_changes.values()),
            "file_baselines": baselines,
            "git_diff": aggregated_diff,
            "status": TaskStatus.TESTING,
            "execution_logs": logs,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Coding agent failed")
        return {
            "status": TaskStatus.FAILED,
            "errors": [f"Coder failed: {exc}"],
            "execution_logs": logs + [f"[Coder] ERROR: {exc}"],
        }

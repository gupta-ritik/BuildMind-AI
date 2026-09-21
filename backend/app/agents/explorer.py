"""
Repository Explorer Agent.

Performs targeted retrieval: lists the repo structure, then uses the plan's
steps as search queries to find relevant files and symbols, without ever
dumping the whole repository into the LLM's context.
"""
from __future__ import annotations

import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.llm.provider import get_chat_model
from app.state import CodePilotState, RelevantFile, TaskStatus, get_plan
from app.tools.code_search import search_code
from app.tools.file_tools import list_files

logger = logging.getLogger(__name__)

_MAX_FILES_LISTED = 200

_SYSTEM_PROMPT = """You are the Repository Explorer Agent inside CodePilot. \
You are given a project's file listing, a short implementation plan, and \
some keyword search hits. Select the files that are actually relevant to \
implementing the plan.

Respond with ONLY a JSON array (no markdown fences) of objects:
[{"path": "relative/path.py", "reason": "why this file matters"}]

Pick at most 12 files. Prefer precision over recall.
"""


def explorer_node(state: CodePilotState) -> dict:
    repo_root = state["repository_path"]
    plan = get_plan(state)
    logs = ["[Explorer] Scanning repository structure."]

    files = list_files(repo_root, max_entries=_MAX_FILES_LISTED)
    logs.append(f"[Explorer] Found {len(files)} files (capped at {_MAX_FILES_LISTED}).")

    search_hits: list[str] = []
    for step in plan.steps[:5]:
        keywords = [w for w in step.split() if len(w) > 3][:3]
        for kw in keywords:
            hits = search_code(repo_root, kw, max_results=5)
            search_hits.extend(f"{h.path}:{h.line_number}: {h.line}" for h in hits)

    model = get_chat_model()
    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=(
            f"Plan goal: {plan.goal}\n"
            f"Plan steps: {plan.steps}\n\n"
            f"File listing ({len(files)} files):\n" + "\n".join(files[:_MAX_FILES_LISTED]) +
            "\n\nKeyword search hits:\n" + "\n".join(search_hits[:60])
        )),
    ]

    try:
        response = model.invoke(messages)
        cleaned = response.content.strip().strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned.split("\n", 1)[-1]
        raw_files = json.loads(cleaned)
        relevant = [RelevantFile(**f) for f in raw_files]
        logs.append(f"[Explorer] Selected {len(relevant)} relevant files.")
        return {
            "relevant_files": relevant,
            "status": TaskStatus.CODING,
            "execution_logs": logs,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Explorer agent failed")
        return {
            "status": TaskStatus.FAILED,
            "errors": [f"Explorer failed: {exc}"],
            "execution_logs": logs + [f"[Explorer] ERROR: {exc}"],
        }

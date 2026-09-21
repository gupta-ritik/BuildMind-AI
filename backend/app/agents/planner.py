"""
Planner Agent.

Turns a natural-language task into a structured, actionable plan with
acceptance criteria and identified risks. Nothing downstream should have
to re-interpret free text where this structured Plan will do.
"""
from __future__ import annotations

import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.llm.provider import get_chat_model
from app.state import CodePilotState, Plan, TaskStatus

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are the Planner Agent inside CodePilot, an autonomous \
software engineering system. Given a software development task, produce a \
concise, actionable implementation plan.

Respond with ONLY a JSON object (no markdown fences, no commentary) matching \
this exact schema:

{
  "goal": "one sentence restating the objective",
  "steps": ["ordered, concrete implementation steps"],
  "acceptance_criteria": ["testable conditions that define success"],
  "risks": ["things that could go wrong or need care"]
}
"""


def _parse_plan_json(raw: str) -> Plan:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.split("\n", 1)[-1] if cleaned.lower().startswith("json") else cleaned
    data = json.loads(cleaned)
    return Plan(**data)


def planner_node(state: CodePilotState) -> dict:
    task = state["task"]
    logs = [f"[Planner] Received task: {task!r}"]

    model = get_chat_model()
    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=f"Task: {task}"),
    ]

    try:
        response = model.invoke(messages)
        plan = _parse_plan_json(response.content)
        logs.append(f"[Planner] Produced plan with {len(plan.steps)} steps.")
        return {
            "plan": plan,
            "status": TaskStatus.EXPLORING,
            "execution_logs": logs,
        }
    except Exception as exc:  # noqa: BLE001 - agent failures must not crash the graph
        logger.exception("Planner agent failed")
        return {
            "status": TaskStatus.FAILED,
            "errors": [f"Planner failed: {exc}"],
            "execution_logs": logs + [f"[Planner] ERROR: {exc}"],
        }

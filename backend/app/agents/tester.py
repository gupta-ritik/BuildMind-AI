"""
Test Agent.

Runs the project's test suite and returns structured results. In Phase 1
this runs via a restricted local subprocess; Phase 2 swaps in Docker
execution behind the same run_tests() call. Phase 5 adds a repository-
memory cache (Redis) for the detected test framework, so repeat tasks
against the same repo skip re-detection.
"""
from __future__ import annotations

import hashlib

from app.cache.redis_client import cache_repository_memory, get_repository_memory
from app.config import get_settings
from app.state import CodePilotState, TaskStatus
from app.tools.test_runner import detect_test_framework, run_tests


def _repo_key(repo_root: str) -> str:
    return hashlib.sha256(repo_root.encode()).hexdigest()[:16]


def tester_node(state: CodePilotState) -> dict:
    repo_root = state["repository_path"]
    settings = get_settings()
    logs = ["[Tester] Running test suite."]

    repo_key = _repo_key(repo_root)
    memory = get_repository_memory(repo_key) or {}
    framework = memory.get("test_framework")
    if framework:
        logs.append(f"[Tester] Using cached test framework: {framework}")
    else:
        framework = detect_test_framework(repo_root)
        memory["test_framework"] = framework
        cache_repository_memory(repo_key, memory)
        logs.append(f"[Tester] Detected and cached test framework: {framework}")

    result = run_tests(repo_root, timeout_seconds=settings.tool_timeout_seconds)
    prior_results = state.get("test_results", [])

    logs.append(
        f"[Tester] status={result.status} passed={result.passed} "
        f"failed={result.failed} duration={result.duration_seconds}s"
    )

    if result.status == "passed":
        next_status = TaskStatus.REVIEWING
    else:
        next_status = TaskStatus.DEBUGGING

    return {
        "test_results": prior_results + [result],
        "status": next_status,
        "execution_logs": logs,
    }

"""
Test execution tool.

Tries the Docker sandbox first (see docker_sandbox.py) so test execution is
isolated per spec §7. If no Docker daemon is reachable, falls back to a
timeout-bounded local subprocess and logs clearly that the sandboxed path
was not used, so this stays runnable in dev environments without Docker
while never silently pretending isolation happened when it didn't.
"""
from __future__ import annotations

import logging
import re
import subprocess
import time
from pathlib import Path

from app.config import get_settings
from app.state import TestResult
from app.tools import docker_sandbox

logger = logging.getLogger(__name__)

_FAILED_LINE = "FAILED "
_TEST_COMMAND = ["python", "-m", "pytest", "-q", "--tb=short"]


def _no_tests_collected(output: str, exit_code: int) -> bool:
    return exit_code == 5 and ("no tests ran" in output.lower() or "collected 0 items" in output.lower())


def detect_test_framework(repo_root: str) -> str:
    from pathlib import Path
    root = Path(repo_root)
    if (root / "pytest.ini").exists() or (root / "pyproject.toml").exists() or any(root.rglob("test_*.py")):
        return "pytest"
    if (root / "package.json").exists():
        return "npm"
    return "unknown"


def _parse_pytest_output(output: str) -> tuple[int, int, list[str]]:
    failed_tests = [line for line in output.splitlines() if line.startswith(_FAILED_LINE)]
    passed = failed = 0
    summary_pattern = re.compile(r"(\d+)\s+(passed|failed|error(?:s)?)")
    for line in output.splitlines():
        if "passed" in line or "failed" in line or "error" in line:
            for count_str, label in summary_pattern.findall(line):
                if label == "passed":
                    passed = int(count_str)
                elif label.startswith("failed"):
                    failed = int(count_str)
    return passed, failed, failed_tests


def _run_via_docker(repo_root: str, timeout_seconds: int, target: str | None) -> TestResult:
    cmd = _TEST_COMMAND + ([target] if target else [])
    start = time.monotonic()
    try:
        result = docker_sandbox.run_in_sandbox(repo_root, cmd, timeout_seconds=timeout_seconds)
    except docker_sandbox.SandboxTimeout as exc:
        return TestResult(
            status="error",
            errors=[str(exc)],
            duration_seconds=round(time.monotonic() - start, 2),
        )
    duration = time.monotonic() - start
    output = result.stdout + "\n" + result.stderr
    passed, failed, failed_tests = _parse_pytest_output(output)
    status = "passed" if result.exit_code == 0 or _no_tests_collected(output, result.exit_code) else "failed"
    return TestResult(
        status=status,
        passed=passed,
        failed=failed if failed else len(failed_tests),
        errors=failed_tests,
        output=output[-8000:],
        duration_seconds=round(duration, 2),
    )


def _run_via_subprocess(repo_root: str, timeout_seconds: int, target: str | None) -> TestResult:
    cmd = _TEST_COMMAND + ([target] if target else [])
    start = time.monotonic()
    try:
        proc = subprocess.run(
            cmd, cwd=repo_root, capture_output=True, text=True, timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return TestResult(
            status="error",
            errors=[f"Test run exceeded {timeout_seconds}s timeout."],
            output=(exc.stdout or "") + (exc.stderr or ""),
            duration_seconds=timeout_seconds,
        )
    duration = time.monotonic() - start
    output = proc.stdout + "\n" + proc.stderr
    passed, failed, failed_tests = _parse_pytest_output(output)
    status = "passed" if proc.returncode == 0 or _no_tests_collected(output, proc.returncode) else "failed"
    return TestResult(
        status=status,
        passed=passed,
        failed=failed if failed else len(failed_tests),
        errors=failed_tests,
        output=output[-8000:],
        duration_seconds=round(duration, 2),
    )


def run_tests(repo_root: str, timeout_seconds: int = 60, target: str | None = None) -> TestResult:
    """
    Run the test suite (or a specific target) and return structured results.

    Uses the Docker sandbox when a daemon is available; otherwise falls back
    to a local, timeout-bounded subprocess and logs that fallback happened.
    """
    settings = get_settings()
    framework = detect_test_framework(repo_root)
    if framework != "pytest":
        if framework == "unknown":
            python_files = list(Path(repo_root).rglob("*.py"))
            try:
                subprocess.run(
                    ["python", "-m", "compileall", "-q", *[str(path) for path in python_files]],
                    cwd=repo_root,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    check=True,
                )
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                output = getattr(exc, "stdout", "") or ""
                output += getattr(exc, "stderr", "") or ""
                return TestResult(status="failed", errors=[output.strip() or "Python syntax check failed."], output=output)
            return TestResult(
                status="passed",
                output="No supported test framework detected; Python compile check passed.",
            )
        return TestResult(
            status="error",
            errors=[f"Unsupported or undetected test framework: {framework}"],
        )

    if docker_sandbox.is_available(settings):
        logger.info("Running tests inside Docker sandbox.")
        return _run_via_docker(repo_root, timeout_seconds, target)

    logger.warning(
        "Docker sandbox not available (no reachable daemon) — "
        "falling back to local subprocess execution. This is NOT isolated; "
        "do not point this at an untrusted repository in this mode."
    )
    return _run_via_subprocess(repo_root, timeout_seconds, target)


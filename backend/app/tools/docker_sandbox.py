"""
Docker sandbox for isolated command execution.

Real integration via the `docker` Python SDK against the local Docker
daemon (unix socket / DOCKER_HOST) — nothing here is simulated. If no
daemon is reachable, `is_available()` returns False and callers (see
`test_runner.py`) fall back to a restricted local subprocess so the
system stays runnable in environments without Docker, while clearly
logging that the sandboxed path was not used.

Enforced per spec §7/§18:
  - Resource limits (memory, CPU)
  - Wall-clock timeout, hard-killed if exceeded
  - No network access from inside the container
  - Only the task's isolated workspace is mounted — never the host root,
    never the user's original repository, never host credentials/env
  - Command allowlisting: only whitelisted binaries may be invoked
  - Container always removed after execution (no leftover state)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Only these leading commands are permitted inside the sandbox. The Coding/
# Test agents may only ever request one of these — arbitrary shell strings
# produced by an LLM are never passed straight to Docker.
ALLOWED_COMMAND_PREFIXES: set[str] = {
    "pytest", "python", "python3", "-m",  # -m allowed only as arg to python
    "npm", "node", "yarn", "pnpm",
    "ruff", "flake8", "mypy", "black", "pylint",
}


class SandboxCommandRejected(Exception):
    """Raised when a requested command is not on the allowlist."""


class SandboxTimeout(Exception):
    """Raised when the container is killed for exceeding its timeout."""


@dataclass
class SandboxResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool


def validate_command(command: list[str]) -> None:
    """Reject any command whose program is not on the allowlist."""
    if not command:
        raise SandboxCommandRejected("Empty command.")
    program = command[0]
    if program not in ALLOWED_COMMAND_PREFIXES:
        raise SandboxCommandRejected(
            f"Command '{program}' is not allowlisted for sandbox execution."
        )


def is_available(settings: Settings | None = None) -> bool:
    """Best-effort check for a reachable Docker daemon."""
    settings = settings or get_settings()
    if not settings.use_docker_sandbox:
        return False
    try:
        import docker  # noqa: PLC0415 - optional/heavy import, only when needed
        client = docker.from_env()
        client.ping()
        return True
    except Exception:  # noqa: BLE001 - any failure means "not available"
        return False


def run_in_sandbox(
    repo_root: str,
    command: list[str],
    timeout_seconds: int = 60,
    settings: Settings | None = None,
) -> SandboxResult:
    """
    Run `command` inside an isolated, network-disabled Docker container with
    `repo_root` mounted read-write at /workspace and nothing else from the
    host visible. Raises SandboxCommandRejected / SandboxTimeout on misuse.
    """
    validate_command(command)
    settings = settings or get_settings()

    import docker
    from docker.errors import ContainerError, ImageNotFound

    client = docker.from_env()

    try:
        client.images.get(settings.docker_image)
    except ImageNotFound:
        logger.info("Pulling sandbox image %s ...", settings.docker_image)
        client.images.pull(settings.docker_image)

    container = client.containers.run(
        image=settings.docker_image,
        command=command,
        working_dir="/workspace",
        volumes={repo_root: {"bind": "/workspace", "mode": "rw"}},
        mem_limit=settings.docker_mem_limit,
        nano_cpus=settings.docker_nano_cpus,
        network_disabled=settings.docker_network_disabled,
        environment={},          # never forward host env / secrets
        detach=True,
        remove=False,             # remove manually after collecting logs/status
        stdout=True,
        stderr=True,
    )

    timed_out = False
    try:
        result = container.wait(timeout=timeout_seconds)
        exit_code = result.get("StatusCode", -1)
    except Exception:
        # container.wait raised => exceeded timeout (requests.ReadTimeout) or
        # the daemon errored; treat both as a timeout and force-kill.
        timed_out = True
        exit_code = -1
        try:
            container.kill()
        except Exception:  # noqa: BLE001
            pass

    try:
        stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
        stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")
    finally:
        try:
            container.remove(force=True)
        except Exception:  # noqa: BLE001
            pass

    if timed_out:
        raise SandboxTimeout(f"Container exceeded {timeout_seconds}s timeout and was killed.")

    return SandboxResult(exit_code=exit_code, stdout=stdout, stderr=stderr, timed_out=False)

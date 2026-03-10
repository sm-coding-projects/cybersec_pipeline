"""Pipeline utility functions — retry logic, output validation, timeout handling.

Provides reusable helpers for tool execution within pipeline phases.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, TYPE_CHECKING

from app.core.exceptions import ToolExecutionError
from app.services.docker_manager import DockerManager

if TYPE_CHECKING:
    from app.pipeline.engine import EventEmitter

logger = logging.getLogger(__name__)

# Error substrings that indicate a transient (retryable) failure.
TRANSIENT_ERROR_PATTERNS: list[str] = [
    "connection refused",
    "connection reset",
    "container not running",
    "not found. Is it running",
    "timeout",
    "timed out",
    "temporary failure",
    "resource temporarily unavailable",
    "service unavailable",
    "502 bad gateway",
    "503 service unavailable",
    "no such container",
    "could not connect",
    "broken pipe",
    "eof",
    "docker api error",
]


def _is_transient_error(error: Exception) -> bool:
    """Determine whether an exception is likely a transient failure.

    Checks the exception message against known transient error patterns.
    Also treats ``ToolExecutionError`` with certain exit codes as transient
    (e.g. 137 = OOM-killed, 143 = SIGTERM, 125 = container failed to start).
    """
    error_msg = str(error).lower()
    for pattern in TRANSIENT_ERROR_PATTERNS:
        if pattern in error_msg:
            return True

    if isinstance(error, ToolExecutionError):
        # 137 = OOM killed, 143 = SIGTERM, 125 = container startup failure
        if error.exit_code in (125, 137, 143):
            return True

    return False


async def retry_tool_exec(
    docker: DockerManager,
    container: str,
    command: str,
    max_retries: int = 2,
    delay: float = 5.0,
    timeout: int = 600,
    workdir: str | None = None,
) -> tuple[int, str]:
    """Execute a Docker command with automatic retry on transient failures.

    Parameters
    ----------
    docker:
        The ``DockerManager`` instance to use for execution.
    container:
        Name of the Docker container to exec into.
    command:
        The shell command to run.
    max_retries:
        Maximum number of retry attempts (in addition to the initial attempt).
    delay:
        Seconds to wait between retry attempts.
    timeout:
        Timeout in seconds for the Docker exec call.
    workdir:
        Optional working directory inside the container.

    Returns
    -------
    tuple[int, str]
        ``(exit_code, combined_output)`` from the last successful or final attempt.

    Raises
    ------
    ToolExecutionError
        If all attempts fail with a transient error, the last error is raised.
        Non-transient errors are raised immediately without retrying.
    """
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 2):  # +2 because range is exclusive and we want max_retries + 1 total
        try:
            exit_code, output = await docker.exec_in_container(
                container=container,
                command=command,
                timeout=timeout,
                workdir=workdir,
            )
            # If the command succeeded (exit 0), return immediately
            if exit_code == 0:
                if attempt > 1:
                    logger.info(
                        "Command succeeded on attempt %d/%d in container %s",
                        attempt,
                        max_retries + 1,
                        container,
                    )
                return exit_code, output

            # Non-zero exit code — create an error to evaluate retryability
            error = ToolExecutionError(
                tool=container,
                message=f"Command failed (exit {exit_code}): {output[-200:]}",
                exit_code=exit_code,
            )
            if not _is_transient_error(error):
                # Non-transient failure — return the result, don't retry
                return exit_code, output

            last_error = error
            if attempt <= max_retries:
                logger.warning(
                    "Transient failure in %s (attempt %d/%d, exit %d) — retrying in %.1fs",
                    container,
                    attempt,
                    max_retries + 1,
                    exit_code,
                    delay,
                )
                await asyncio.sleep(delay)

        except ToolExecutionError as exc:
            if not _is_transient_error(exc):
                raise
            last_error = exc
            if attempt <= max_retries:
                logger.warning(
                    "Transient error in %s (attempt %d/%d): %s — retrying in %.1fs",
                    container,
                    attempt,
                    max_retries + 1,
                    str(exc)[:200],
                    delay,
                )
                await asyncio.sleep(delay)

    # All retries exhausted
    if last_error is not None:
        logger.error(
            "All %d attempts failed for command in container %s",
            max_retries + 1,
            container,
        )
        raise last_error

    # Should not reach here, but satisfy type checker
    raise ToolExecutionError(tool=container, message="All retry attempts exhausted")


async def validate_tool_output(
    docker: DockerManager,
    container: str,
    output_file: str,
    tool_name: str,
    required: bool = False,
) -> bool:
    """Validate that a tool produced an output file and it is non-empty.

    Parameters
    ----------
    docker:
        The ``DockerManager`` instance.
    container:
        Container name where the output file resides.
    output_file:
        Full path to the expected output file inside the container.
    tool_name:
        Human-readable tool name for log messages.
    required:
        If ``True``, raises ``ToolExecutionError`` when the file is
        missing or empty.  If ``False`` (the default), logs a warning
        and returns ``False``.

    Returns
    -------
    bool
        ``True`` if the file exists and is non-empty, ``False`` otherwise.
    """
    try:
        exit_code, output = await docker.exec_in_container(
            container,
            f"test -s {output_file} && echo EXISTS || echo MISSING",
            timeout=30,
        )
        if "EXISTS" in output:
            logger.debug("Output file validated for %s: %s", tool_name, output_file)
            return True

        msg = f"{tool_name} output file missing or empty: {output_file}"
        if required:
            raise ToolExecutionError(tool=tool_name, message=msg)
        logger.warning(msg)
        return False

    except ToolExecutionError:
        if required:
            raise
        logger.warning("Could not validate output file for %s: %s", tool_name, output_file)
        return False


async def emit_tool_output(emitter: "EventEmitter", tool: str, output: str) -> None:
    """Emit a tool's stdout/stderr as individual tool_log events.

    Called after exec_in_container returns so that the output is visible
    in the live log panel.  Limits to the last 200 lines to avoid flooding
    the WebSocket connection.
    """
    if not output:
        return
    lines = [line for line in output.splitlines() if line.strip()]
    for line in lines[-200:]:
        await emitter.emit("tool_log", {"tool": tool, "line": line})


class ToolTimeout(Exception):
    """Raised when a tool execution exceeds its timeout."""

    def __init__(self, tool: str, timeout_seconds: int) -> None:
        self.tool = tool
        self.timeout_seconds = timeout_seconds
        super().__init__(f"{tool} timed out after {timeout_seconds}s")


async def exec_with_timeout(
    docker: DockerManager,
    container: str,
    command: str,
    timeout: int = 600,
    workdir: str | None = None,
) -> tuple[int, str]:
    """Execute a Docker command with an explicit asyncio timeout.

    If the command takes longer than *timeout* seconds, it is cancelled
    and a ``ToolTimeout`` is raised.  This provides a Python-level guard
    on top of the Docker SDK's own timeout parameter.

    Parameters
    ----------
    docker:
        The ``DockerManager`` instance.
    container:
        Container name.
    command:
        Shell command to run.
    timeout:
        Maximum wall-clock seconds to wait.
    workdir:
        Optional working directory inside the container.

    Returns
    -------
    tuple[int, str]
        ``(exit_code, output)`` on success.

    Raises
    ------
    ToolTimeout
        If the execution exceeds *timeout* seconds.
    """
    try:
        result = await asyncio.wait_for(
            docker.exec_in_container(
                container=container,
                command=command,
                timeout=timeout,
                workdir=workdir,
            ),
            timeout=timeout + 30,  # Give a small buffer beyond the Docker SDK timeout
        )
        return result
    except asyncio.TimeoutError:
        logger.error(
            "Tool execution timed out: container=%s, timeout=%ds, command=%s",
            container,
            timeout,
            command[:200],
        )
        # Attempt to kill the running process inside the container
        try:
            await docker.exec_in_container(container, "pkill -f " + command.split()[0], timeout=10)
        except Exception:
            logger.warning("Could not kill timed-out process in %s", container)
        raise ToolTimeout(tool=container, timeout_seconds=timeout)

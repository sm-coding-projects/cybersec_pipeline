"""Docker SDK wrapper for communicating with tool containers.

All tool interactions go through this class. Uses docker-py, NOT subprocess calls.
The Docker socket is mounted into the backend and celery-worker containers.
"""

from __future__ import annotations

import asyncio
import logging
import shlex
from typing import Any

import docker
from docker.errors import APIError, NotFound

from app.core.exceptions import ToolExecutionError

logger = logging.getLogger(__name__)

# Tool containers that the pipeline interacts with.
TOOL_CONTAINERS: list[str] = [
    "theharvester",
    "amass",
    "dnsx",
    "nmap-scanner",
    "httpx",
    "nuclei",
    "zap",
    "defectdojo-nginx",
    "defectdojo-web",
]


class DockerManager:
    """Manages communication with tool containers via the Docker SDK."""

    def __init__(self) -> None:
        self.client: docker.DockerClient = docker.DockerClient.from_env()

    # ── Execute ──────────────────────────────────────────────────────────

    async def exec_in_container(
        self,
        container: str,
        command: str,
        timeout: int = 600,
        workdir: str | None = None,
    ) -> tuple[int, str]:
        """Execute a command inside a running container.

        Runs the blocking docker-py ``exec_run`` call in a thread-pool executor
        so the asyncio event loop is **never blocked**.  This enables true
        concurrency when multiple tools run under ``asyncio.gather`` (e.g.
        theHarvester + Amass in parallel during Phase 1).

        ``asyncio.wait_for`` enforces the *timeout*; on expiry the process
        inside the container is killed via ``pkill`` and a ``ToolExecutionError``
        is raised so the pipeline can handle the failure gracefully.

        Returns ``(exit_code, combined_output)`` where *combined_output* is
        stdout + stderr decoded as UTF-8.
        """
        try:
            container_obj = self.client.containers.get(container)
        except NotFound:
            raise ToolExecutionError(
                tool=container,
                message=f"Container '{container}' not found. Is it running?",
            )
        except APIError as exc:
            raise ToolExecutionError(
                tool=container,
                message=f"Docker API error for '{container}': {exc}",
            )

        exec_kwargs: dict[str, Any] = {
            "cmd": ["sh", "-c", command],
            "demux": True,
        }
        if workdir is not None:
            exec_kwargs["workdir"] = workdir

        logger.debug("Exec in %s: %s", container, command)
        loop = asyncio.get_running_loop()

        try:
            exec_result = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: container_obj.exec_run(**exec_kwargs)),
                timeout=float(timeout),
            )
        except asyncio.TimeoutError:
            # Kill the timed-out process inside the container, then raise.
            tool_binary = shlex.quote(command.split()[0].split("/")[-1])
            logger.warning(
                "exec_in_container timed out after %ds in '%s' — killing '%s'",
                timeout,
                container,
                tool_binary,
            )

            async def _kill() -> None:
                try:
                    await loop.run_in_executor(
                        None,
                        lambda: container_obj.exec_run(
                            cmd=["sh", "-c", f"pkill -9 -f {tool_binary} 2>/dev/null; true"],
                            demux=False,
                        ),
                    )
                except Exception:
                    pass

            asyncio.create_task(_kill())
            raise ToolExecutionError(
                tool=container,
                message=f"Command timed out after {timeout}s: {command[:120]}",
                exit_code=124,
            )
        except APIError as exc:
            raise ToolExecutionError(
                tool=container,
                message=f"Docker API error for '{container}': {exc}",
            )

        stdout = (exec_result.output[0] or b"").decode("utf-8", errors="replace")
        stderr = (exec_result.output[1] or b"").decode("utf-8", errors="replace")
        combined = stdout + stderr

        if exec_result.exit_code != 0:
            logger.warning(
                "Container %s command exited %d: %s",
                container,
                exec_result.exit_code,
                combined[-500:],
            )

        return exec_result.exit_code, combined

    # ── Container status ─────────────────────────────────────────────────

    def get_container_status(self, container_name: str) -> dict[str, Any]:
        """Return a status dict for a single container."""
        try:
            container = self.client.containers.get(container_name)
            state = container.attrs.get("State", {})
            return {
                "name": container_name,
                "status": container.status,
                "running": container.status == "running",
                "uptime": state.get("StartedAt", ""),
                "health": state.get("Health", {}).get("Status", "unknown"),
            }
        except NotFound:
            return {
                "name": container_name,
                "status": "not_found",
                "running": False,
                "uptime": "",
                "health": "unknown",
            }
        except APIError as exc:
            logger.error("Docker API error checking %s: %s", container_name, exc)
            return {
                "name": container_name,
                "status": "error",
                "running": False,
                "uptime": "",
                "health": "unknown",
            }

    def get_all_tool_statuses(self) -> list[dict[str, Any]]:
        """Return the health status of every tool container."""
        return [self.get_container_status(name) for name in TOOL_CONTAINERS]

    # ── File helpers ─────────────────────────────────────────────────────

    async def read_file_from_container(self, container: str, filepath: str) -> str:
        """Read the contents of a file inside a container.

        This is useful when reading tool output from shared volumes.
        """
        exit_code, output = await self.exec_in_container(container, f"cat {filepath}")
        if exit_code != 0:
            raise ToolExecutionError(
                tool=container,
                message=f"Cannot read {filepath} from {container}: {output}",
                exit_code=exit_code,
            )
        return output

    # ── Lifecycle ────────────────────────────────────────────────────────

    def close(self) -> None:
        """Close the underlying Docker client connection."""
        try:
            self.client.close()
        except Exception:  # noqa: BLE001
            pass

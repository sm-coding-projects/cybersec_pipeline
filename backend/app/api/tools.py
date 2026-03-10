"""Tool status API endpoints.

Provides health checks for all tool containers and the ability to test
individual tools or trigger updates.
All endpoints require JWT authentication.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import get_current_user
from app.models.user import User
from app.schemas.finding import ToolStatusItem, ToolStatusResponse
from app.services.docker_manager import TOOL_CONTAINERS, DockerManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tools", tags=["tools"])


def _get_docker_manager() -> DockerManager:
    """Create a DockerManager instance."""
    return DockerManager()


@router.get("/status", response_model=ToolStatusResponse)
async def get_tool_status(
    current_user: User = Depends(get_current_user),
) -> ToolStatusResponse:
    """Get the health status of all tool containers.

    Returns the running state, uptime, and optional API reachability
    for each container used in the pipeline.
    """
    dm = _get_docker_manager()
    try:
        statuses = dm.get_all_tool_statuses()
        items = []
        for s in statuses:
            items.append(
                ToolStatusItem(
                    name=s["name"],
                    container=s["name"],
                    status=s["status"],
                    running=s["running"],
                    uptime=s.get("uptime", ""),
                    api_reachable=None,
                )
            )
        return ToolStatusResponse(tools=items)
    except Exception as exc:
        logger.exception("Failed to get tool statuses")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Cannot connect to Docker: {exc}",
        ) from exc
    finally:
        dm.close()


@router.post("/{tool_name}/test")
async def test_tool(
    tool_name: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Run a quick connectivity test on a specific tool container.

    Executes a simple command inside the container to verify it is
    responsive and functional.
    """
    if tool_name not in TOOL_CONTAINERS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown tool: {tool_name}. Available: {', '.join(TOOL_CONTAINERS)}",
        )

    # Simple test commands per tool
    test_commands: dict[str, str] = {
        "theharvester": "theHarvester --help 2>&1 | head -5",
        "amass": "amass --version 2>&1",
        "dnsx": "dnsx -version 2>&1",
        "nmap-scanner": "nmap --version 2>&1 | head -2",
        "httpx": "httpx -version 2>&1",
        "nuclei": "nuclei -version 2>&1",
        "zap": "curl -s http://localhost:8090/JSON/core/view/version/ 2>&1 | head -5",
        "defectdojo-nginx": "curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/ 2>&1",
        "defectdojo-web": "python -c 'print(\"ok\")' 2>&1",
    }

    command = test_commands.get(tool_name, "echo ok")

    dm = _get_docker_manager()
    try:
        exit_code, output = await dm.exec_in_container(tool_name, command, timeout=30)
        return {
            "tool": tool_name,
            "success": exit_code == 0,
            "exit_code": exit_code,
            "output": output[:2000],
        }
    except Exception as exc:
        return {
            "tool": tool_name,
            "success": False,
            "exit_code": -1,
            "output": str(exc),
        }
    finally:
        dm.close()


@router.post("/nuclei/update-templates")
async def update_nuclei_templates(
    current_user: User = Depends(get_current_user),
) -> dict:
    """Trigger a Nuclei template update inside the nuclei container.

    This downloads the latest community templates from
    projectdiscovery/nuclei-templates.
    """
    dm = _get_docker_manager()
    try:
        exit_code, output = await dm.exec_in_container(
            "nuclei",
            "nuclei -update-templates 2>&1",
            timeout=120,
        )
        return {
            "success": exit_code == 0,
            "exit_code": exit_code,
            "output": output[:5000],
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Failed to update templates: {exc}",
        ) from exc
    finally:
        dm.close()

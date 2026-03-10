from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.dashboard import router as dashboard_router
from app.api.findings import router as findings_router
from app.api.scans import router as scans_router
from app.api.targets import router as targets_router
from app.api.tools import router as tools_router

api_router = APIRouter(prefix="/api/v1")

# Auth routes
api_router.include_router(auth_router)

# Scan routes
api_router.include_router(scans_router)

# Target routes (nested under /scans/{scan_id})
api_router.include_router(targets_router)

# Finding routes (both nested /scans/{scan_id}/findings and top-level /findings)
api_router.include_router(findings_router)

# Dashboard routes
api_router.include_router(dashboard_router)

# Tool status routes
api_router.include_router(tools_router)

# Note: The WebSocket route (/ws/scans/{scan_id}) is registered directly
# on the FastAPI app in main.py, NOT under the /api/v1 prefix.

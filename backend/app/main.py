import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.ws import router as ws_router
from app.config import settings
from app.database import engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    logger.info("Starting CyberSec Pipeline backend...")
    logger.info("Database URL: %s", settings.database_url.split("@")[-1])  # Log host only, not creds
    logger.info("Redis URL: %s", settings.redis_url)
    yield
    logger.info("Shutting down CyberSec Pipeline backend...")
    await engine.dispose()


app = FastAPI(
    title="CyberSec Pipeline API",
    description="Automated cybersecurity reconnaissance and vulnerability assessment platform",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# CORS middleware — allow frontend dev server and production origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # Vite dev server
        "http://localhost:80",     # Nginx production
        "http://localhost",        # Nginx production (no port)
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],  # Expose download headers to browser JS
)

# Include all API routes
app.include_router(api_router)

# WebSocket route registered directly on the app (not under /api/v1 prefix)
app.include_router(ws_router)


@app.get("/api/v1/health", tags=["health"])
async def health_check() -> dict:
    """Health check endpoint. Returns 200 if the API is running."""
    return {
        "status": "healthy",
        "service": "cybersec-pipeline",
        "version": "1.0.0",
    }

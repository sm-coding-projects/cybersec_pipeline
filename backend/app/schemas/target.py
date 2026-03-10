from datetime import datetime

from pydantic import BaseModel

from app.models.base import TargetType


class TargetResponse(BaseModel):
    id: int
    scan_id: int
    target_type: TargetType
    value: str
    source_tool: str
    is_live: bool
    resolved_ips: list[str] | None = None
    open_ports: list[dict] | None = None
    http_status: int | None = None
    http_title: str | None = None
    technologies: list[str] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class TargetListResponse(BaseModel):
    items: list[TargetResponse]
    total: int
    page: int
    per_page: int


class TargetStatsResponse(BaseModel):
    total: int
    subdomains: int
    ips: int
    emails: int
    urls: int
    live: int

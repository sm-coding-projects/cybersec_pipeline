from datetime import datetime

from pydantic import BaseModel, Field

from app.models.base import FindingStatus, Severity


class FindingResponse(BaseModel):
    id: int
    scan_id: int
    target_id: int | None = None
    title: str
    severity: Severity
    source_tool: str
    template_id: str | None = None
    description: str
    evidence: str | None = None
    remediation: str | None = None
    reference_urls: list[str] = []
    affected_url: str | None = None
    affected_host: str | None = None
    affected_port: int | None = None
    status: FindingStatus
    is_duplicate: bool
    defectdojo_id: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FindingListResponse(BaseModel):
    items: list[FindingResponse]
    total: int
    page: int
    per_page: int


class FindingUpdate(BaseModel):
    status: FindingStatus | None = None
    is_duplicate: bool | None = None


class DashboardStatsResponse(BaseModel):
    total_scans: int
    active_scans: int
    total_findings: int
    critical_findings: int
    high_findings: int
    medium_findings: int
    low_findings: int
    info_findings: int
    total_targets_discovered: int
    unique_ips: int
    unique_subdomains: int


class SeverityBreakdownItem(BaseModel):
    severity: str
    count: int


class SeverityBreakdownResponse(BaseModel):
    items: list[SeverityBreakdownItem]


class ScanTimelineItem(BaseModel):
    id: int
    scan_uid: str
    target_domain: str
    status: str
    created_at: datetime
    completed_at: datetime | None = None


class ScanTimelineResponse(BaseModel):
    items: list[ScanTimelineItem]


class TopFindingItem(BaseModel):
    title: str
    count: int
    severity: str


class TopFindingsResponse(BaseModel):
    items: list[TopFindingItem]


class ToolStatusItem(BaseModel):
    name: str
    container: str
    status: str
    running: bool = False
    uptime: str = ""
    api_reachable: bool | None = None


class ToolStatusResponse(BaseModel):
    tools: list[ToolStatusItem]

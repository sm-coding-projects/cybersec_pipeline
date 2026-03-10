from datetime import datetime

from pydantic import BaseModel, Field

from app.models.base import PhaseStatus, ScanStatus


class ScanConfig(BaseModel):
    harvester_sources: str = "bing,crtsh,dnsdumpster"
    amass_timeout_minutes: int = Field(default=15, ge=1, le=60)
    masscan_rate: int = Field(default=10000, ge=100, le=100000)
    masscan_ports: str = "1-65535"
    nmap_scripts: str = "default,vuln"
    nuclei_severity: list[str] = Field(default=["low", "medium", "high", "critical"])
    nuclei_rate_limit: int = Field(default=150, ge=10, le=1000)
    enable_zap: bool = True
    enable_openvas: bool = False
    push_to_defectdojo: bool = True


class ScanCreate(BaseModel):
    target_domain: str = Field(..., min_length=3, max_length=255)
    config: ScanConfig = Field(default_factory=ScanConfig)


class ScanPhaseResponse(BaseModel):
    id: int
    phase_number: int
    phase_name: str
    status: PhaseStatus
    tool_statuses: dict = {}
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    error_message: str | None = None

    model_config = {"from_attributes": True}


class ScanResponse(BaseModel):
    id: int
    scan_uid: str
    target_domain: str
    status: ScanStatus
    current_phase: int
    config: dict
    results_dir: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    created_by: int
    created_at: datetime
    updated_at: datetime
    phases: list[ScanPhaseResponse] = []

    model_config = {"from_attributes": True}


class ScanListResponse(BaseModel):
    items: list[ScanResponse]
    total: int
    page: int
    per_page: int


class ScanLogResponse(BaseModel):
    scan_id: int
    logs: list[dict]

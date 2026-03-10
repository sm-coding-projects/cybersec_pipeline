from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, FindingStatus, Severity


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("scans.id", ondelete="CASCADE"), nullable=False, index=True)
    target_id: Mapped[int | None] = mapped_column(
        ForeignKey("targets.id", ondelete="SET NULL"), nullable=True
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    severity: Mapped[Severity] = mapped_column(
        Enum(Severity, name="severity", values_callable=lambda x: [e.value for e in x]), nullable=False, index=True
    )
    source_tool: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    template_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    remediation: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_urls: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    affected_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    affected_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    affected_port: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[FindingStatus] = mapped_column(
        Enum(FindingStatus, name="finding_status", values_callable=lambda x: [e.value for e in x]), default=FindingStatus.OPEN, nullable=False
    )
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    defectdojo_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    scan: Mapped["Scan"] = relationship("Scan", back_populates="findings")
    target: Mapped["Target | None"] = relationship("Target", back_populates="findings")

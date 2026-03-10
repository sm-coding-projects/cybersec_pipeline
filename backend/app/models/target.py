from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TargetType


class Target(Base):
    __tablename__ = "targets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("scans.id", ondelete="CASCADE"), nullable=False, index=True)
    target_type: Mapped[TargetType] = mapped_column(
        Enum(TargetType, name="target_type", values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    value: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    source_tool: Mapped[str] = mapped_column(String(100), nullable=False)
    is_live: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Enrichment data (populated by later phases)
    resolved_ips: Mapped[list | None] = mapped_column(JSON, nullable=True)
    open_ports: Mapped[list | None] = mapped_column(JSON, nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    http_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    technologies: Mapped[list | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    scan: Mapped["Scan"] = relationship("Scan", back_populates="targets")
    findings: Mapped[list["Finding"]] = relationship("Finding", back_populates="target", lazy="selectin")

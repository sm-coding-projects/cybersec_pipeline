from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, PhaseStatus, ScanStatus


class Scan(Base):
    __tablename__ = "scans"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    scan_uid: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    target_domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[ScanStatus] = mapped_column(
        Enum(ScanStatus, name="scan_status", values_callable=lambda x: [e.value for e in x]), default=ScanStatus.PENDING, nullable=False
    )
    current_phase: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    results_dir: Mapped[str] = mapped_column(String(500), nullable=False)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    creator: Mapped["User"] = relationship("User", back_populates="scans", lazy="selectin")
    phases: Mapped[list["ScanPhase"]] = relationship(
        "ScanPhase", back_populates="scan", cascade="all, delete-orphan", lazy="selectin",
        order_by="ScanPhase.phase_number"
    )
    targets: Mapped[list["Target"]] = relationship(
        "Target", back_populates="scan", cascade="all, delete-orphan", lazy="selectin"
    )
    findings: Mapped[list["Finding"]] = relationship(
        "Finding", back_populates="scan", cascade="all, delete-orphan", lazy="selectin"
    )


class ScanPhase(Base):
    __tablename__ = "scan_phases"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("scans.id", ondelete="CASCADE"), nullable=False)
    phase_number: Mapped[int] = mapped_column(Integer, nullable=False)
    phase_name: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[PhaseStatus] = mapped_column(
        Enum(PhaseStatus, name="phase_status", values_callable=lambda x: [e.value for e in x]), default=PhaseStatus.PENDING, nullable=False
    )
    tool_statuses: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    log_output: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    scan: Mapped["Scan"] = relationship("Scan", back_populates="phases")

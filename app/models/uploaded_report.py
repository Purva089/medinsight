from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.lab_result import LabResult
    from app.models.patient import Patient


class UploadedReport(Base, TimestampMixin):
    """Tracks every PDF report uploaded by a patient."""

    __tablename__ = "uploaded_reports"

    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patients.patient_id", ondelete="CASCADE"),
        nullable=False,
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # MD5 of raw file bytes — used as a cache key to avoid re-processing
    file_hash: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    # pending → processing → completed / failed
    extraction_status: Mapped[str] = mapped_column(
        String(50), server_default=text("'pending'"), nullable=False
    )
    extraction_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    tests_extracted: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    patient: Mapped["Patient"] = relationship(
        "Patient", back_populates="uploaded_reports", lazy="noload"
    )
    lab_results: Mapped[list["LabResult"]] = relationship(
        "LabResult", back_populates="report", lazy="noload"
    )

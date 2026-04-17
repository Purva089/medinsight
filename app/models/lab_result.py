from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, Float, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.patient import Patient
    from app.models.uploaded_report import UploadedReport


class LabResult(Base, TimestampMixin):
    """A single lab test value extracted from an uploaded report or entered manually."""

    __tablename__ = "lab_results"
    __table_args__ = (
        UniqueConstraint(
            "patient_id", "test_name", "report_date",
            name="uq_lab_result_per_day",
        ),
    )

    result_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patients.patient_id", ondelete="CASCADE"),
        nullable=False,
    )
    # nullable — results entered without an associated uploaded report
    report_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("uploaded_reports.report_id", ondelete="SET NULL"),
        nullable=True,
    )
    test_name: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(50))
    reference_range_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    reference_range_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    # normal / high / low / critical
    status: Mapped[str | None] = mapped_column(String(20))
    # blood_count | metabolic | liver | thyroid | others
    category: Mapped[str] = mapped_column(String(50), nullable=False, server_default="others")
    report_date: Mapped[date] = mapped_column(Date, nullable=False)

    patient: Mapped["Patient"] = relationship(
        "Patient", back_populates="lab_results", lazy="noload"
    )
    report: Mapped["UploadedReport | None"] = relationship(
        "UploadedReport", back_populates="lab_results", lazy="noload"
    )


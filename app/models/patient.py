from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.consultation import Consultation
    from app.models.lab_result import LabResult
    from app.models.patient_summary import PatientSummary
    from app.models.uploaded_report import UploadedReport
    from app.models.user import User


class Patient(Base, TimestampMixin):
    """Patient demographics — core fields used by all agents."""

    __tablename__ = "patients"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    name: Mapped[str | None] = mapped_column(String(255))
    age: Mapped[int | None] = mapped_column(Integer)
    gender: Mapped[str | None] = mapped_column(String(10))
    blood_type: Mapped[str | None] = mapped_column(String(10))
    medical_condition: Mapped[str | None] = mapped_column(String(255))
    medication: Mapped[str | None] = mapped_column(String(255))

    user: Mapped["User"] = relationship(
        "User", back_populates="patient", lazy="noload"
    )
    lab_results: Mapped[list["LabResult"]] = relationship(
        "LabResult", back_populates="patient", lazy="noload"
    )
    uploaded_reports: Mapped[list["UploadedReport"]] = relationship(
        "UploadedReport", back_populates="patient", lazy="noload"
    )
    consultations: Mapped[list["Consultation"]] = relationship(
        "Consultation", back_populates="patient", lazy="noload"
    )
    summary: Mapped["PatientSummary | None"] = relationship(
        "PatientSummary", back_populates="patient", uselist=False, lazy="noload"
    )


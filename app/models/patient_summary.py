from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.patient import Patient


class PatientSummary(Base):
    """
    LTM summary for a patient — one row per patient (unique FK).

    updated_at tracks when the summary was last regenerated.
    No TimestampMixin here because created_at is not meaningful;
    generated_at and updated_at carry the temporal semantics instead.
    """

    __tablename__ = "patient_summaries"

    summary_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patients.patient_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    summary_text: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    covers_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    covers_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    patient: Mapped["Patient"] = relationship(
        "Patient", back_populates="summary", lazy="noload"
    )


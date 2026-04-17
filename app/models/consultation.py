from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Consultation(Base):
    """
    One question-answer pair from a patient chat session.

    session_id groups all messages within a single conversation.
    Each message is immutable once written — no updated_at needed.
    """

    __tablename__ = "consultations"

    consult_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patients.patient_id", ondelete="CASCADE"),
        nullable=False,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    intent_handled: Mapped[str | None] = mapped_column(String(50))
    # high / medium / low
    confidence_level: Mapped[str | None] = mapped_column(String(20))
    sources_cited: Mapped[list | None] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    trend_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    sql_query_generated: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    patient: Mapped["Patient"] = relationship(
        "Patient", back_populates="consultations", lazy="noload"
    )


from __future__ import annotations

import uuid

from sqlalchemy import Float, String, Text, UniqueConstraint, text
# LabReference extended with clinical enrichment fields
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class LabReference(Base, TimestampMixin):
    """
    Stores MedlinePlus reference data scraped for each lab test.

    One row per test name — the scraper upserts on conflict so re-running
    is always safe. range_low and range_high are populated in a later stage
    when the extraction parser is implemented.
    """

    __tablename__ = "lab_references"
    __table_args__ = (
        UniqueConstraint("test_name", name="uq_lab_reference_test_name"),
    )

    reference_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    test_name: Mapped[str] = mapped_column(String(100), nullable=False)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Full scraped page text — truncated to 5000 chars for storage
    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    range_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    range_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Clinical enrichment
    category: Mapped[str] = mapped_column(String(50), nullable=False, server_default="others")
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    advice: Mapped[str | None] = mapped_column(Text, nullable=True)
    causes_high: Mapped[str | None] = mapped_column(Text, nullable=True)
    causes_low: Mapped[str | None] = mapped_column(Text, nullable=True)
    specialist_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    retesting_urgency: Mapped[str | None] = mapped_column(String(50), nullable=True)

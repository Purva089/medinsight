from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""

    type_annotation_map: dict[Any, Any] = {}


class TimestampMixin:
    """Adds created_at / updated_at TIMESTAMP WITH TIME ZONE columns with DB-side defaults."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        onupdate=func.now(),
        nullable=False,
    )

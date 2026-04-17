from __future__ import annotations

import uuid

from sqlalchemy import Boolean, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    """Application user — can be a patient or an admin."""

    __tablename__ = "users"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), server_default=text("'patient'"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), nullable=False)

    patient: Mapped["Patient"] = relationship(
        "Patient", back_populates="user", uselist=False, lazy="noload"
    )


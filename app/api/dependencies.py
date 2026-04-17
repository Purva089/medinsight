"""
FastAPI shared dependencies.
"""
from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.patient import Patient
from app.models.user import User
from app.services.llm_service import LLMService, llm_service as _llm_singleton

_bearer = HTTPBearer()

# ── DB session ────────────────────────────────────────────────────────────────

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


# ── JWT auth ──────────────────────────────────────────────────────────────────

async def get_current_patient(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> Patient:
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )
        patient_id_str: str | None = payload.get("sub")
        if patient_id_str is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    patient = (
        await db.execute(select(Patient).where(Patient.patient_id == uuid.UUID(patient_id_str)))
    ).scalar_one_or_none()

    if patient is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Patient not found")

    return patient


# ── service singletons ────────────────────────────────────────────────────────


def get_llm() -> LLMService:
    return _llm_singleton

"""
Shared pytest fixtures for MedInsight test suite.
"""
from __future__ import annotations

import os
os.environ["TESTING"] = "1"  # NullPool in database.py; must precede app imports

import uuid
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from jose import jwt
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.patient import Patient
from app.models.user import User


# ── DB session ────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture()
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yields a per-test async DB session, rolls back after each test."""
    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()


# ── Test patient ──────────────────────────────────────────────────────────────

_TEST_EMAIL = "test@medinsight.example.com"


@pytest_asyncio.fixture()
async def test_patient(db_session: AsyncSession) -> AsyncGenerator[str, None]:
    """
    Creates a test user + patient row, yields patient_id (str),
    and deletes both rows after the test.
    """
    import bcrypt as _bcrypt
    hashed = _bcrypt.hashpw(b"TestPass@99", _bcrypt.gensalt()).decode()

    user = User(
        email=_TEST_EMAIL,
        hashed_password=hashed,
        full_name="Test Patient",
        role="patient",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    patient = Patient(user_id=user.user_id, name="Test Patient", age=30, gender="M")
    db_session.add(patient)
    await db_session.commit()
    await db_session.refresh(patient)

    patient_id = str(patient.patient_id)
    yield patient_id

    # Cleanup — cascade deletes patient + related rows via FK
    await db_session.execute(delete(User).where(User.email == _TEST_EMAIL))
    await db_session.commit()


# ── JWT token ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def test_token(test_patient: str) -> str:
    """Return a valid JWT for the test patient."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=60)
    return jwt.encode(
        {"sub": test_patient, "exp": expire},
        settings.secret_key,
        algorithm=settings.algorithm,
    )


# ── Mock LLM ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def mock_llm(mocker):
    """
    Patch LLMService.call_reasoning to return a valid ReportResponse JSON string
    without hitting the real Groq API.
    """
    mock_response = (
        '{"direct_answer":"Test answer.","guideline_context":"Test context.",'
        '"trend_summary":"No trend.","watch_for":"Nothing.","sources":[],'
        '"disclaimer":"This is not medical advice.","confidence":"high",'
        '"intent_handled":"rag"}'
    )
    return mocker.patch(
        "app.services.llm_service.LLMService.call_reasoning",
        return_value=mock_response,
    )




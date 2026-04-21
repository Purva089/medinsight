"""
Shared pytest fixtures for MedInsight test suite.
"""
from __future__ import annotations

import os
os.environ["TESTING"] = "1"  # NullPool in database.py; must precede app imports

# ── Exclude standalone scripts from pytest collection ────────────────────────
collect_ignore = ["test_agents.py"]

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.lab_result import LabResult
from app.models.patient import Patient
from app.models.uploaded_report import UploadedReport
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


# ── Async HTTP client ─────────────────────────────────────────────────────────

@pytest_asyncio.fixture()
async def client() -> AsyncGenerator[AsyncClient, None]:
    """HTTPX AsyncClient wired to the FastAPI app via ASGI transport."""
    from app.api.main import app
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ── Lab results fixture ───────────────────────────────────────────────────────

@pytest_asyncio.fixture()
async def lab_results(test_patient: str) -> AsyncGenerator[list[uuid.UUID], None]:
    """
    Insert 3 LabResult rows for the test patient across 3 months.
    Yields list of result_ids; cleans up after each test.
    """
    today = date.today()
    rows = [
        LabResult(
            patient_id=uuid.UUID(test_patient),
            test_name="Hemoglobin",
            value=val,
            unit="g/dL",
            reference_range_low=12.0,
            reference_range_high=16.0,
            status="normal" if 12.0 <= val <= 16.0 else "low",
            category="blood_count",
            report_date=today - timedelta(days=60 - i * 30),
        )
        for i, val in enumerate([11.5, 12.8, 13.2])
    ]
    async with AsyncSessionLocal() as db:
        db.add_all(rows)
        await db.commit()
        for r in rows:
            await db.refresh(r)
        ids = [r.result_id for r in rows]

    yield ids

    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(LabResult).where(LabResult.result_id.in_(ids))
        )
        await db.commit()


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


# ── Minimal MedInsightState builder ──────────────────────────────────────────

def make_state(
    question: str = "What is a normal hemoglobin level?",
    intent: str = "rag",
    patient_id: str | None = None,
    extracted_tests: list[dict] | None = None,
) -> dict:
    """Return a minimal MedInsightState dict for agent unit tests."""
    pid = patient_id or str(uuid.uuid4())
    tests = extracted_tests or [
        {
            "test_name": "Hemoglobin",
            "value": 12.5,
            "unit": "g/dL",
            "reference_range_low": 12.0,
            "reference_range_high": 16.0,
            "status": "normal",
            "confidence": 0.95,
            "category": "blood_count",
        },
        {
            "test_name": "SGPT",
            "value": 65.0,
            "unit": "U/L",
            "reference_range_low": 7.0,
            "reference_range_high": 56.0,
            "status": "high",
            "confidence": 0.92,
            "category": "liver",
        },
    ]
    return {
        "patient_id": pid,
        "patient_profile": {"patient_id": pid, "name": "Test", "age": 30, "gender": "M"},
        "ltm_summary": "No prior history.",
        "stm_messages": [],
        "current_question": question,
        "intent": intent,
        "request_id": f"test-{uuid.uuid4().hex[:8]}",
        "current_report_id": str(uuid.uuid4()),
        "extracted_tests": tests,
        "extraction_confidence": 0.93,
        "rag_chunks": [],
        "rag_context": "",
        "others_tests": [],
        "disclaimer_required": False,
        "needs_rag": intent in ("rag", "general"),
        "needs_sql": intent == "sql",
        "needs_trend": intent == "trend",
        "needs_report_generation": False,
        "trend_results": [],
        "mentioned_tests": [],
        "sql_query_generated": None,
        "sql_results": [],
        "final_response": {},
        "errors": [],
        "a2a_messages": [],
    }




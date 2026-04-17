"""
API endpoint integration tests using httpx.AsyncClient.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from typing import AsyncGenerator

from app.api.main import app
from app.core.database import AsyncSessionLocal
from app.models.patient import Patient
from app.models.user import User

# Base URL used for all client requests
_BASE = "http://test/api/v1"


@pytest_asyncio.fixture()
async def client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ── Helper: register + login to get token ─────────────────────────────────────

async def _register_and_login(client: AsyncClient, suffix: str = "") -> tuple[str, str]:
    """Register a fresh account, return (token, patient_id)."""
    email = f"ep_test_{uuid.uuid4().hex[:8]}{suffix}@medinsight.example.com"
    r = await client.post(
        "/api/v1/auth/register",
        json={"full_name": "EP Test", "email": email, "password": "TestPass@99"},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    return data["access_token"], data["patient_id"]


async def _cleanup_user(email: str) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(User).where(User.email == email))
        await db.commit()


# ── test_register_success ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    email = f"reg_{uuid.uuid4().hex[:8]}@medinsight.example.com"
    r = await client.post(
        "/api/v1/auth/register",
        json={"full_name": "New User", "email": email, "password": "ValidPass@1"},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert "access_token" in data
    assert "patient_id" in data
    await _cleanup_user(email)


# ── test_login_wrong_password ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    # Register first
    email = f"lw_{uuid.uuid4().hex[:8]}@medinsight.example.com"
    await client.post(
        "/api/v1/auth/register",
        json={"full_name": "Login Test", "email": email, "password": "ValidPass@1"},
    )
    # Try wrong password
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "WrongPass@999"},
    )
    assert r.status_code == 401, r.text
    await _cleanup_user(email)


# ── test_chat_requires_auth ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chat_requires_auth(client: AsyncClient):
    r = await client.post(
        "/api/v1/chat/ask",
        json={"question": "Is my TSH normal?"},
    )
    assert r.status_code == 401, r.text   # No auth header → 401 from HTTPBearer


# ── test_history_scoped_to_patient ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_history_scoped_to_patient(client: AsyncClient):
    """
    Patient A should only see their own history.
    Patient B's history endpoint returns their own data (HTTP 200),
    not patient A's data — scoped by JWT, not query param.
    """
    token_a, pid_a = await _register_and_login(client, "_a")
    token_b, pid_b = await _register_and_login(client, "_b")

    # Patient B hits history with their own token — expects 200, empty list
    r = await client.get(
        "/api/v1/history",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 200
    data_b = r.json()
    # Ensure patient A's patient_id does not appear in patient B's history
    patient_ids_in_result = [row.get("patient_id") for row in data_b]
    assert pid_a not in patient_ids_in_result

    # Cleanup both accounts
    async with AsyncSessionLocal() as db:
        for pid in (pid_a, pid_b):
            patient = await db.get(Patient, uuid.UUID(pid))
            if patient:
                user = await db.get(User, patient.user_id)
                if user:
                    await db.delete(user)
        await db.commit()


# ── test_upload_wrong_file_type ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_wrong_file_type(client: AsyncClient):
    token, pid = await _register_and_login(client)
    r = await client.post(
        "/api/v1/reports/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("test.txt", b"plain text content", "text/plain")},
    )
    assert r.status_code == 400, r.text

    async with AsyncSessionLocal() as db:
        patient = await db.get(Patient, uuid.UUID(pid))
        if patient:
            user = await db.get(User, patient.user_id)
            if user:
                await db.delete(user)
        await db.commit()


# ── test_trends_returns_chart_data ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_trends_returns_chart_data(client: AsyncClient, test_patient: str, test_token: str):
    """
    If TSH data exists for the test patient, endpoint returns valid TrendResult.
    If not enough data, it should return 422 — not 500.
    """
    from datetime import date, timedelta
    from app.models.lab_result import LabResult

    # Insert 2 TSH data points so trend can be computed
    async with AsyncSessionLocal() as db:
        today = date.today()
        for i, val in enumerate([2.0, 4.5]):
            lr = LabResult(
                patient_id=uuid.UUID(test_patient),
                test_name="TSH",
                value=val,
                unit="mIU/L",
                report_date=today - timedelta(days=60 - i * 30),
            )
            db.add(lr)
        await db.commit()

    r = await client.get(
        "/api/v1/trends/TSH",
        headers={"Authorization": f"Bearer {test_token}"},
    )

    assert r.status_code in (200, 422), f"Unexpected status {r.status_code}: {r.text}"
    if r.status_code == 200:
        data = r.json()
        assert isinstance(data["data_points"], list)
        assert data["direction"] in ("rising", "falling", "stable")

    # Cleanup
    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(LabResult).where(
                LabResult.patient_id == uuid.UUID(test_patient),
                LabResult.test_name == "TSH",
            )
        )
        await db.commit()

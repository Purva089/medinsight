"""
Authentication tests — register, login, JWT, protected routes.

Covers:
- Successful registration returns 201 + token + patient_id
- Duplicate email returns 409
- Login with correct credentials returns token
- Login with wrong password returns 401
- Login with unknown email returns 401
- Protected route without token returns 401
- Protected route with expired token returns 401
- Protected route with valid token returns 200
- JWT payload contains correct patient_id
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from jose import jwt
from sqlalchemy import delete

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.user import User

pytestmark = pytest.mark.asyncio

_BASE = "/api/v1"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _unique_email(prefix: str = "auth") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"


async def _cleanup(email: str) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(User).where(User.email == email))
        await db.commit()


async def _register(client: AsyncClient, email: str, password: str = "ValidPass@1") -> dict:
    r = await client.post(
        f"{_BASE}/auth/register",
        json={"full_name": "Auth Test User", "email": email, "password": password},
    )
    return r


# ── Registration ──────────────────────────────────────────────────────────────

async def test_register_success(client: AsyncClient):
    """POST /auth/register with valid data → 201 + access_token + patient_id."""
    email = _unique_email("reg_ok")
    r = await _register(client, email)
    assert r.status_code == 201, r.text
    data = r.json()
    assert "access_token" in data
    assert "patient_id" in data
    assert data["token_type"] == "bearer"
    await _cleanup(email)


async def test_register_duplicate_email_returns_409(client: AsyncClient):
    """Registering twice with the same email → 409 Conflict."""
    email = _unique_email("reg_dup")
    await _register(client, email)
    r = await _register(client, email)
    assert r.status_code == 409, r.text
    await _cleanup(email)


async def test_register_weak_password_returns_422(client: AsyncClient):
    """Password that fails validation → 422 Unprocessable Entity."""
    r = await client.post(
        f"{_BASE}/auth/register",
        json={"full_name": "Weak", "email": _unique_email("weak"), "password": "123"},
    )
    assert r.status_code == 422, r.text


async def test_register_missing_email_returns_422(client: AsyncClient):
    """Missing email field → 422."""
    r = await client.post(
        f"{_BASE}/auth/register",
        json={"full_name": "No Email", "password": "ValidPass@1"},
    )
    assert r.status_code == 422, r.text


# ── Login ─────────────────────────────────────────────────────────────────────

async def test_login_success(client: AsyncClient):
    """POST /auth/login with correct credentials → 200 + access_token."""
    email = _unique_email("login_ok")
    await _register(client, email)
    r = await client.post(
        f"{_BASE}/auth/login",
        json={"email": email, "password": "ValidPass@1"},
    )
    assert r.status_code == 200, r.text
    assert "access_token" in r.json()
    await _cleanup(email)


async def test_login_wrong_password_returns_401(client: AsyncClient):
    """POST /auth/login with wrong password → 401."""
    email = _unique_email("login_bad")
    await _register(client, email)
    r = await client.post(
        f"{_BASE}/auth/login",
        json={"email": email, "password": "WrongPass@999"},
    )
    assert r.status_code == 401, r.text
    await _cleanup(email)


async def test_login_unknown_email_returns_401(client: AsyncClient):
    """POST /auth/login with non-existent email → 401."""
    r = await client.post(
        f"{_BASE}/auth/login",
        json={"email": f"nobody_{uuid.uuid4().hex[:8]}@example.com", "password": "Whatever@1"},
    )
    assert r.status_code == 401, r.text


# ── JWT ───────────────────────────────────────────────────────────────────────

async def test_jwt_payload_contains_patient_id(client: AsyncClient):
    """Token sub claim should equal the patient_id returned at registration."""
    email = _unique_email("jwt_check")
    r = await _register(client, email)
    data = r.json()
    token = data["access_token"]
    patient_id = data["patient_id"]

    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    assert payload["sub"] == patient_id
    await _cleanup(email)


async def test_expired_token_returns_401(client: AsyncClient, test_patient: str):
    """A JWT that expired 1 hour ago → 401 on a protected route."""
    expired = datetime.now(timezone.utc) - timedelta(hours=1)
    token = jwt.encode(
        {"sub": test_patient, "exp": expired},
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    r = await client.get(
        f"{_BASE}/history",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 401, r.text


# ── Protected routes ──────────────────────────────────────────────────────────

async def test_protected_route_no_token_returns_401(client: AsyncClient):
    """Chat /ask without Authorization header → 401."""
    r = await client.post(
        f"{_BASE}/chat/ask",
        json={"question": "Is my TSH normal?"},
    )
    assert r.status_code == 401, r.text


async def test_protected_route_invalid_token_returns_401(client: AsyncClient):
    """Malformed/garbage token → 401."""
    r = await client.get(
        f"{_BASE}/history",
        headers={"Authorization": "Bearer totally.invalid.token"},
    )
    assert r.status_code == 401, r.text


async def test_protected_route_valid_token_returns_200(client: AsyncClient, test_token: str):
    """History endpoint with valid JWT → 200."""
    r = await client.get(
        f"{_BASE}/history",
        headers={"Authorization": f"Bearer {test_token}"},
    )
    assert r.status_code == 200, r.text


# ── Cross-patient isolation ───────────────────────────────────────────────────

async def test_history_scoped_to_requesting_patient(client: AsyncClient):
    """Patient B's history must not contain Patient A's patient_id."""
    email_a = _unique_email("iso_a")
    email_b = _unique_email("iso_b")
    r_a = await _register(client, email_a)
    r_b = await _register(client, email_b)
    pid_a = r_a.json()["patient_id"]
    token_b = r_b.json()["access_token"]

    r = await client.get(
        f"{_BASE}/history",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 200
    pids = [row.get("patient_id") for row in r.json()]
    assert pid_a not in pids

    await _cleanup(email_a)
    await _cleanup(email_b)

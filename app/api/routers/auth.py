"""
Authentication router – register and login.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from jose import jwt
import bcrypt as _bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_patient, get_db
from app.core.config import settings
from app.core.logging import get_logger
from app.models.patient import Patient
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, SessionStatusResponse, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])
log = get_logger(__name__)

def _hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()


def _verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())


def _create_access_token(patient_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": patient_id, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


# ── Register ──────────────────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    """Create a new user account and linked patient record."""
    # Check for duplicate e-mail
    existing = (
        await db.execute(select(User).where(User.email == body.email.lower()))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this e-mail already exists.",
        )

    user = User(
        email=body.email.lower(),
        hashed_password=_hash_password(body.password),
        full_name=body.full_name,
        role="patient",
        is_active=True,
    )
    db.add(user)
    await db.flush()  # populate user_id

    patient = Patient(
        user_id=user.user_id,
        name=body.full_name,
    )
    db.add(patient)
    await db.commit()
    await db.refresh(patient)

    token = _create_access_token(str(patient.patient_id))
    return TokenResponse(access_token=token, patient_id=str(patient.patient_id))


# ── Login ─────────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    """Authenticate and return a JWT."""
    user = (
        await db.execute(select(User).where(User.email == body.email.lower()))
    ).scalar_one_or_none()

    if user is None or not _verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect e-mail or password.",
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated.")

    # Fetch linked patient
    patient = (
        await db.execute(select(Patient).where(Patient.user_id == user.user_id))
    ).scalar_one_or_none()

    if patient is None:
        # Auto-heal: a user exists with no linked patient row (can happen from
        # older registrations or manual DB edits). Create the missing record.
        patient = Patient(user_id=user.user_id, name=user.full_name)
        db.add(patient)
        await db.commit()
        await db.refresh(patient)

    token = _create_access_token(str(patient.patient_id))
    return TokenResponse(access_token=token, patient_id=str(patient.patient_id))


@router.get("/me", response_model=SessionStatusResponse)
async def auth_me(patient: Patient = Depends(get_current_patient)) -> SessionStatusResponse:
    """Validate current bearer token and return identity payload."""
    return SessionStatusResponse(patient_id=str(patient.patient_id))

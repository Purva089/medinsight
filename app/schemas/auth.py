"""
Auth-related Pydantic schemas.
"""
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    patient_id: str


class SessionStatusResponse(BaseModel):
    valid: bool = True
    patient_id: str
    token_type: str = "bearer"

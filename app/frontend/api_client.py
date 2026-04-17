"""
Shared API client helpers for all Streamlit pages.

Usage:
    from app.frontend.api_client import API_BASE, auth_headers
"""
from __future__ import annotations

import os

import streamlit as st

# Base URL — override via env var for staging/production
API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000/api/v1")


def auth_headers() -> dict[str, str]:
    """Return Authorization header dict using the current session JWT token."""
    token = st.session_state.get("jwt_token", "")
    return {"Authorization": f"Bearer {token}"}

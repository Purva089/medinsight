"""Helpers to persist frontend auth across browser refreshes."""
from __future__ import annotations

import time
import json
from pathlib import Path
from uuid import uuid4

# In-memory session map (survives Streamlit reruns/refreshes in same process).
_SESSIONS: dict[str, dict] = {}
_TTL_SECONDS = 60 * 60 * 12  # 12 hours
_AUTH_FILE = Path.home() / ".medinsight" / "frontend_auth_session.json"


def _prune_expired(now_ts: float | None = None) -> None:
    now = now_ts or time.time()
    expired = [sid for sid, data in _SESSIONS.items() if data.get("expires_at", 0) < now]
    for sid in expired:
        _SESSIONS.pop(sid, None)


def create_auth_session(
    jwt_token: str,
    patient_id: str | None = None,
    patient_profile: dict | None = None,
) -> str:
    """Create an auth session id and store auth payload."""
    _prune_expired()
    sid = uuid4().hex
    _SESSIONS[sid] = {
        "jwt_token": jwt_token,
        "token": jwt_token,
        "patient_id": patient_id,
        "patient_profile": patient_profile or {},
        "expires_at": time.time() + _TTL_SECONDS,
    }
    return sid


def get_auth_session(sid: str | None) -> dict | None:
    """Return auth payload for sid if valid."""
    if not sid:
        return None
    _prune_expired()
    data = _SESSIONS.get(sid)
    if not data:
        return None
    data["expires_at"] = time.time() + _TTL_SECONDS
    return data


def clear_auth_session(sid: str | None) -> None:
    """Remove auth payload for sid."""
    if sid:
        _SESSIONS.pop(sid, None)


def save_persistent_auth(
    jwt_token: str,
    patient_id: str | None = None,
    patient_profile: dict | None = None,
) -> None:
    """Persist auth on local disk for hard refresh/app restart restore."""
    payload = {
        "jwt_token": jwt_token,
        "token": jwt_token,
        "patient_id": patient_id,
        "patient_profile": patient_profile or {},
        "saved_at": time.time(),
    }
    _AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    _AUTH_FILE.write_text(json.dumps(payload), encoding="utf-8")


def load_persistent_auth() -> dict | None:
    """Load persisted auth from disk."""
    if not _AUTH_FILE.exists():
        return None
    try:
        data = json.loads(_AUTH_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict) or not data.get("jwt_token"):
        return None
    return data


def clear_persistent_auth() -> None:
    """Remove persisted auth file."""
    try:
        if _AUTH_FILE.exists():
            _AUTH_FILE.unlink()
    except Exception:
        pass


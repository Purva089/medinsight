"""MedInsight — Streamlit entry point."""
from __future__ import annotations
import os
import requests
import streamlit as st

st.set_page_config(
    page_title="MedInsight",
    page_icon="🩺",
    layout="wide",
    initial_sidebar_state="expanded",
)

from app.frontend.components.theme import (
    inject_css,
    SIDEBAR_BG, SIDEBAR_TEXT, SIDEBAR_MUTED, SIDEBAR_HOVER,
    PRIMARY, SECONDARY, BG_CARD2,
)
from app.frontend.components.auth_session import load_persistent_auth, clear_persistent_auth
from app.frontend.pages.login     import show_login_page
from app.frontend.pages.dashboard import show_dashboard_page
from app.frontend.pages.chat      import show_chat_page
from app.frontend.pages.upload    import show_upload_page
from app.frontend.pages.trends    import show_trends_page
from app.frontend.pages.history   import show_history_page

inject_css()
_API = os.environ.get("API_BASE_URL", "http://localhost:8000/api/v1")

# ── Session defaults ──────────────────────────────────────────────────────────
for k, v in {
    "jwt_token":       None,
    "patient_id":      None,
    "patient_profile": None,
    "ltm_summary":     None,
    "stm_messages":    [],
    "active_report_id":None,
    "current_page":    "Dashboard",
    "prefill_q":       None,
    "token":           None,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# Restore auth from persistent disk store and validate token.
if not st.session_state.get("jwt_token"):
    disk_auth = load_persistent_auth()
    if disk_auth and disk_auth.get("jwt_token"):
        token = disk_auth.get("jwt_token")
        try:
            me = requests.get(
                f"{_API}/auth/me",
                headers={"Authorization": f"Bearer {token}"},
                timeout=8,
            )
            if me.ok:
                me_data = me.json() if isinstance(me.json(), dict) else {}
                st.session_state["jwt_token"] = token
                st.session_state["token"] = token
                st.session_state["patient_id"] = (
                    me_data.get("patient_id") or disk_auth.get("patient_id")
                )

                profile = requests.get(
                    f"{_API}/patients/me",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=8,
                )
                if profile.ok:
                    st.session_state["patient_profile"] = profile.json()
                elif disk_auth.get("patient_profile"):
                    st.session_state["patient_profile"] = disk_auth.get("patient_profile")
            elif me.status_code in (401, 403):
                clear_persistent_auth()
            else:
                # Keep persistent login during rate limits or server errors
                st.session_state["jwt_token"] = token
                st.session_state["token"] = token
                if disk_auth.get("patient_profile"):
                    st.session_state["patient_profile"] = disk_auth.get("patient_profile")
                if disk_auth.get("patient_id"):
                    st.session_state["patient_id"] = disk_auth.get("patient_id")
        except Exception as e:
            # Keep persistent login during API startup/network hiccups.
            st.session_state["jwt_token"] = token
            st.session_state["token"] = token
            if disk_auth.get("patient_profile"):
                st.session_state["patient_profile"] = disk_auth.get("patient_profile")
            if disk_auth.get("patient_id"):
                st.session_state["patient_id"] = disk_auth.get("patient_id")
            st.session_state["jwt_token"] = token
            st.session_state["token"] = token
            if disk_auth.get("patient_profile"):
                st.session_state["patient_profile"] = disk_auth.get("patient_profile")
            if disk_auth.get("patient_id"):
                st.session_state["patient_id"] = disk_auth.get("patient_id")

# ── Auth gate ─────────────────────────────────────────────────────────────────
if not st.session_state.get("jwt_token"):
    show_login_page()
    st.stop()

# ── Sidebar ───────────────────────────────────────────────────────────────────
profile = st.session_state.get("patient_profile") or {}
name    = profile.get("full_name") or profile.get("name") or "Patient"
initials = "".join(w[0].upper() for w in name.split()[:2])

NAV = [
    ("🏠", "Dashboard"),
    ("💬", "Chat"),
    ("📄", "Upload Report"),
    ("📈", "Trends"),
    ("📋", "History"),
]

with st.sidebar:
    # ── Brand ─────────────────────────────────────────────────────────────────
    st.markdown(
        f"""<div style="padding:28px 20px 20px;border-bottom:1px solid rgba(255,255,255,0.08);margin-bottom:12px">
  <div style="display:flex;align-items:center;gap:12px">
    <div style="background:linear-gradient(135deg,{PRIMARY},{SECONDARY});
                width:42px;height:42px;border-radius:12px;display:flex;
                align-items:center;justify-content:center;
                font-size:1.25rem;flex-shrink:0">🩺</div>
    <div>
      <p style="margin:0;font-size:1.05rem;font-weight:800;color:{SIDEBAR_TEXT};
                letter-spacing:-0.01em">MedInsight</p>
      <p style="margin:0;font-size:0.7rem;color:{SIDEBAR_MUTED}">AI Health Intelligence</p>
    </div>
  </div>
</div>""",
        unsafe_allow_html=True,
    )

    # ── Patient avatar ────────────────────────────────────────────────────────
    cond = profile.get("medical_condition") or ""
    st.markdown(
        f"""<div style="padding:12px 20px 16px">
  <div style="display:flex;align-items:center;gap:10px">
    <div style="background:linear-gradient(135deg,{SECONDARY},{PRIMARY});
                width:38px;height:38px;border-radius:50%;display:flex;
                align-items:center;justify-content:center;
                font-size:0.9rem;font-weight:800;color:white;flex-shrink:0">{initials}</div>
    <div style="min-width:0">
      <p style="margin:0;font-size:0.82rem;font-weight:700;color:{SIDEBAR_TEXT};
                overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{name}</p>
      <p style="margin:0;font-size:0.7rem;color:{SIDEBAR_MUTED};
                overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{cond or "Patient"}</p>
    </div>
  </div>
</div>""",
        unsafe_allow_html=True,
    )

    # ── Navigation ────────────────────────────────────────────────────────────
    st.markdown(
        f'<p style="font-size:0.65rem;font-weight:700;color:{SIDEBAR_MUTED};'
        f'text-transform:uppercase;letter-spacing:0.1em;'
        f'padding:0 20px;margin:4px 0 8px">Menu</p>',
        unsafe_allow_html=True,
    )

    current = st.session_state.get("current_page", "Dashboard")
    for icon, label in NAV:
        is_active = current == label
        if is_active:
            st.markdown(
                '<span class="nav-active" style="display:none"></span>',
                unsafe_allow_html=True,
            )
        if st.button(f"{icon}  {label}", key=f"nav_{label}", use_container_width=True):
            st.session_state["current_page"] = label
            st.rerun()

    st.markdown(
        '<div style="height:1px;background:rgba(255,255,255,0.07);margin:16px 20px"></div>',
        unsafe_allow_html=True,
    )

    if st.button("🚪  Sign Out", use_container_width=True, key="logout"):
        clear_persistent_auth()
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

    # ── Footer ────────────────────────────────────────────────────────────────
    st.markdown(
        f'<p style="font-size:0.65rem;color:{SIDEBAR_MUTED};'
        f'text-align:center;padding:20px 0 0">v2.0 · AI-powered · Not medical advice</p>',
        unsafe_allow_html=True,
    )

# ── Page routing ──────────────────────────────────────────────────────────────
page = st.session_state.get("current_page", "Dashboard")
dispatch = {
    "Dashboard":     show_dashboard_page,
    "Chat":          show_chat_page,
    "Upload Report": show_upload_page,
    "Trends":        show_trends_page,
    "History":       show_history_page,
}
dispatch.get(page, show_dashboard_page)()

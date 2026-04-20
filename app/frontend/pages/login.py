"""Login page — indigo split-screen."""
from __future__ import annotations
import requests
import streamlit as st
from app.frontend.api_client import API_BASE as _API
from app.frontend.components.auth_session import save_persistent_auth

_N = "#1E1B4B"   # navy
_B = "#6366F1"   # indigo
_V = "#7C3AED"   # violet
_W = "#FFFFFF"
_S = "#F5F3FF"   # violet-50
_BR= "#E5E7EB"
_T = "#111827"
_M = "#9CA3AF"
_SE= "#4B5563"

_PAGE_CSS = f"""<style>
html,body,[data-testid="stAppViewContainer"]{{background:{_S}!important}}
[data-testid="stMain"] .block-container{{padding:0!important;max-width:100%!important}}
[data-testid="stSidebar"]{{display:none!important}}
[data-testid="stSidebarNav"]{{display:none!important}}
#MainMenu,footer,header{{visibility:hidden!important;height:0!important}}
[data-testid="stDecoration"]{{display:none!important}}
.stButton>button{{width:100%;padding:13px 0!important;border-radius:11px!important;
  font-size:0.95rem!important;font-weight:700!important;transition:all 0.15s!important}}
.stButton>button[kind="primary"]{{
  background:linear-gradient(135deg,{_B},{_V})!important;border:none!important;
  color:white!important;box-shadow:0 4px 16px rgba(99,102,241,0.4)!important}}
.stButton>button[kind="primary"]:hover{{transform:translateY(-1px)!important;
  box-shadow:0 6px 22px rgba(99,102,241,0.55)!important}}
[data-testid="stTextInput"] input,
[data-testid="stTextInput"] [data-baseweb="input"] {{background:{_W}!important;color:{_T}!important;
  border-radius:11px!important; font-size:0.9rem!important; padding:4px!important}}
[data-testid="stTextInput"] div[data-baseweb="base-input"] {{background:{_W}!important;
  border:1.5px solid {_BR}!important;}}
[data-testid="stTextInput"] input:focus{{border-color:{_B}!important;
  box-shadow:0 0 0 3px rgba(99,102,241,0.14)!important}}
[data-testid="stTabs"] [data-baseweb="tab-list"]{{background:#EDEDFD!important;
  border-radius:12px!important;border:1px solid #C7D2FE!important;
  padding:4px!important;gap:3px!important}}
[data-testid="stTabs"] [data-baseweb="tab"]{{background:transparent!important;
  color:{_M}!important;border-radius:9px!important;border:none!important;
  font-weight:600!important;font-size:0.9rem!important;padding:9px 26px!important}}
[data-testid="stTabs"] [aria-selected="true"]{{background:{_W}!important;
  color:{_B}!important;box-shadow:0 1px 4px rgba(99,102,241,0.18)!important}}
[data-testid="stAlert"]{{border-radius:11px!important}}
</style>"""


def _do_login(email: str, pwd: str) -> None:
    try:
        r = requests.post(f"{_API}/auth/login",
                          json={"email": email, "password": pwd}, timeout=15)
    except requests.exceptions.ConnectionError:
        st.error("Cannot reach the server — is the API running on port 8000?"); return
    except requests.exceptions.Timeout:
        st.error("Request timed out — please try again."); return
    if r.ok:
        d = r.json()
        profile_data = {}
        st.session_state.update(jwt_token=d.get("access_token"),
                                token=d.get("access_token"),
                                patient_id=d.get("patient_id"))
        try:
            p = requests.get(f"{_API}/patients/me",
                             headers={"Authorization": f"Bearer {d.get('access_token')}"},
                             timeout=8)
            if p.ok:
                profile_data = p.json()
                st.session_state["patient_profile"] = profile_data
        except Exception:
            pass
        save_persistent_auth(
            jwt_token=d.get("access_token") or "",
            patient_id=d.get("patient_id"),
            patient_profile=profile_data,
        )
        st.rerun()
    else:
        try:    detail = r.json().get("detail", "Login failed.")
        except Exception: detail = f"HTTP {r.status_code} — {(r.text or '')[:120]}"
        st.error(detail)


def _do_register(email: str, pwd: str, name: str) -> None:
    try:
        r = requests.post(f"{_API}/auth/register",
                          json={"email": email, "password": pwd, "full_name": name},
                          timeout=15)
    except requests.exceptions.ConnectionError:
        st.error("Cannot reach the server."); return
    except requests.exceptions.Timeout:
        st.error("Request timed out."); return
    if r.ok:
        st.success("Account created! Switch to Sign In and log in.")
    else:
        try:    detail = r.json().get("detail", "Registration failed.")
        except Exception: detail = f"HTTP {r.status_code} — {(r.text or '')[:120]}"
        st.error(detail)


def show_login_page() -> None:
    st.markdown(_PAGE_CSS, unsafe_allow_html=True)

    left, right = st.columns([1, 1.15], gap="small")

    # ── LEFT — brand panel ────────────────────────────────────────────────────
    with left:
        st.markdown(f"""
<div style="background:linear-gradient(160deg,{_N} 0%,#1e3a72 55%,#312e81 100%);
            min-height:100vh;padding:64px 48px;box-sizing:border-box;
            display:flex;flex-direction:column;justify-content:center">

  <div style="display:flex;align-items:center;gap:14px;margin-bottom:56px">
    <div style="background:linear-gradient(135deg,{_B},{_V});width:54px;height:54px;
                border-radius:16px;display:flex;align-items:center;
                justify-content:center;font-size:1.7rem;flex-shrink:0">🩺</div>
    <div>
      <p style="margin:0;font-size:1.55rem;font-weight:900;color:{_W};
                letter-spacing:-0.03em">MedInsight</p>
      <p style="margin:0;font-size:0.72rem;color:rgba(224,231,255,0.6)">
        AI Health Intelligence</p>
    </div>
  </div>

  <h2 style="margin:0 0 14px;font-size:2.15rem;font-weight:900;color:{_W};
             line-height:1.2;letter-spacing:-0.03em">
    Your health,<br/>understood deeply.
  </h2>
  <p style="margin:0 0 52px;font-size:0.95rem;color:rgba(224,231,255,0.65);
            line-height:1.75;max-width:340px">
    Upload your lab reports and receive personalised AI insights,
    trend analysis, and evidence-backed guidance — all in one place.
  </p>

  <div style="display:flex;flex-direction:column;gap:20px">
    <div style="display:flex;align-items:flex-start;gap:14px">
      <div style="background:rgba(99,102,241,0.25);width:38px;height:38px;
                  border-radius:11px;display:flex;align-items:center;
                  justify-content:center;font-size:1.1rem;flex-shrink:0">📊</div>
      <div>
        <p style="margin:0;font-size:0.9rem;font-weight:700;color:{_W}">Lab Trend Tracking</p>
        <p style="margin:2px 0 0;font-size:0.78rem;color:rgba(224,231,255,0.5)">
          Watch your values change over time with visual charts</p>
      </div>
    </div>
    <div style="display:flex;align-items:flex-start;gap:14px">
      <div style="background:rgba(99,102,241,0.25);width:38px;height:38px;
                  border-radius:11px;display:flex;align-items:center;
                  justify-content:center;font-size:1.1rem;flex-shrink:0">🤖</div>
      <div>
        <p style="margin:0;font-size:0.9rem;font-weight:700;color:{_W}">AI-Powered Chat</p>
        <p style="margin:2px 0 0;font-size:0.78rem;color:rgba(224,231,255,0.5)">
          Ask anything, get evidence-backed personalised answers</p>
      </div>
    </div>
    <div style="display:flex;align-items:flex-start;gap:14px">
      <div style="background:rgba(99,102,241,0.25);width:38px;height:38px;
                  border-radius:11px;display:flex;align-items:center;
                  justify-content:center;font-size:1.1rem;flex-shrink:0">🔒</div>
      <div>
        <p style="margin:0;font-size:0.9rem;font-weight:700;color:{_W}">Private &amp; Secure</p>
        <p style="margin:2px 0 0;font-size:0.78rem;color:rgba(224,231,255,0.5)">
          Your data is encrypted and never shared</p>
      </div>
    </div>
  </div>

  <p style="margin:60px 0 0;font-size:0.68rem;color:rgba(224,231,255,0.3)">
    Not a substitute for professional medical advice.</p>
</div>""", unsafe_allow_html=True)

    # ── RIGHT — form panel ────────────────────────────────────────────────────
    with right:
        st.markdown(f"""
<div style="padding:64px 0 0 0;
            box-sizing:border-box;display:flex;flex-direction:column;
            justify-content:center">
  <h1 style="margin:0 0 6px;font-size:1.8rem;font-weight:900;color:{_T};
             letter-spacing:-0.03em">Welcome back</h1>
  <p style="margin:0 0 32px;color:{_M};font-size:0.9rem">
    Sign in or create a new account to get started</p>
</div>""", unsafe_allow_html=True)

        tab_in, tab_up = st.tabs(["Sign In", "Create Account"])

        with tab_in:
            st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)
            em = st.text_input("Email", placeholder="patient1@medinsight.demo", key="li_em")
            pw = st.text_input("Password", type="password", placeholder="Enter password", key="li_pw")
            st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
            if st.button("Sign In", type="primary", key="li_btn", use_container_width=True):
                if not em or not pw:
                    st.error("Please fill in all fields.")
                else:
                    with st.spinner("Signing in…"):
                        _do_login(em.strip(), pw)
#             st.markdown(f"""
# <div style="margin-top:18px;padding:14px 16px;background:#F0F0FE;
#             border:1px solid #C7D2FE;border-radius:12px">
#   <p style="margin:0 0 3px;font-size:0.72rem;font-weight:800;color:{_B}">
#     Demo credentials</p>
#   <p style="margin:0;font-size:0.82rem;color:{_B};font-family:monospace;line-height:1.6">
#     patient1@medinsight.demo<br/>Demo@1234</p>
# </div>""", unsafe_allow_html=True)

        with tab_up:
            st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)
            rn = st.text_input("Full name", placeholder="Jane Smith", key="ru_name")
            re = st.text_input("Email", placeholder="you@example.com", key="ru_em")
            rp = st.text_input("Password", type="password",
                               placeholder="At least 8 characters", key="ru_pw")
            rp2= st.text_input("Confirm password", type="password",
                               placeholder="Repeat your password", key="ru_pw2")
            st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
            if st.button("Create Account", type="primary", key="ru_btn", use_container_width=True):
                if not rn or not re or not rp:
                    st.error("All fields are required.")
                elif rp != rp2:
                    st.error("Passwords do not match.")
                elif len(rp) < 8:
                    st.error("Password must be at least 8 characters.")
                else:
                    with st.spinner("Creating account…"):
                        _do_register(re.strip(), rp, rn.strip())

"""Trends page."""
from __future__ import annotations
import os, requests
from urllib.parse import quote as url_quote
import streamlit as st
from app.frontend.api_client import API_BASE as _API, auth_headers as _hdr
from app.frontend.components.theme import (
    inject_css, BG_CARD, BG_CARD2, BORDER, BORDER2,
    PRIMARY, SECONDARY, SUCCESS, WARNING, DANGER,
    TEXT, TEXT_SEC, TEXT_MUTED, status_badge,
)
from app.frontend.components.trend_chart import render_trend_chart


@st.cache_data(ttl=120, show_spinner=False)


@st.cache_data(ttl=120, show_spinner=False)
def _fetch_tests(token: str):
    try:
        r = requests.get(f"{_API}/patients/me/lab-results/latest",
                         headers={"Authorization": f"Bearer {token}"}, timeout=15)
        if r.ok:
            data = r.json()
            items = data if isinstance(data, list) else data.get("results", [])
            return sorted({(x.get("test_name") or x.get("name","")).strip() for x in items if x.get("test_name") or x.get("name")})
    except: pass
    return []


@st.cache_data(ttl=60, show_spinner=False)
def _fetch_trend(token: str, test_name: str):
    try:
        enc = url_quote(test_name, safe="")
        r = requests.get(f"{_API}/trends/{enc}",
                         headers={"Authorization": f"Bearer {token}"}, timeout=20)
        if r.ok: return r.json()
    except: pass
    return None


def _stat_card(label: str, val: str, sub: str, color: str) -> str:
    return (
        f'<div style="background:{BG_CARD};border:1px solid {BORDER};'
        f'border-top:3px solid {color};border-radius:14px;'
        f'padding:18px 20px;box-shadow:0 1px 4px rgba(99,102,241,0.07)">'
        f'<p style="margin:0 4px 0;font-size:0.7rem;font-weight:800;'
        f'color:{TEXT_MUTED};text-transform:uppercase;letter-spacing:0.07em">{label}</p>'
        f'<p style="margin:0;font-size:1.75rem;font-weight:900;color:{TEXT}">{val}</p>'
        f'<p style="margin:2px 0 0;font-size:0.72rem;color:{TEXT_MUTED}">{sub}</p>'
        f'</div>'
    )


def show_trends_page() -> None:
    inject_css()
    st.markdown(
        f'<div class="med-card" style="padding:18px 20px;margin-bottom:18px">'
        f'<div class="med-kicker" style="margin-bottom:8px">Trend analysis</div>'
        f'<h1 style="margin:0 0 6px;font-size:1.45rem;font-weight:900;color:{TEXT};letter-spacing:-0.02em">Lab Trends</h1>'
        f'<p style="margin:0;color:{TEXT_MUTED};font-size:0.86rem;line-height:1.6">Track how your results change over time.</p></div>',
        unsafe_allow_html=True,
    )

    tok = st.session_state.get("jwt_token","")
    tests = _fetch_tests(tok)

    if not tests:
        st.markdown(
            f'<div class="med-card-soft" style="padding:18px 20px;color:{TEXT_SEC}">'
            f'No lab data yet — upload a report first to see trends.</div>',
            unsafe_allow_html=True,
        )
        if st.button("Upload your first report", type="primary"):
            st.session_state["current_page"]="Upload Report"; st.rerun()
        return

    sel = st.selectbox("Select a test to analyse", tests,
                       key="trend_sel",
                       label_visibility="collapsed",
                       placeholder="Choose a test…")
    if not sel: return

    data = _fetch_trend(tok, sel)
    if data is None:
        st.warning("Could not load trend data. Please try again."); return

    dp   = data.get("data_points") or []

    # ── Stats row ────────────────────────────────────────────────────────────
    latest_v = dp[-1].get("value") if dp else "—"
    count_v  = len(dp)
    ref_l    = data.get("reference_low")  or ""
    ref_h    = data.get("reference_high") or ""
    ref_str  = f"{ref_l}–{ref_h}" if ref_l or ref_h else "—"
    trend_s  = (data.get("direction") or "").capitalize() or "—"
    trend_c  = DANGER if "rising" in trend_s.lower() else SUCCESS if "falling" in trend_s.lower() else TEXT_MUTED

    c1,c2,c3,c4 = st.columns(4)
    for col, lbl, val, sub, clr in [
        (c1, "Latest Value",   str(latest_v), data.get("unit","")  or "",   PRIMARY),
        (c2, "Data Points",    str(count_v),  "total readings",             SECONDARY),
        (c3, "Reference Range",ref_str,       data.get("unit","")  or "",   SUCCESS),
        (c4, "Trend",          trend_s,       "recent direction",           trend_c),
    ]:
        col.markdown(_stat_card(lbl, val, sub, clr), unsafe_allow_html=True)

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

    # ── Chart ─────────────────────────────────────────────────────────────────
    if dp:
        render_trend_chart(
            data_points=dp,
            test_name=sel,
            unit=data.get("unit",""),
            ref_low=float(ref_l) if ref_l else None,
            ref_high=float(ref_h) if ref_h else None,
        )
    else:
        st.info("Not enough data points to render a chart yet.")

    # ── AI Interpretation ─────────────────────────────────────────────────────
    interp = data.get("trend_description") or data.get("interpretation")
    if interp:
        st.markdown(
            f'<div style="background:{BG_CARD};border:1px solid {BORDER};'
            f'border-left:4px solid {PRIMARY};border-radius:12px;'
            f'padding:18px 22px;margin-top:16px;'
            f'box-shadow:0 1px 4px rgba(99,102,241,0.07)">'
            f'<p style="margin:0 0 8px;font-size:0.7rem;font-weight:800;color:{TEXT_MUTED};'
            f'text-transform:uppercase;letter-spacing:0.08em">&#129504; AI Interpretation</p>'
            f'<p style="margin:0;color:{TEXT_SEC};font-size:0.875rem;line-height:1.75">{interp}</p>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── CTA ───────────────────────────────────────────────────────────────────
    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    if st.button(f"&#128172; Ask AI about {sel} →",
                 type="primary", key="trend_ask"):
        st.session_state["prefill_q"] = f"Explain my {sel} trend and what I should do."
        st.session_state["current_page"] = "Chat"
        st.rerun()

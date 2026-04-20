"""Dashboard — health overview."""
from __future__ import annotations
import os, requests
import streamlit as st
from app.frontend.api_client import API_BASE as _API, auth_headers as _hdr
from app.frontend.components.theme import (
    inject_css, BG_CARD, BG_CARD2, BORDER, BORDER2,
    PRIMARY, SECONDARY, SUCCESS, WARNING, DANGER,
    TEXT, TEXT_SEC, TEXT_MUTED, status_badge, confidence_badge, page_header,
)


@st.cache_data(ttl=60)
def _profile(tok):
    try: r = requests.get(f"{_API}/patients/me", headers={"Authorization":f"Bearer {tok}"}, timeout=8); return r.json() if r.ok else {}
    except: return {}

@st.cache_data(ttl=60)
def _latest(tok):
    try: r = requests.get(f"{_API}/patients/me/lab-results/latest", headers={"Authorization":f"Bearer {tok}"}, timeout=8); return r.json() if r.ok else []
    except: return []

@st.cache_data(ttl=60)
def _reports(tok):
    try: r = requests.get(f"{_API}/patients/me/reports", headers={"Authorization":f"Bearer {tok}"}, timeout=8); return r.json() if r.ok else []
    except: return []

@st.cache_data(ttl=30)
def _history(tok):
    try: r = requests.get(f"{_API}/history", headers={"Authorization":f"Bearer {tok}"}, timeout=8); return r.json() if r.ok else []
    except: return []


def _set_chat_context_from_latest_report(reports: list[dict]) -> None:
    if not reports:
        return
    latest_report = reports[0]
    report_id = latest_report.get("report_id") or latest_report.get("id")
    if report_id:
        st.session_state["active_report_id"] = str(report_id)


def show_dashboard_page() -> None:
    inject_css()
    tok = st.session_state.get("jwt_token","")
    prof = _profile(tok)
    first = (prof.get("full_name") or prof.get("name") or "there").split()[0]
    latest  = _latest(tok)
    reports = _reports(tok)
    hist    = _history(tok)
    abnormal= [r for r in latest if (r.get("status") or "").lower() != "normal"]

    # ── Header ────────────────────────────────────────────────────────────────
    st.markdown(
        f'<div class="med-card" style="padding:18px 20px;margin-bottom:18px">'
        f'<div class="med-kicker" style="margin-bottom:8px">Health overview</div>'
        f'<h1 style="margin:0 0 6px;font-size:1.55rem;font-weight:900;color:{TEXT};letter-spacing:-0.02em">'
        f'Good day, {first} 👋</h1>'
        f'<p style="margin:0;color:{TEXT_MUTED};font-size:0.88rem;line-height:1.6">Here is your latest summary — the most recent report, key lab values, and the results that need attention.</p>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── No data CTA ───────────────────────────────────────────────────────────
    if not reports:
        st.markdown(
            f'''<div class="med-card" style="background:linear-gradient(135deg,#EEF2FF,#F5F3FF);
                           border:1px solid {BORDER2};padding:48px 40px;text-align:center;margin-bottom:28px">
  <div style="font-size:3rem;margin-bottom:12px">📋</div>
  <h3 style="margin:0 0 8px;color:{TEXT};font-weight:800">No reports uploaded yet</h3>
  <p style="margin:0 0 24px;color:{TEXT_SEC};font-size:0.9rem">
    Upload your first lab report to unlock personalised AI health insights</p>
</div>''',
            unsafe_allow_html=True,
        )
        if st.button("Upload your first report →", type="primary", key="dash_upload_cta"):
            st.session_state["current_page"] = "Upload Report"; st.rerun()
        return

    # ── Abnormal banner ───────────────────────────────────────────────────────
    if abnormal:
        st.markdown(
            f'<div class="med-card-soft" style="background:#FEF3C7;border:1px solid #FCD34D;border-left:4px solid {WARNING};'
            f'padding:12px 18px;margin-bottom:20px;display:flex;align-items:center;gap:10px">'
            f'<span style="font-size:1.1rem">&#9888;&#65039;</span>'
            f'<span style="font-size:0.875rem;font-weight:600;color:#92400E">'
            f'{len(abnormal)} result(s) outside normal range — review below</span></div>',
            unsafe_allow_html=True,
        )

    # ── Metrics ───────────────────────────────────────────────────────────────
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Reports Uploaded", len(reports))
    c2.metric("Tests Tracked", len(latest))
    c3.metric("Abnormal Results", len(abnormal),
              delta=f"{len(abnormal)} flagged" if abnormal else None,
              delta_color="inverse")
    c4.metric("Last Report", (reports[0].get("uploaded_at","")[:10] if reports else "—"))
    st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)

    # ── Two-column body ───────────────────────────────────────────────────────
    col_l, col_r = st.columns([1.5, 1], gap="large")

    with col_l:
        st.markdown(
            f'<p class="med-kicker" style="margin-bottom:12px">Current Lab Values</p>',
            unsafe_allow_html=True,
        )
        if latest:
            sorted_r = sorted(latest, key=lambda x: 0 if (x.get("status","")).lower()!="normal" else 1)
            rows_html = ""
            for row in sorted_r[:12]:
                tn   = row.get("test_name","-")
                val  = str(row.get("value","-"))
                unit = row.get("unit","") or ""
                st_s = (row.get("status") or "").lower()
                sbg  = "#FFF1F2" if st_s in ("high","critical") else "#FFFBEB" if st_s=="low" else "transparent"
                vc   = DANGER if st_s in ("high","critical") else WARNING if st_s=="low" else TEXT
                sb   = status_badge(row.get("status",""))
                rows_html += (
                    f'<tr style="background:{sbg};border-bottom:1px solid {BORDER}">'
                    f'<td style="padding:10px 14px;font-weight:600;color:{TEXT};font-size:0.85rem">{tn}</td>'
                    f'<td style="text-align:right;padding:10px 14px;font-family:monospace;'
                    f'font-weight:700;color:{vc};font-size:0.85rem">{val} {unit}</td>'
                    f'<td style="text-align:center;padding:10px 14px">{sb}</td>'
                    f'</tr>'
                )
            st.markdown(
                f'''<div class="med-card" style="overflow:hidden">
  <table style="width:100%;border-collapse:collapse">
    <thead>
      <tr style="background:{BG_CARD2};border-bottom:2px solid {BORDER}">
        <th style="text-align:left;padding:10px 14px;font-size:0.7rem;font-weight:800;
                   color:{TEXT_MUTED};text-transform:uppercase;letter-spacing:0.07em">Test</th>
        <th style="text-align:right;padding:10px 14px;font-size:0.7rem;font-weight:800;
                   color:{TEXT_MUTED};text-transform:uppercase;letter-spacing:0.07em">Value</th>
        <th style="text-align:center;padding:10px 14px;font-size:0.7rem;font-weight:800;
                   color:{TEXT_MUTED};text-transform:uppercase;letter-spacing:0.07em">Status</th>
      </tr>
    </thead>
    <tbody>''' + rows_html + f'''</tbody>
  </table>
</div>''',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="med-card-soft" style="padding:18px 20px;color:{TEXT_SEC};">'
                f'No lab results found yet. Upload a report to populate this table.</div>',
                unsafe_allow_html=True,
            )

    with col_r:
        # Quick Ask
        st.markdown(
            f'<p class="med-kicker" style="margin-bottom:12px">Ask AI</p>',
            unsafe_allow_html=True,
        )
        for q in [
            "What do my latest results mean?",
            "Which values need attention?",
            "How can I improve my health?",
        ]:
            if st.button(q, use_container_width=True, key=f"qq_{q[:18]}"):
                _set_chat_context_from_latest_report(reports)
                st.session_state["prefill_q"] = q
                st.session_state["current_page"] = "Chat"; st.rerun()

        custom = st.text_input("Ask a question", placeholder="Ask something specific…", key="dash_q",
                               label_visibility="collapsed")
        if st.button("Ask →", type="primary", use_container_width=True, key="dash_ask"):
            if custom.strip():
                _set_chat_context_from_latest_report(reports)
                st.session_state["prefill_q"] = custom.strip()
                st.session_state["current_page"] = "Chat"; st.rerun()

        # Recent consultations
        if hist:
            st.markdown(
                f'<p class="med-kicker" style="margin:20px 0 12px">Recent Consultations</p>',
                unsafe_allow_html=True,
            )
            for item in hist[:4]:
                q2   = (item.get("question") or "")[:72]
                conf = item.get("confidence_level") or "low"
                date = (item.get("created_at") or "")[:10]
                cbadge = confidence_badge(conf)
                st.markdown(
                                        f'''<div class="med-card" style="padding:12px 14px;margin-bottom:8px">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px">
    <p style="margin:0;font-size:0.82rem;color:{TEXT};flex:1;line-height:1.4">{q2}&#8230;</p>
    {cbadge}
  </div>
  <p style="margin:5px 0 0;font-size:0.7rem;color:{TEXT_MUTED}">{date}</p>
</div>''',
                    unsafe_allow_html=True,
                )

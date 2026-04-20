"""Upload Report page."""
from __future__ import annotations
import os, time, requests
import streamlit as st
from app.frontend.api_client import API_BASE as _API, auth_headers as _hdr
from app.frontend.components.theme import (
    inject_css, BG_CARD, BG_CARD2, BORDER, BORDER2,
    PRIMARY, SECONDARY, SUCCESS, WARNING, DANGER,
    TEXT, TEXT_SEC, TEXT_MUTED, status_badge,
)


def _poll(report_id: str):
    steps = ["Parsing PDF content…","Running AI extraction…",
             "Matching reference ranges…","Finalising results…"]
    bar = st.progress(0, text=steps[0])

    def _normalise(raw):
        """Always return a dict so callers can use .get() safely."""
        if isinstance(raw, list):
            return {"results": raw}
        if isinstance(raw, dict):
            return raw
        return {}

    for i, step in enumerate(steps):
        bar.progress((i+1)*25, text=step)
        time.sleep(1.5)  # Increased from 0.9 to 1.5 seconds for Groq API processing
        try:
            r = requests.get(f"{_API}/reports/{report_id}/results", headers=_hdr(), timeout=10)
            if r.ok:
                d = _normalise(r.json())
                results = d.get("results", []) if isinstance(d.get("results"), list) else []
                # Only consider complete if we actually have test results
                if len(results) > 0:
                    bar.progress(100, text="Complete ✓")
                    return d
        except: pass
    
    # Final check after all steps - give it one more try with longer timeout
    try:
        r = requests.get(f"{_API}/reports/{report_id}/results", headers=_hdr(), timeout=20)
        if r.ok:
            d = _normalise(r.json())
            return d
    except: pass
    return None


def _show_results(data) -> None:
    # Normalise: API may return a plain list or a dict wrapper
    if isinstance(data, list):
        data = {"results": data}
    tests = data.get("results") or data.get("extracted_tests") or []
    
    # Don't show success message if no tests found (extraction may still be processing)
    if not tests:
        st.info("⏳ Extraction in progress... Refresh in a few seconds.")
        return
    
    st.markdown(
        f'<div style="background:#F0FDF4;border:1px solid #BBF7D0;'
        f'border-left:4px solid {SUCCESS};border-radius:12px;'
        f'padding:14px 18px;margin-bottom:16px;display:flex;align-items:center;gap:10px">'
        f'<span style="font-size:1.1rem">&#10003;</span>'
        f'<span style="font-weight:700;color:{SUCCESS}">Extraction complete — '
        f'{len(tests)} test(s) found</span></div>',
        unsafe_allow_html=True,
    )
    c1,c2 = st.columns(2)
    with c1:
        if st.button("&#128172; Chat about this report", use_container_width=True, type="primary", key="up_chat"):
            st.session_state["active_report_id"] = data.get("report_id") or st.session_state.get("_last_rid")
            st.session_state["current_page"]="Chat"; st.rerun()
    with c2:
        if st.button("&#128200; View Trends", use_container_width=True, key="up_trend"):
            st.session_state["current_page"]="Trends"; st.rerun()

    if not tests: return
    sorted_t = sorted(tests, key=lambda x: 0 if (x.get("status","")).lower()!="normal" else 1)
    rows = ""
    for t in sorted_t:
        tn  = t.get("test_name","-")
        val = str(t.get("value","-"))
        un  = t.get("unit","") or ""
        rl  = t.get("reference_range_low") or t.get("ref_low") or ""
        rh  = t.get("reference_range_high") or t.get("ref_high") or ""
        ref = f"{rl}–{rh} {un}".strip("– ") if rl or rh else un
        ss  = (t.get("status") or "").lower()
        bg  = "#FFF1F2" if ss in ("high","critical") else "#FFFBEB" if ss=="low" else "transparent"
        vc  = DANGER if ss in ("high","critical") else WARNING if ss=="low" else TEXT
        rows += (
            f'<tr style="background:{bg};border-bottom:1px solid {BORDER}">'
            f'<td style="padding:10px 14px;font-weight:600;color:{TEXT};font-size:0.84rem">{tn}</td>'
            f'<td style="text-align:right;padding:10px 14px;font-family:monospace;font-weight:700;color:{vc};font-size:0.84rem">{val} {un}</td>'
            f'<td style="text-align:right;padding:10px 14px;color:{TEXT_MUTED};font-size:0.78rem">{ref}</td>'
            f'<td style="text-align:center;padding:10px 14px">{status_badge(t.get("status",""))}</td>'
            f'</tr>'
        )
    st.markdown(
        f'''<div style="background:{BG_CARD};border:1px solid {BORDER};
                       border-radius:14px;overflow:hidden;margin-top:16px;
                       box-shadow:0 1px 4px rgba(99,102,241,0.07)">
  <table style="width:100%;border-collapse:collapse">
    <thead><tr style="background:{BG_CARD2};border-bottom:2px solid {BORDER}">
      <th style="text-align:left;padding:10px 14px;font-size:0.7rem;font-weight:800;color:{TEXT_MUTED};text-transform:uppercase;letter-spacing:0.07em">Test</th>
      <th style="text-align:right;padding:10px 14px;font-size:0.7rem;font-weight:800;color:{TEXT_MUTED};text-transform:uppercase;letter-spacing:0.07em">Value</th>
      <th style="text-align:right;padding:10px 14px;font-size:0.7rem;font-weight:800;color:{TEXT_MUTED};text-transform:uppercase;letter-spacing:0.07em">Reference</th>
      <th style="text-align:center;padding:10px 14px;font-size:0.7rem;font-weight:800;color:{TEXT_MUTED};text-transform:uppercase;letter-spacing:0.07em">Status</th>
    </tr></thead>
    <tbody>''' + rows + f'''</tbody>
  </table>
</div>''',
        unsafe_allow_html=True,
    )


def show_upload_page() -> None:
    inject_css()
    st.markdown(
        f'<div class="med-card" style="padding:18px 20px;margin-bottom:18px">'
        f'<div class="med-kicker" style="margin-bottom:8px">Report ingestion</div>'
        f'<h1 style="margin:0 0 6px;font-size:1.45rem;font-weight:900;color:{TEXT};letter-spacing:-0.02em">'
        f'Upload Lab Report</h1>'
        f'<p style="margin:0;color:{TEXT_MUTED};font-size:0.86rem;line-height:1.6">'
        f'Drop in a PDF and the app will extract values, map ranges, and prepare the report for chat and trend analysis.</p></div>',
        unsafe_allow_html=True,
    )

    _, cc, _ = st.columns([0.4,3,0.4])
    with cc:
        f = st.file_uploader("Drop your PDF here or click to browse",
                             type=["pdf"], key="up_file")
        if f:
            kb = round(len(f.getvalue())/1024,1)
            st.markdown(
                f'<div class="med-card-soft" style="padding:12px 16px;margin:12px 0;'
                f'display:flex;align-items:center;gap:12px">'
                f'<span style="font-size:1.4rem">&#128196;</span>'
                f'<div><p style="margin:0;font-size:0.875rem;font-weight:700;color:{TEXT}">{f.name}</p>'
                f'<p style="margin:0;font-size:0.72rem;color:{TEXT_MUTED}">{kb} KB &bull; PDF</p>'
                f'</div></div>',
                unsafe_allow_html=True,
            )
            if st.button("&#9889; Extract Results", use_container_width=True,
                         type="primary", key="up_go"):
                with st.spinner("Uploading…"):
                    try:
                        resp = requests.post(
                            f"{_API}/reports/upload",
                            files={"file":(f.name,f.getvalue(),"application/pdf")},
                            headers=_hdr(), timeout=60,
                        )
                    except requests.exceptions.ConnectionError:
                        st.error("Cannot reach the API."); st.stop()
                    except Exception as e:
                        st.error(f"Upload failed: {e}"); st.stop()
                if resp.ok:
                    rid = resp.json().get("report_id") or resp.json().get("id")
                    st.session_state["_last_rid"] = rid
                    data = _poll(str(rid))
                    if data: _show_results(data)
                    else: st.warning("Extraction still in progress — check back soon.")
                else:
                    try: msg = resp.json().get("detail","Upload failed.")
                    except: msg = resp.text[:200] or "Upload failed."
                    st.error(msg)

        st.markdown("<div style='height:24px'></div>", unsafe_allow_html=True)
        st.markdown(
                        f'''<div class="med-card" style="padding:18px 22px">
  <p style="margin:0 0 10px;font-size:0.72rem;font-weight:800;color:{TEXT_MUTED};
            text-transform:uppercase;letter-spacing:0.08em">Tips for best results</p>
  <ul style="margin:0;padding-left:16px;color:{TEXT_SEC};font-size:0.83rem;line-height:1.9">
    <li>Use clearly scanned PDFs with readable text</li>
    <li>Include the full report with reference ranges</li>
    <li>One report per date / visit for accurate trend tracking</li>
    <li>Maximum file size: 10 MB</li>
  </ul>
</div>''',
            unsafe_allow_html=True,
        )

"""Chat page — ChatGPT-style bubbles + live progress."""
from __future__ import annotations
import os, time, requests
import html
import streamlit as st
from app.frontend.api_client import API_BASE as _API, auth_headers as _hdr
from app.frontend.components.theme import (
    inject_css, BG_CARD, BG_CARD2, BORDER, BORDER2,
    PRIMARY, SECONDARY, SUCCESS, WARNING, DANGER,
    TEXT, TEXT_SEC, TEXT_MUTED, confidence_badge,
)
from app.frontend.components.trend_chart import render_trend_chart


@st.cache_data(ttl=30)


@st.cache_data(ttl=30)
def _hist_list(tok):
    try: r = requests.get(f"{_API}/history", headers={"Authorization":f"Bearer {tok}"}, timeout=8); return r.json() if r.ok else []
    except: return []


@st.cache_data(ttl=60)
def _reports(tok):
    try:
        r = requests.get(f"{_API}/patients/me/reports", headers={"Authorization":f"Bearer {tok}"}, timeout=8)
        return r.json() if r.ok else []
    except:
        return []


@st.cache_data(ttl=30)
def _get_lab_history(tok, test_name: str):
    """Fetch historical data for a specific test to render trend charts."""
    try:
        r = requests.get(
            f"{_API}/patients/me/lab-results/history",
            params={"test_name": test_name, "limit": 10},
            headers={"Authorization": f"Bearer {tok}"},
            timeout=8
        )
        if r.ok:
            return r.json()
    except:
        pass
    return []
    

@st.cache_data(ttl=30)
def _get_all_lab_results(tok):
    """Fetch all lab results for the patient."""
    try:
        r = requests.get(
            f"{_API}/patients/me/lab-results/latest",
            headers={"Authorization": f"Bearer {tok}"},
            timeout=8
        )
        if r.ok:
            return r.json()
    except:
        pass
    return []


def _ask(question: str):
    payload = {"question": question, "stm_context": st.session_state.get("stm_messages",[])}
    rid = st.session_state.get("active_report_id")
    if rid: payload["report_id"] = rid
    try:
        r = requests.post(f"{_API}/chat/ask", json=payload, headers=_hdr(), timeout=180)
        if r.ok: return r.json()
        st.error(f"API error {r.status_code}: {(r.text or '')[:200]}")
    except requests.exceptions.ConnectionError: st.error("Cannot reach the API on port 8000.")
    except requests.exceptions.Timeout: st.error("The AI is taking too long — please try again.")
    except Exception as e: st.error(f"Error: {e}")
    return None


def _section_card(title: str, content: str) -> str:
    if not content:
        return ""
    safe_title = html.escape(title)
    safe_content = html.escape(content)
    return (
        f'<div class="med-card-soft" style="padding:14px 16px;margin-top:12px">'
        f'<div class="med-kicker" style="margin-bottom:8px">{safe_title}</div>'
        f'<div class="med-muted" style="color:{TEXT};line-height:1.75;white-space:pre-wrap">{safe_content}</div>'
        f'</div>'
    )


def _render_user_bubble(text: str) -> None:
    safe_text = html.escape(text or "")
    st.markdown(
        f'''<div style="display:flex;justify-content:flex-end;margin-bottom:14px">
  <div style="background:linear-gradient(135deg,{PRIMARY},{SECONDARY});color:white;
              border-radius:16px 6px 16px 16px;padding:12px 18px;
              max-width:78%;font-size:0.9rem;line-height:1.65;
              box-shadow:0 8px 18px rgba(99,102,241,0.24);white-space:pre-wrap">{safe_text}</div>
</div>''',
        unsafe_allow_html=True,
    )


def _show_compact_progress() -> None:
    steps = [
        "Classifying your question",
        "Searching knowledge base",
        "Analysing report context",
        "Generating personalised answer",
    ]
    slot = st.empty()
    for i, step in enumerate(steps, start=1):
        slot.markdown(
            f'<div class="med-card-soft" style="padding:12px 14px;margin:6px 0 14px">'
            f'<div class="med-kicker" style="margin-bottom:4px">Thinking</div>'
            f'<div style="font-size:0.87rem;color:{TEXT};font-weight:600">{i}/{len(steps)} · {step}…</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        time.sleep(0.16)
    slot.empty()


def _render_ai(msg: dict) -> None:
    d    = msg.get("data") or {}
    # API returns: {"response": {"direct_answer":..., "confidence":..., ...}, "trend_data":[...]}
    resp = d.get("response") if isinstance(d.get("response"), dict) else {}
    ans  = resp.get("direct_answer") or msg.get("content") or ""
    conf = resp.get("confidence") or "low"
    intent = (resp.get("intent_handled") or "general").replace("_"," ").title()
    guidelines = resp.get("guideline_context") or ""
    trend_sum  = resp.get("trend_summary") or ""
    watch_for  = resp.get("watch_for") or ""
    sources    = resp.get("sources") or []
    trend_data = d.get("trend_data") or []
    cbadge     = confidence_badge(conf)
    safe_intent = html.escape(intent)

    # AI card
    st.markdown(
        f'''<div style="display:flex;align-items:flex-start;gap:12px;margin-bottom:16px">
  <div style="background:linear-gradient(135deg,{PRIMARY},{SECONDARY});
              width:34px;height:34px;border-radius:10px;display:flex;align-items:center;
              justify-content:center;color:white;font-weight:800;font-size:0.85rem;
              flex-shrink:0;margin-top:2px">M</div>
  <div style="flex:1;min-width:0">
    <div class="med-card" style="padding:16px 18px;border-radius:18px 18px 18px 6px">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;padding-bottom:10px;border-bottom:1px solid {BORDER}">
                <span class="med-kicker">{safe_intent}</span>
        <span style="margin-left:auto">{cbadge}</span>
      </div>
            <div class="med-answer">{ans}</div>
      {_section_card("Guideline context", guidelines)}
      {_section_card("Trend analysis", trend_sum)}
      {_section_card("Watch for", watch_for)}
      {'' if not sources else ''}
    </div>''',
        unsafe_allow_html=True,
    )
    
    # Render trend charts if we have trend data
    if trend_data:
        st.markdown(
            f'<div class="med-card-soft" style="padding:14px 16px;margin-top:12px">'
            f'<div class="med-kicker" style="margin-bottom:12px">📊 Trend Visualizations</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        # Create columns for charts (2 per row)
        chart_cols = st.columns(2)
        for idx, trend in enumerate(trend_data[:6]):  # Limit to 6 charts
            test_name = trend.get("test_name", "Unknown Test")
            data_points = trend.get("data_points") or trend.get("history") or []
            unit = trend.get("unit", "")
            ref_low = trend.get("reference_low") or trend.get("ref_low")
            ref_high = trend.get("reference_high") or trend.get("ref_high")
            
            if data_points and len(data_points) >= 2:
                with chart_cols[idx % 2]:
                    render_trend_chart(
                        test_name=test_name,
                        data_points=data_points,
                        unit=unit,
                        ref_low=ref_low,
                        ref_high=ref_high,
                    )
    
    # Try to render charts for abnormal values from extracted tests
    _render_abnormal_trends(d)
    
    if sources:
        st.markdown(
            f'<div class="med-card-soft" style="padding:12px 14px;margin-top:12px">'
            f'<div class="med-kicker" style="margin-bottom:8px">Sources</div>'
            f'<div style="display:flex;flex-wrap:wrap;gap:6px">'
            + "".join(
                f'<span class="med-pill" style="background:{BG_CARD2};color:{PRIMARY};">{html.escape(str(s))}</span>'
                for s in sources[:5]
            )
            + '</div></div>',
            unsafe_allow_html=True,
        )
    st.markdown(
        f'<p style="font-size:0.68rem;color:{TEXT_MUTED};margin:8px 0 0">'
        f'AI-generated — always consult a qualified doctor for medical decisions.</p>',
        unsafe_allow_html=True,
    )
    st.markdown("</div></div>", unsafe_allow_html=True)


def _render_abnormal_trends(data: dict) -> None:
    """Render trend charts for abnormal values if we have historical data."""
    tok = st.session_state.get("jwt_token", "")
    if not tok:
        return
    
    # Get all lab results to find abnormal ones
    all_results = _get_all_lab_results(tok)
    if not all_results:
        return
    
    # Find abnormal values
    abnormal_tests = [
        r for r in all_results 
        if (r.get("status") or "").lower() in ("high", "low", "critical")
    ]
    
    if not abnormal_tests:
        return
    
    # Limit to first 4 abnormal tests
    abnormal_tests = abnormal_tests[:4]
    
    st.markdown(
        f'<div class="med-card-soft" style="padding:14px 16px;margin-top:12px">'
        f'<div class="med-kicker" style="margin-bottom:8px">📈 Historical Trends for Abnormal Values</div>'
        f'<p style="font-size:0.8rem;color:{TEXT_SEC};margin-bottom:12px">'
        f'Tracking how your abnormal values have changed over time</p>'
        f'</div>',
        unsafe_allow_html=True,
    )
    
    # Create columns for charts
    chart_cols = st.columns(2)
    charts_rendered = 0
    
    for idx, test in enumerate(abnormal_tests):
        test_name = test.get("test_name", "")
        if not test_name:
            continue
        
        # Get historical data for this test
        history = _get_lab_history(tok, test_name)
        if not history or len(history) < 2:
            # If no history, create single-point data
            history = [{
                "date": test.get("report_date") or test.get("created_at", "")[:10],
                "value": test.get("value"),
                "status": test.get("status")
            }]
        
        # Ensure we have at least 2 points for a trend line
        if len(history) >= 1:
            with chart_cols[charts_rendered % 2]:
                render_trend_chart(
                    test_name=test_name,
                    data_points=history,
                    unit=test.get("unit", ""),
                    ref_low=test.get("reference_range_low") or test.get("ref_low"),
                    ref_high=test.get("reference_range_high") or test.get("ref_high"),
                )
            charts_rendered += 1
        
        if charts_rendered >= 4:
            break


def show_chat_page() -> None:
    inject_css()
    st.markdown(
        """
        <style>
        .st-key-history_panel > [data-testid="stVerticalBlockBorderWrapper"],
        .st-key-chat_panel > [data-testid="stVerticalBlockBorderWrapper"] {
          border-radius: 16px !important;
          border-color: #D6DAF8 !important;
          background: #FFFFFF !important;
          box-shadow: 0 8px 20px rgba(79, 70, 229, 0.06) !important;
          height: calc(100vh - 300px) !important;
          overflow-y: auto !important;
        }
        .st-key-history_list {
          max-height: calc(100vh - 310px) !important;
          overflow-y: auto !important;
          overflow-x: hidden !important;
          padding-right: 4px !important;
        }
        .st-key-chat_list {
          max-height: calc(100vh - 330px) !important;
          overflow-y: auto !important;
          overflow-x: hidden !important;
          padding: 2px 4px 2px 2px !important;
        }
        .st-key-history_list .stButton > button {
          text-align: left !important;
          justify-content: flex-start !important;
          line-height: 1.35 !important;
          min-height: 54px !important;
          border-radius: 12px !important;
          font-size: 0.83rem !important;
          color: #1F2937 !important;
          border: 1px solid #E5E7EB !important;
          background: #F8FAFF !important;
        }
        .st-key-history_list .stButton > button:hover {
          background: #EEF2FF !important;
          border-color: #C7D2FE !important;
          color: #4338CA !important;
        }
        [data-testid="stChatInput"] {
          position: sticky !important;
          bottom: 0 !important;
          background: transparent !important;
          padding-top: 8px !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    tok = st.session_state.get("jwt_token","")
    prefill = st.session_state.pop("prefill_q", None)

    if not st.session_state.get("active_report_id"):
        reports = _reports(tok)
        if reports:
            latest_report = reports[0]
            report_id = latest_report.get("report_id") or latest_report.get("id")
            if report_id:
                st.session_state["active_report_id"] = str(report_id)

    # Header
    st.markdown(
        f'<div class="med-card" style="padding:18px 20px;margin-bottom:18px">'
        f'<div class="med-kicker" style="margin-bottom:8px">AI Health Chat</div>'
        f'<h1 style="margin:0 0 6px;font-size:1.5rem;font-weight:900;color:{TEXT};letter-spacing:-0.02em">'
        f'Ask about your report, results, or symptoms</h1>'
        f'<p style="margin:0;color:{TEXT_MUTED};font-size:0.86rem;line-height:1.6">'
        f'Use the uploaded PDF as context, then ask follow-up questions about values, trends, and what to improve.</p></div>',
        unsafe_allow_html=True,
    )

    # Report context banner
    rid = st.session_state.get("active_report_id")
    if rid:
        bc, dc = st.columns([10,2])
        with bc:
            st.markdown(
                f'<div class="med-card-soft" style="padding:10px 16px;border-left:4px solid {PRIMARY};'
                f'margin-bottom:14px;font-size:0.85rem;font-weight:700;color:{PRIMARY}">'
                f'Answering in context of report #{rid}</div>',
                unsafe_allow_html=True,
            )
        with dc:
            if st.button("Clear report", key="dis_rep", use_container_width=True):
                st.session_state["active_report_id"] = None
                st.rerun()

    # Layout
    hcol, mcol = st.columns([1.08, 3.2], gap="medium")

    with hcol:
        st.markdown(
            '<div style="font-size:0.72rem;font-weight:800;letter-spacing:0.08em;'
            f'color:{TEXT_MUTED};text-transform:uppercase;margin:0 0 8px">History</div>',
            unsafe_allow_html=True,
        )
        if st.button("＋  New Chat", use_container_width=True, key="new_chat"):
            st.session_state["stm_messages"] = []
            _hist_list.clear()
            st.rerun()
        with st.container(border=True, key="history_panel"):
            history = _hist_list(tok)[:120]
            if not history:
                st.markdown(
                    f'<div class="med-card-soft" style="padding:12px 12px;color:{TEXT_MUTED};font-size:0.82rem">'
                    f'No previous chats yet.</div>',
                    unsafe_allow_html=True,
                )
            for _hi, item in enumerate(history):
                q_full = (item.get("question") or "").strip()
                dt = (item.get("created_at") or "")[:10]
                q_show = (q_full[:64] + "...") if len(q_full) > 64 else (q_full or "Untitled")
                _hkey = f"h_{item.get('id') or _hi}"
                if st.button(f"🗨️  {q_show}", use_container_width=True, key=_hkey):
                    st.session_state["stm_messages"] = [
                        {"role": "user", "content": item.get("question", "")},
                        {
                            "role": "assistant",
                            "content": item.get("response", {}).get("direct_answer", "") if isinstance(item.get("response"), dict) else item.get("answer", ""),
                            "data": item,
                        },
                    ]
                    st.rerun()
                st.caption(dt or "—")

    with mcol:
        msgs = st.session_state.get("stm_messages", [])

        with st.container(border=True, key="chat_panel"):
            if not msgs and not prefill:
                st.markdown(
                    f'''<div class="med-card" style="text-align:center;padding:70px 28px;color:{TEXT_MUTED}">
  <div style="font-size:3.2rem;margin-bottom:14px">💬</div>
  <h3 style="color:{TEXT};font-weight:800;margin:0 0 8px;font-size:1.18rem">
      Start a conversation</h3>
  <p style="font-size:0.9rem;margin:0 auto;max-width:380px;line-height:1.75;color:{TEXT_SEC}">
      Ask what your uploaded report means, which values are normal or abnormal, and what you can do next.</p>
  <div style="display:flex;flex-wrap:wrap;justify-content:center;gap:8px;margin-top:18px">
      <span class="med-pill">Explain my report</span>
      <span class="med-pill">What is abnormal?</span>
      <span class="med-pill">How do I improve this?</span>
  </div>
</div>''',
                    unsafe_allow_html=True,
                )
            else:
                for msg in msgs:
                    if msg["role"] == "user":
                        _render_user_bubble(msg.get("content", ""))
                    else:
                        _render_ai(msg)

            typing_indicator = st.empty()

        question = st.chat_input("Ask about your health…", key="chat_in")
        final_q = prefill or question

        if final_q:
            st.session_state.setdefault("stm_messages", []).append(
                {"role": "user", "content": final_q}
            )
            with typing_indicator.container():
                _render_user_bubble(final_q)
                with st.spinner("Classifying question and fetching medical guidelines..."):
                    result = _ask(final_q)

            if not result:
                st.markdown(
                    f'<div class="med-card-soft" style="padding:10px 14px;border-left:4px solid {DANGER};margin-bottom:10px">'
                    f'<span style="font-size:0.85rem;color:{DANGER};font-weight:700">Unable to generate a response. Please try again.</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            if result:
                _ans_text = (result.get("response") or {}).get("direct_answer", "") if isinstance(result.get("response"), dict) else ""
                st.session_state["stm_messages"].append(
                    {"role": "assistant", "content": _ans_text, "data": result}
                )
                if result.get("ltm_summary"):
                    st.session_state["ltm_summary"] = result["ltm_summary"]
                _hist_list.clear()
                st.rerun()

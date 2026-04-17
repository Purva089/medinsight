"""Consultation History page."""
from __future__ import annotations
import os, datetime, requests
import streamlit as st
from app.frontend.api_client import API_BASE as _API, auth_headers as _hdr
from app.frontend.components.theme import (
    inject_css, BG_CARD, BG_CARD2, BORDER, BORDER2,
    PRIMARY, SECONDARY, SUCCESS, WARNING, DANGER, ACCENT,
    TEXT, TEXT_SEC, TEXT_MUTED, confidence_badge,
)


@st.cache_data(ttl=30, show_spinner=False)


@st.cache_data(ttl=30, show_spinner=False)
def _fetch_history(token: str):
    try:
        r = requests.get(f"{_API}/history", headers={"Authorization": f"Bearer {token}"},
                         timeout=20)
        if r.ok:
            d = r.json()
            return d if isinstance(d, list) else d.get("items", [])
    except: pass
    return []


def _fmt_date(raw: str) -> str:
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try: return datetime.datetime.strptime(raw[:26], fmt).strftime("%d %b %Y, %H:%M")
        except: pass
    return raw[:16] if raw else "—"


def _group_by_date(items):
    groups: dict[str, list] = {}
    for it in items:
        raw  = it.get("created_at") or it.get("timestamp") or ""
        date = raw[:10] if raw else "—"
        groups.setdefault(date, []).append(it)
    return groups


def show_history_page() -> None:
    inject_css()
    st.markdown(
        f'<div class="med-card" style="padding:18px 20px;margin-bottom:18px">'
        f'<div class="med-kicker" style="margin-bottom:8px">Conversation archive</div>'
        f'<h1 style="margin:0 0 6px;font-size:1.45rem;font-weight:900;color:{TEXT};letter-spacing:-0.02em">Consultation History</h1>'
        f'<p style="margin:0;color:{TEXT_MUTED};font-size:0.86rem;line-height:1.6">All your AI health conversations in one place.</p></div>',
        unsafe_allow_html=True,
    )

    tok = st.session_state.get("jwt_token","")
    all_items = _fetch_history(tok)

    if not all_items:
        st.markdown(
            f'<div class="med-card-soft" style="padding:18px 20px;color:{TEXT_SEC};margin-top:8px">'
            f'No consultations yet — start a chat to get personalised health insights.</div>',
            unsafe_allow_html=True,
        )
        if st.button("Start a Chat", type="primary"):
            st.session_state["current_page"]="Chat"; st.rerun()
        return

    # ── Filters ───────────────────────────────────────────────────────────────
    fc, tc, cc, _ = st.columns([1.2, 1.2, 1.4, 2])
    with fc:
        from_d = st.date_input("From", value=None, key="hist_from",
                               label_visibility="collapsed")
    with tc:
        to_d = st.date_input("To", value=None, key="hist_to",
                             label_visibility="collapsed")
    with cc:
        conf_f = st.selectbox("Confidence", ["All","High","Medium","Low"],
                              key="hist_conf", label_visibility="collapsed")

    items = all_items
    if from_d:
        items = [x for x in items
                 if (x.get("created_at","") or x.get("timestamp",""))[:10] >= str(from_d)]
    if to_d:
        items = [x for x in items
                 if (x.get("created_at","") or x.get("timestamp",""))[:10] <= str(to_d)]
    if conf_f != "All":
        items = [x for x in items
                 if (x.get("confidence_level") or x.get("confidence","")).lower() == conf_f.lower()]

    st.markdown(
        f'<p class="med-muted" style="margin:4px 0 16px">'
        f'{len(items)} consultation(s) found</p>',
        unsafe_allow_html=True,
    )

    # ── Download ──────────────────────────────────────────────────────────────
    if items:
        lines = []
        for it in items:
            ts = _fmt_date(it.get("created_at") or it.get("timestamp",""))
            q  = it.get("query") or it.get("question","")
            a  = it.get("answer") or it.get("response","")
            lines.append(f"[{ts}]\nQ: {q}\nA: {a}\n{'─'*60}")
        st.download_button("&#8681; Export all (.txt)", "\n".join(lines),
                           file_name="medinsight_history.txt",
                           mime="text/plain", key="hist_dl")

    # ── Timeline ──────────────────────────────────────────────────────────────
    groups = _group_by_date(items)
    for date_key in sorted(groups.keys(), reverse=True):
        # Date separator
        try:
            dt_obj = datetime.date.fromisoformat(date_key)
            today  = datetime.date.today()
            if dt_obj == today:             label = "Today"
            elif dt_obj == today - datetime.timedelta(days=1): label = "Yesterday"
            else: label = dt_obj.strftime("%A, %d %b %Y")
        except: label = date_key

        st.markdown(
            f'<div style="display:flex;align-items:center;gap:10px;margin:20px 0 10px">'
            f'<div style="width:9px;height:9px;border-radius:50%;background:{ACCENT};flex-shrink:0"></div>'
            f'<span style="font-size:0.72rem;font-weight:800;color:{TEXT_MUTED};'
            f'text-transform:uppercase;letter-spacing:0.08em">{label}</span>'
            f'<div style="flex:1;height:1px;background:{BORDER}"></div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        for idx, it in enumerate(groups[date_key]):
            q   = it.get("query") or it.get("question","") or "Untitled question"
            ans = it.get("answer") or it.get("response","") or "No response recorded."
            conf = it.get("confidence_level") or it.get("confidence","")
            ts  = _fmt_date(it.get("created_at") or it.get("timestamp",""))
            srcs = it.get("sources") or []
            cid  = it.get("consultation_id") or it.get("id","")

            with st.expander(f"&#128172;  {q[:90]}{'…' if len(q)>90 else ''}", expanded=False):
                # Question block
                st.markdown(
                    f'<div style="background:{BG_CARD2};border:1px solid {BORDER2};'
                    f'border-radius:10px;padding:12px 15px;margin-bottom:12px">'
                    f'<p style="margin:0 0 2px;font-size:0.68rem;font-weight:700;'
                    f'color:{PRIMARY};text-transform:uppercase;letter-spacing:0.07em">Question</p>'
                    f'<p style="margin:0;color:{TEXT};font-size:0.875rem;font-weight:500">{q}</p>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                # Answer
                st.markdown(
                    f'<p style="color:{TEXT_SEC};font-size:0.875rem;line-height:1.75;'
                    f'margin:0 0 12px">{ans}</p>',
                    unsafe_allow_html=True,
                )
                # Footer row
                meta_html = f'<span style="font-size:0.72rem;color:{TEXT_MUTED};margin-right:10px">&#128336; {ts}</span>'
                if conf:
                    meta_html += f'&nbsp;&nbsp;{confidence_badge(conf)}'
                st.markdown(meta_html, unsafe_allow_html=True)

                # Sources
                if srcs:
                    pills = " ".join(
                        f'<span style="background:{BG_CARD2};border:1px solid {BORDER2};'
                        f'color:{PRIMARY};padding:2px 9px;border-radius:20px;'
                        f'font-size:0.7rem;font-weight:600;margin:2px 2px 0 0;'
                        f'display:inline-block">{s}</span>'
                        for s in srcs
                    )
                    st.markdown(
                        f'<div style="margin-top:8px"><span style="font-size:0.7rem;'
                        f'color:{TEXT_MUTED};font-weight:700;text-transform:uppercase;'
                        f'letter-spacing:0.06em">Sources: </span>{pills}</div>',
                        unsafe_allow_html=True,
                    )

                st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
                if st.button("Continue this chat →", key=f"hist_cont_{date_key}_{idx}"):
                    st.session_state["prefill_q"] = q
                    st.session_state["current_page"] = "Chat"
                    st.rerun()

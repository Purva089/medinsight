"""
Source citations component — dark-theme expandable source pills.
Kept for backward-compat; chat.py / history.py now render inline.
"""
from __future__ import annotations

import streamlit as st

_ACCENT_BLUE = "#0EA5E9"
_TEXT_MUTED  = "#64748B"
_BORDER      = "#334155"


def render_sources(sources: list[str]) -> None:
    """Render an expander with clickable source pill links, or a 'no sources' caption."""
    if not sources:
        st.markdown(
            f'<p style="color:{_TEXT_MUTED};font-size:0.78rem;margin:4px 0">'
            f'No sources — answer based on general knowledge.</p>',
            unsafe_allow_html=True,
        )
        return

    pills_html = " &nbsp; ".join(
        f'<a href="{s}" target="_blank" style="display:inline-block;'
        f'background:rgba(14,165,233,0.12);border:1px solid rgba(14,165,233,0.3);'
        f'color:{_ACCENT_BLUE};padding:3px 12px;border-radius:20px;'
        f'font-size:0.72rem;text-decoration:none">🔗 Source {i+1}</a>'
        for i, s in enumerate(sources[:6])
    )

    with st.expander(f"📚 Sources ({len(sources)})"):
        st.markdown(pills_html, unsafe_allow_html=True)
        for i, url in enumerate(sources):
            st.markdown(f"- [{url}]({url})", unsafe_allow_html=False)

"""
Chat bubble component.
Thin wrapper around st.chat_message that renders a single message dict.
"""
from __future__ import annotations

import streamlit as st


def render_chat_bubble(message: dict) -> None:
    """
    Render a single message dict with role 'user' or 'assistant'.
    For assistant messages, renders only the text content — the caller
    (show_chat_page) is responsible for badges / charts / disclaimer.
    """
    role = message.get("role", "user")
    content = message.get("content", "")
    with st.chat_message(role):
        st.write(content)

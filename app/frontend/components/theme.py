"""MedInsight Design System v3 — Indigo / Violet Medical SaaS."""
from __future__ import annotations
import streamlit as st

# ── Sidebar ───────────────────────────────────────────────────────────────────
SIDEBAR_BG     = "#1E1B4B"
SIDEBAR_TEXT   = "#E0E7FF"
SIDEBAR_MUTED  = "#818CF8"
SIDEBAR_HOVER  = "rgba(255,255,255,0.06)"

# ── Page / cards ──────────────────────────────────────────────────────────────
BG       = "#F5F3FF"
BG_CARD  = "#FFFFFF"
BG_CARD2 = "#EEF2FF"
BG_CARD3 = "#F8FAFF"
BORDER   = "#E5E7EB"
BORDER2  = "#C7D2FE"

# ── Brand ─────────────────────────────────────────────────────────────────────
PRIMARY   = "#6366F1"
PRI_DARK  = "#4F46E5"
SECONDARY = "#7C3AED"
ACCENT    = "#06B6D4"

# ── Status ────────────────────────────────────────────────────────────────────
SUCCESS = "#059669"
WARNING = "#D97706"
DANGER  = "#DC2626"
INFO    = "#0284C7"

# ── Text ──────────────────────────────────────────────────────────────────────
TEXT       = "#111827"
TEXT_SEC   = "#4B5563"
TEXT_MUTED = "#9CA3AF"

COLORS = dict(bg=BG, card=BG_CARD, border=BORDER, primary=PRIMARY,
              success=SUCCESS, warning=WARNING, danger=DANGER,
              text=TEXT, muted=TEXT_MUTED)

_CSS = f"""
<style>
html, body {{
  background: {BG} !important;
  color: {TEXT} !important;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}}
[data-testid="stAppViewContainer"] {{
  background: {BG} !important;
}}
[data-testid="stMain"] .block-container {{
  background: {BG} !important;
  padding-top: 1.4rem !important;
  padding-bottom: 2.25rem !important;
  max-width: 1240px;
}}
[data-testid="stAppViewContainer"] h1,
[data-testid="stAppViewContainer"] h2,
[data-testid="stAppViewContainer"] h3,
[data-testid="stAppViewContainer"] h4,
[data-testid="stAppViewContainer"] p {{
  margin-top: 0;
}}

/* ── Sidebar ──────────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] {{
  background: {SIDEBAR_BG} !important;
  border-right: none !important;
}}
[data-testid="stSidebar"] * {{ color: {SIDEBAR_TEXT} !important; }}
[data-testid="stSidebar"] .stButton > button {{
  background: transparent !important;
  border: none !important;
  color: {SIDEBAR_TEXT} !important;
  width: 100%;
  text-align: left;
  padding: 10px 16px;
  border-radius: 10px;
  font-size: 0.875rem;
  font-weight: 500;
  transition: background 0.15s;
  justify-content: flex-start;
  letter-spacing: 0.01em;
}}
[data-testid="stSidebar"] .stButton > button:hover {{
  background: {SIDEBAR_HOVER} !important;
}}

/* Active nav — uses :has() adjacent sibling */
[data-testid="stMarkdownContainer"]:has(.nav-active) + div button {{
  background: rgba(99,102,241,0.22) !important;
  border-left: 3px solid {PRIMARY} !important;
  color: white !important;
  font-weight: 700 !important;
  padding-left: 13px !important;
}}

/* ── Chrome ───────────────────────────────────────────────────────────────── */
footer {{ visibility: hidden !important; height: 0 !important; }}
[data-testid="stDecoration"] {{ display: none !important; }}
/* Ensure header and sidebar toggle remain fully visible */
header[data-testid="stHeader"] {{
  display: block !important;
  visibility: visible !important;
  background: transparent !important;
}}
button[data-testid="collapsedControl"] {{
  display: inline-flex !important;
  visibility: visible !important;
  opacity: 1 !important;
  position: fixed !important;
  top: 0.75rem !important;
  left: 0.75rem !important;
  width: 2.25rem !important;
  height: 2.25rem !important;
  align-items: center !important;
  justify-content: center !important;
  background: {BG_CARD} !important;
  border: 1px solid {BORDER} !important;
  border-radius: 10px !important;
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.12) !important;
  color: {TEXT} !important;
  cursor: pointer !important;
  z-index: 99999 !important;
}}
button[data-testid="collapsedControl"] svg {{
  fill: {TEXT} !important;
  color: {TEXT} !important;
}}
button[data-testid="collapsedControl"]:hover {{
  background: {BG_CARD2} !important;
  border-color: {PRIMARY} !important;
}}
/* Hide Streamlit's auto-generated multipage sidebar nav (we use our own) */
[data-testid="stSidebarNav"] {{ display: none !important; }}
section[data-testid="stSidebarNav"] {{ display: none !important; }}

/* ── Metric cards ─────────────────────────────────────────────────────────── */
[data-testid="metric-container"] {{
  background: {BG_CARD};
  border: 1px solid {BORDER};
  border-radius: 14px;
  padding: 20px 22px;
  box-shadow: 0 8px 24px rgba(99,102,241,0.08);
  border-top: 3px solid {PRIMARY};
}}
[data-testid="metric-container"] label {{
  color: {TEXT_MUTED} !important;
  font-size: 0.7rem !important;
  font-weight: 700 !important;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}}
[data-testid="metric-container"] [data-testid="stMetricValue"] {{
  color: {TEXT} !important;
  font-size: 2rem !important;
  font-weight: 800 !important;
  line-height: 1.15 !important;
}}

/* ── Buttons ──────────────────────────────────────────────────────────────── */
.stButton > button {{
  background: {BG_CARD};
  border: 1.5px solid {BORDER};
  color: {TEXT_SEC};
  border-radius: 12px;
  font-size: 0.875rem;
  font-weight: 500;
  transition: all 0.15s;
  padding: 9px 18px;
}}
.stButton > button:hover {{
  border-color: {PRIMARY};
  color: {PRIMARY};
  background: {BG_CARD2};
}}
.stButton > button[kind="primary"] {{
  background: linear-gradient(135deg, {PRIMARY}, {SECONDARY}) !important;
  border: none !important;
  color: white !important;
  font-weight: 700 !important;
  box-shadow: 0 10px 24px rgba(99,102,241,0.28) !important;
}}
.stButton > button[kind="primary"]:hover {{
  transform: translateY(-1px) !important;
  box-shadow: 0 12px 28px rgba(99,102,241,0.35) !important;
}}

/* ── Inputs ───────────────────────────────────────────────────────────────── */
[data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea,
[data-testid="stSelectbox"] > div > div {{
  background: {BG_CARD} !important;
  color: {TEXT} !important;
  border: 1.5px solid {BORDER} !important;
  border-radius: 12px !important;
  font-size: 0.9rem !important;
}}
[data-testid="stTextInput"] input:focus,
[data-testid="stTextArea"] textarea:focus {{
  border-color: {PRIMARY} !important;
  box-shadow: 0 0 0 3px rgba(99,102,241,0.12) !important;
}}

/* ── Chat input ─── */
[data-testid="stChatInput"] {{
  background: {BG_CARD} !important;
  color: {TEXT} !important;
}}
[data-testid="stChatInput"] * {{
  color: {TEXT} !important;
  background: {BG_CARD} !important;
}}
[data-testid="stChatInput"] textarea {{
  background: {BG_CARD} !important;
  border: 1.5px solid {BORDER2} !important;
  border-radius: 16px !important;
  color: {TEXT} !important;
  box-shadow: 0 10px 24px rgba(99,102,241,0.08) !important;
}}
[data-testid="stChatInput"] textarea:focus {{
  border-color: {PRIMARY} !important;
  box-shadow: 0 0 0 3px rgba(99,102,241,0.1) !important;
}}

/* ── Chat layout ─────────────────────────────────────────────────────────── */
[data-testid="stChatMessage"] {{
  padding: 0.15rem 0 0.4rem 0 !important;
}}
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] {{
  line-height: 1.7;
}}

/* ── Scrollable panes for chat page ──────────────────────────────────────── */
.med-card {{
  background: {BG_CARD};
  border: 1px solid {BORDER};
  border-radius: 18px;
  box-shadow: 0 10px 28px rgba(99,102,241,0.08);
}}
.med-card-soft {{
  background: {BG_CARD3};
  border: 1px solid {BORDER2};
  border-radius: 16px;
  box-shadow: 0 8px 22px rgba(99,102,241,0.06);
}}
.med-pill {{
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.32rem 0.7rem;
  border-radius: 999px;
  background: {BG_CARD2};
  color: {PRIMARY};
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.02em;
  border: 1px solid {BORDER2};
}}
.med-muted {{
  color: {TEXT_MUTED};
  font-size: 0.8rem;
}}
.med-kicker {{
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-size: 0.68rem;
  font-weight: 800;
  color: {TEXT_MUTED};
}}
.med-answer {{
  color: {TEXT};
  font-size: 0.92rem;
  line-height: 1.78;
  white-space: pre-wrap;
}}

  /* ── Expanders ─── */
  details {{
    background: {BG_CARD} !important;
    border: 1px solid {BORDER} !important;
    border-radius: 14px !important;
    margin-bottom: 10px;
  }}
  details summary {{
    color: {TEXT} !important;
    font-weight: 600 !important;
    padding: 12px 16px !important;
    background: {BG_CARD} !important;
  }}
  [data-testid="stExpander"] {{
    background: {BG_CARD} !important;
    border-radius: 12px !important;
  }}
  [data-testid="stExpander"] details {{
    background: {BG_CARD} !important;
    border: 1px solid {BORDER} !important;
  }}
  [data-testid="stExpander"] details summary {{
    color: {TEXT} !important;
    background: {BG_CARD} !important;
  }}
  [data-testid="stExpander"] summary p {{
    color: {TEXT} !important;
  }}
  [data-testid="stExpander"] [data-testid="stExpanderDetails"] {{
    background: {BG_CARD} !important;
    color: {TEXT} !important;
  }}

  /* ── File uploader ────────────────────────────────────────────────────────── */
[data-testid="stFileUploadDropzone"] {{
  background: #FAFAFF !important;
  border: 2px dashed {BORDER2} !important;
  border-radius: 16px !important;
  padding: 40px !important;
}}
[data-testid="stFileUploadDropzone"]:hover {{
  border-color: {PRIMARY} !important;
  background: {BG_CARD2} !important;
}}

/* ── Progress bar ─────────────────────────────────────────────────────────── */
[data-testid="stProgressBar"] > div > div {{
  background: linear-gradient(90deg, {PRIMARY}, {SECONDARY}) !important;
  border-radius: 4px;
}}

/* ── Tabs ─────────────────────────────────────────────────────────────────── */
[data-testid="stTabs"] [data-baseweb="tab-list"] {{
  background: {BG_CARD2} !important;
  border-radius: 12px;
  border: 1px solid {BORDER};
  padding: 4px;
  gap: 2px;
}}
[data-testid="stTabs"] [data-baseweb="tab"] {{
  background: transparent !important;
  color: {TEXT_MUTED} !important;
  border-radius: 9px !important;
  border: none !important;
  font-weight: 500 !important;
}}
[data-testid="stTabs"] [aria-selected="true"] {{
  background: {BG_CARD} !important;
  color: {PRIMARY} !important;
  font-weight: 700 !important;
  box-shadow: 0 1px 3px rgba(99,102,241,0.15);
}}

/* ── Date input ───────────────────────────────────────────────────────────── */
[data-testid="stDateInput"] input {{
  background: {BG_CARD} !important;
  border: 1.5px solid {BORDER} !important;
  border-radius: 10px !important;
  color: {TEXT} !important;
}}

/* ── Alerts ───────────────────────────────────────────────────────────────── */
[data-testid="stAlert"] {{ border-radius: 12px !important; }}

/* ── Dataframe / table polish ────────────────────────────────────────────── */
[data-testid="stDataFrame"] {{
  background: {BG_CARD} !important;
  border-radius: 14px !important;
  overflow: hidden !important;
  border: 1px solid {BORDER} !important;
  box-shadow: 0 8px 24px rgba(99,102,241,0.06) !important;
}}

/* ── Divider ──────────────────────────────────────────────────────────────── */
hr {{ border-color: {BORDER} !important; margin: 1.5rem 0 !important; }}

/* ── Status widget ────────────────────────────────────────────────────────── */
[data-testid="stStatusWidget"] {{
  background: {BG_CARD2} !important;
  border: 1px solid {BORDER2} !important;
  border-radius: 12px !important;
}}
</style>
"""


def inject_css() -> None:
    """Inject the full design system CSS. Call once per page render."""
    st.markdown(_CSS, unsafe_allow_html=True)


# ── HTML helpers ──────────────────────────────────────────────────────────────

def badge(label: str, bg: str = PRIMARY, fg: str = "white") -> str:
    return (
        f'<span style="background:{bg};color:{fg};padding:3px 10px;'
        f'border-radius:20px;font-size:0.68rem;font-weight:700;'
        f'letter-spacing:0.05em;display:inline-block">{label}</span>'
    )


def status_badge(status: str) -> str:
    s = (status or "").lower()
    if s == "normal":
        return badge("NORMAL", "#DCFCE7", SUCCESS)
    if s in ("high", "critical"):
        return badge(s.upper(), "#FEE2E2", DANGER)
    if s == "low":
        return badge("LOW", "#FEF3C7", WARNING)
    return badge(s.upper() or "—", "#F3F4F6", TEXT_MUTED)


def confidence_badge(level: str) -> str:
    l = (level or "low").lower()
    if l == "high":   return badge("HIGH",   "#DCFCE7", SUCCESS)
    if l == "medium": return badge("MED",    "#FEF3C7", WARNING)
    return             badge("LOW",    "#FEE2E2", DANGER)


def page_header(title: str, subtitle: str = "") -> None:
    sub = (
        f'<p style="margin:4px 0 0;color:{TEXT_SEC};font-size:0.875rem">'
        f'{subtitle}</p>'
        if subtitle else ""
    )
    st.markdown(
        f'<div style="margin-bottom:28px">'
        f'<h1 style="margin:0;font-size:1.5rem;font-weight:800;color:{TEXT};'
        f'letter-spacing:-0.02em">{title}</h1>{sub}</div>',
        unsafe_allow_html=True,
    )

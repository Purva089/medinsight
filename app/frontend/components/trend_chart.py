"""Plotly trend chart — indigo/violet palette v3."""
from __future__ import annotations
import streamlit as st
import plotly.graph_objects as go

# Palette constants (mirrors theme.py)
_PRIMARY   = "#6366F1"   # indigo-500
_DANGER    = "#DC2626"   # red
_WARNING   = "#D97706"   # amber
_SUCCESS   = "#059669"   # emerald
_BG        = "#F5F3FF"   # page background (violet-50)
_GRID      = "#E5E7EB"   # gray-200
_TEXT      = "#111827"
_TEXT_SEC  = "#4B5563"


def render_trend_chart(
    test_name: str,
    data_points: list[dict],
    unit: str = "",
    # Accept both naming conventions
    ref_low: float | None = None,
    ref_high: float | None = None,
    reference_low: float | None = None,
    reference_high: float | None = None,
) -> None:
    """Render an indigo-styled Plotly chart directly into Streamlit."""
    if not data_points:
        st.info(f"No data available for {test_name}")
        return
    
    r_low  = ref_low  if ref_low  is not None else reference_low
    r_high = ref_high if ref_high is not None else reference_high

    dates  = [p.get("date") or p.get("test_date") or p.get("report_date") or "" for p in data_points]
    values = [p.get("value") for p in data_points]
    
    # Filter out None values
    valid_data = [(d, v) for d, v in zip(dates, values) if v is not None]
    if not valid_data:
        st.info(f"No valid data points for {test_name}")
        return
    
    dates, values = zip(*valid_data)
    dates = list(dates)
    values = list(values)

    # Per-point marker colors
    marker_colors = []
    for p in data_points:
        if p.get("value") is None:
            continue
        s = (p.get("status") or "").lower()
        if s in ("high", "critical"): marker_colors.append(_DANGER)
        elif s == "low":              marker_colors.append(_WARNING)
        else:                         marker_colors.append(_SUCCESS)

    # Line color: red if majority out-of-range, else indigo
    n_abnormal = sum(1 for c in marker_colors if c != _SUCCESS)
    line_color = _DANGER if n_abnormal > len(marker_colors) / 2 else _PRIMARY

    fig = go.Figure()

    # Shaded normal band
    if r_low is not None and r_high is not None:
        fig.add_hrect(
            y0=r_low, y1=r_high,
            fillcolor="rgba(5,150,105,0.07)",
            line_width=0,
            annotation_text="Normal range",
            annotation_position="top left",
            annotation_font_color=_SUCCESS,
            annotation_font_size=10,
        )

    # Main trace
    y_label = f"{test_name} ({unit})" if unit else test_name
    fig.add_trace(go.Scatter(
        x=dates, y=values,
        mode="lines+markers",
        name=y_label,
        line=dict(color=line_color, width=2.5, shape="spline", smoothing=0.6),
        marker=dict(
            color=marker_colors, size=10,
            line=dict(color="white", width=2),
            symbol="circle",
        ),
        hovertemplate=(
            f"<b>{test_name}</b><br>"
            "Date: %{x}<br>"
            f"Value: %{{y}} {unit}<extra></extra>"
        ),
    ))

    # Reference lines
    if r_high is not None:
        fig.add_hline(
            y=r_high,
            line_dash="dash", line_color=_DANGER, line_width=1.5,
            annotation_text=f"High  {r_high}",
            annotation_position="top right",
            annotation_font_color=_DANGER,
            annotation_font_size=10,
        )
    if r_low is not None:
        fig.add_hline(
            y=r_low,
            line_dash="dash", line_color=_WARNING, line_width=1.5,
            annotation_text=f"Low  {r_low}",
            annotation_position="bottom right",
            annotation_font_color=_WARNING,
            annotation_font_size=10,
        )

    fig.update_layout(
        paper_bgcolor="white",
        plot_bgcolor=_BG,
        font=dict(family="Inter, -apple-system, sans-serif", color=_TEXT, size=12),
        title=dict(
            text=y_label,
            font=dict(size=14, color=_TEXT, family="Inter, sans-serif"),
            x=0, xanchor="left", pad=dict(l=0, b=8),
        ),
        xaxis=dict(
            showgrid=True, gridcolor=_GRID, gridwidth=1,
            showline=True, linecolor=_GRID, linewidth=1,
            tickfont=dict(size=11, color=_TEXT_SEC),
            title=dict(text="Date", font=dict(color=_TEXT_SEC, size=11)),
            tickangle=-30,
        ),
        yaxis=dict(
            showgrid=True, gridcolor=_GRID, gridwidth=1,
            showline=True, linecolor=_GRID, linewidth=1,
            tickfont=dict(size=11, color=_TEXT_SEC),
            title=dict(
                text=unit if unit else "Value",
                font=dict(color=_TEXT_SEC, size=11),
            ),
            zeroline=False,
        ),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor="white",
            bordercolor=_GRID,
            font=dict(family="Inter, sans-serif", size=12, color=_TEXT),
        ),
        margin=dict(l=20, r=20, t=50, b=40),
        showlegend=False,
        height=340,
    )

    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

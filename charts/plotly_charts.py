"""Plotly 차트 빌더"""
from __future__ import annotations
import plotly.graph_objects as go
from simulator.constants import C


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    """'#rrggbb' → 'rgba(r,g,b,alpha)'"""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _dark_layout(**kwargs) -> dict:
    base = dict(
        paper_bgcolor=C["bg"],
        plot_bgcolor=C["panel"],
        font=dict(color=C["text"], size=10),
        margin=dict(l=40, r=20, t=30, b=30),
        legend=dict(bgcolor=C["panel"], bordercolor=C["border"], borderwidth=1, font_size=10),
    )
    base.update(kwargs)
    return base


def dps_line_chart(timeline1: list[dict], timeline2: list[dict]) -> go.Figure:
    """PVE DPS 진행 차트 (초 단위)."""
    fig = go.Figure()
    if timeline1:
        fig.add_trace(go.Scatter(
            x=[d["sec"] for d in timeline1],
            y=[d["dps"] for d in timeline1],
            name="P1 DPS", mode="lines",
            line=dict(color=C["p1"], width=2),
        ))
    if timeline2:
        fig.add_trace(go.Scatter(
            x=[d["sec"] for d in timeline2],
            y=[d["dps"] for d in timeline2],
            name="P2 DPS", mode="lines",
            line=dict(color=C["p2"], width=2),
        ))
    fig.update_layout(
        **_dark_layout(title="DPS 추이"),
        xaxis=dict(title="시간(초)", gridcolor=C["border"]),
        yaxis=dict(title="DPS", gridcolor=C["border"]),
    )
    return fig


def hp_timeline_chart(hp_timeline: list[dict]) -> go.Figure:
    """PVP HP 타임라인 차트."""
    fig = go.Figure()
    if hp_timeline:
        fig.add_trace(go.Scatter(
            x=[d["sec"] for d in hp_timeline],
            y=[d["P1 HP"] for d in hp_timeline],
            name="P1 HP", mode="lines",
            line=dict(color=C["p1"], width=2),
            fill="tozeroy", fillcolor=_hex_to_rgba(C["p1"], 0.1),
        ))
        fig.add_trace(go.Scatter(
            x=[d["sec"] for d in hp_timeline],
            y=[d["P2 HP"] for d in hp_timeline],
            name="P2 HP", mode="lines",
            line=dict(color=C["p2"], width=2),
            fill="tozeroy", fillcolor=_hex_to_rgba(C["p2"], 0.1),
        ))
    fig.update_layout(
        **_dark_layout(title="HP 타임라인"),
        xaxis=dict(title="시간(초)", gridcolor=C["border"]),
        yaxis=dict(title="HP", gridcolor=C["border"]),
    )
    return fig


def stats_bar_chart(
    labels: list[str],
    p1_vals: list[float],
    p2_vals: list[float],
) -> go.Figure:
    """스탯 비교 바 차트."""
    fig = go.Figure(data=[
        go.Bar(name="P1", x=labels, y=p1_vals,
               marker_color=C["p1"], opacity=0.85),
        go.Bar(name="P2", x=labels, y=p2_vals,
               marker_color=C["p2"], opacity=0.85),
    ])
    fig.update_layout(
        **_dark_layout(title="스탯 비교", barmode="group"),
        xaxis=dict(gridcolor=C["border"]),
        yaxis=dict(gridcolor=C["border"]),
    )
    return fig


def pie_chart(labels: list[str], values: list[float], title: str, color_scale: str = "Viridis") -> go.Figure:
    """확률 분포 원형 그래프."""
    fig = go.Figure(data=[go.Pie(
        labels=labels, 
        values=values, 
        hole=.3,
        textinfo='label+percent',
        marker=dict(line=dict(color=C["border"], width=1))
    )])
    fig.update_layout(
        **_dark_layout(title=title),
        showlegend=False
    )
    return fig


def radar_chart(
    categories: list[str],
    p1_vals: list[float],
    p2_vals: list[float],
) -> go.Figure:
    """정규화된 레이더 차트."""
    # 닫힌 다각형을 위해 첫 값을 마지막에 추가
    cats = categories + [categories[0]]
    v1 = p1_vals + [p1_vals[0]]
    v2 = p2_vals + [p2_vals[0]]

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=v1, theta=cats, name="P1",
        fill="toself", fillcolor=_hex_to_rgba(C["p1"], 0.13),
        line=dict(color=C["p1"], width=2),
    ))
    fig.add_trace(go.Scatterpolar(
        r=v2, theta=cats, name="P2",
        fill="toself", fillcolor=_hex_to_rgba(C["p2"], 0.13),
        line=dict(color=C["p2"], width=2),
    ))
    fig.update_layout(
        **_dark_layout(title="스탯 레이더"),
        polar=dict(
            bgcolor=C["panel"],
            radialaxis=dict(visible=True, range=[0, 100], gridcolor=C["border"]),
            angularaxis=dict(gridcolor=C["border"]),
        ),
    )
    return fig

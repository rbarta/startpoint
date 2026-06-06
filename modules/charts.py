import plotly.graph_objects as go

_BG = "#0E1117"
_BG2 = "#1E2130"
_TEXT = "#FAFAFA"
_GRID = "#2E3250"
_PRIMARY = "#00C49A"
_SECONDARY = "#4A9EFF"
_WARN = "#F4A261"
_DANGER = "#E63946"

PHASE_COLORS = {
    "Build": _PRIMARY,
    "Balance": _SECONDARY,
    "Ease": _WARN,
}


def dark_layout(title: str = "", x_title: str = "", y_title: str = "", **kwargs) -> go.Layout:
    return go.Layout(
        title=dict(text=title, font=dict(color=_TEXT, size=16)),
        paper_bgcolor=_BG,
        plot_bgcolor=_BG2,
        font=dict(color=_TEXT, family="sans-serif"),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor=_BG2,
            bordercolor=_GRID,
            font=dict(color=_TEXT, size=12),
            namelength=-1,          # never truncate trace names
        ),
        xaxis=dict(
            title=x_title,
            gridcolor=_GRID,
            zerolinecolor=_GRID,
            tickfont=dict(color=_TEXT),
        ),
        yaxis=dict(
            title=y_title,
            gridcolor=_GRID,
            zerolinecolor=_GRID,
            tickfont=dict(color=_TEXT),
        ),
        legend=dict(
            bgcolor=_BG2,
            bordercolor=_GRID,
            font=dict(color=_TEXT),
        ),
        margin=dict(l=60, r=20, t=50, b=50),
        **kwargs,
    )


def format_cad(value: float) -> str:
    if value >= 1_000_000:
        return f"${value/1_000_000:.2f}M"
    if value >= 1_000:
        return f"${value/1_000:.0f}K"
    return f"${value:.0f}"

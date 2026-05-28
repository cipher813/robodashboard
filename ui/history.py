"""Figure + summary builders for the portfolio snapshot history view."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


def nav_vs_spy_figure(history: pd.DataFrame, *, normalize: bool = True) -> go.Figure | None:
    """Line chart of real portfolio NAV vs SPY over the snapshot history.

    Args:
        history: DataFrame with ``date``, ``nav``, and optionally ``spy_close``.
        normalize: Index both series to 100 at the first snapshot for comparison.

    Returns:
        A Plotly Figure, or None if there are fewer than two snapshots.
    """
    if history is None or len(history) < 2:
        return None

    h = history.sort_values("date")
    fig = go.Figure()

    nav = h["nav"]
    nav_vals = (nav / nav.iloc[0]) * 100 if normalize else nav
    fig.add_trace(go.Scatter(
        x=h["date"], y=nav_vals, mode="lines", name="Portfolio",
        line=dict(color="#22c55e", width=3),
    ))

    if "spy_close" in h.columns:
        spy = h["spy_close"].dropna()
        if len(spy) >= 2:
            spy_aligned = h.loc[spy.index]
            spy_vals = (spy / spy.iloc[0]) * 100 if normalize else spy
            fig.add_trace(go.Scatter(
                x=spy_aligned["date"], y=spy_vals, mode="lines", name="SPY",
                line=dict(color="gray", width=2, dash="dash"),
            ))

    fig.update_layout(
        height=450,
        margin=dict(t=10, b=40, l=60, r=10),
        yaxis_title="Indexed (100 = first snapshot)" if normalize else "NAV ($)",
        xaxis_title="",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified",
    )
    return fig


def history_summary(history: pd.DataFrame) -> dict | None:
    """Compute since-first-snapshot return, SPY return, and alpha.

    Returns None if there are fewer than two snapshots.
    """
    if history is None or len(history) < 2:
        return None

    h = history.sort_values("date")
    nav_start, nav_end = h["nav"].iloc[0], h["nav"].iloc[-1]
    port_return = (nav_end / nav_start - 1) if nav_start > 0 else 0.0

    spy_return = None
    alpha = None
    if "spy_close" in h.columns:
        spy = h["spy_close"].dropna()
        if len(spy) >= 2 and spy.iloc[0] > 0:
            spy_return = spy.iloc[-1] / spy.iloc[0] - 1
            alpha = port_return - spy_return

    return {
        "start_date": h["date"].iloc[0],
        "end_date": h["date"].iloc[-1],
        "n_days": len(h),
        "nav_start": nav_start,
        "nav_end": nav_end,
        "port_return": port_return,
        "spy_return": spy_return,
        "alpha": alpha,
    }

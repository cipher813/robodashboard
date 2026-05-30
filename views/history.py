"""Portfolio History page — real NAV-vs-SPY time series from daily snapshots.

Unlike the Overview's performance chart (which applies *today's* share counts to
historical prices), this view plots the actual NAV recorded each day the
dashboard was run, so it reflects real holdings as they changed over time.

Registered via ``st.navigation`` from ``app.py`` (no ``st.set_page_config`` here).
"""

from __future__ import annotations

import streamlit as st

from bootstrap import get_clients
from data.snapshots import load_history
from ui import history as history_ui

st.title("Portfolio History")

config, _, _, _ = get_clients()
snapshots_dir = config.get("cache", {}).get("price_history_dir", "cache")
snapshots_dir = f"{snapshots_dir.rstrip('/')}/snapshots"

history = load_history(snapshots_dir)

if len(history) < 2:
    n = len(history)
    st.info(
        f"History builds as you use the dashboard. {n} day"
        f"{'' if n == 1 else 's'} recorded so far — come back tomorrow for a "
        "real NAV-vs-SPY chart. (One snapshot is written per day on the Overview page.)"
    )
    st.stop()

summary = history_ui.history_summary(history)
col1, col2, col3, col4 = st.columns(4)
col1.metric("Current NAV", f"${summary['nav_end']:,.0f}")
col2.metric("Return (since first snapshot)", f"{summary['port_return']:.1%}")
if summary["spy_return"] is not None:
    col3.metric("SPY (same window)", f"{summary['spy_return']:.1%}")
    col4.metric("Alpha vs SPY", f"{summary['alpha']:+.1%}")

st.caption(f"{summary['n_days']} daily snapshots · {summary['start_date'].date()} → {summary['end_date'].date()}")

normalize = st.checkbox("Normalize to 100", value=True, key="hist_normalize")
fig = history_ui.nav_vs_spy_figure(history, normalize=normalize)
if fig is not None:
    st.plotly_chart(fig, width="stretch")

with st.expander("Snapshot data"):
    st.dataframe(history.sort_values("date", ascending=False), width="stretch", hide_index=True)

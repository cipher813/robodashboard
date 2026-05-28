"""RoboDashboard — personal portfolio analytics.

Streamlit dashboard that connects to brokerage accounts via SnapTrade,
aggregates holdings, and displays institutional-grade metrics.

Usage:
    streamlit run app.py
"""

from __future__ import annotations

import logging

import streamlit as st

from bootstrap import (
    get_account_breakdown,
    get_account_options,
    get_clients,
    get_portfolio,
    render_client_messages,
)
from data.snapshots import write_snapshot
from ui import charts, columns, summary

logging.basicConfig(level=logging.INFO)

# ── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(page_title="RoboDashboard", page_icon=":chart_with_upwards_trend:", layout="wide")
st.title("RoboDashboard")

# ── Config + clients ─────────────────────────────────────────────────────────

config, cache, reader, messages = get_clients()
display_config = config.get("display", {})
render_client_messages(messages)

# ── Account selector (consolidated by default; filter to one/several) ─────────

account_options = get_account_options()  # [(number, label)]
selected_numbers = None
if len(account_options) > 1:
    label_to_num = {label: num for num, label in account_options}
    all_labels = [label for _, label in account_options]
    chosen = st.multiselect("Accounts", all_labels, default=all_labels, key="account_filter")
    # A strict subset filters; all (or none) selected = consolidated.
    if chosen and len(chosen) < len(all_labels):
        selected_numbers = tuple(label_to_num[label] for label in chosen)

# ── Load portfolio (for the current selection) ───────────────────────────────

with st.spinner("Loading portfolio data..."):
    df, source = get_portfolio(selected_numbers)

if df.empty:
    st.error("No portfolio data available. Link a brokerage account or check cached data.")
    st.stop()

if "cached" in source:
    st.warning(f"Showing cached data — {source}")

# ── Record daily snapshot — always all-accounts, independent of the view ──────

try:
    all_df, _ = get_portfolio(None)
    spy_hist = cache.get_spy_history()
    spy_close = float(spy_hist["Close"].iloc[-1]) if not spy_hist.empty else None
    write_snapshot(all_df, spy_close=spy_close, source=source)
except Exception as e:  # snapshotting is best-effort; never block the dashboard
    logging.getLogger(__name__).warning("Snapshot write failed: %s", e)

# ── Summary ──────────────────────────────────────────────────────────────────

summary.render_summary_cards(df)
summary.render_account_breakdown(get_account_breakdown())

# ── Holdings table ───────────────────────────────────────────────────────────

st.subheader("Holdings")

display_df = df.copy()

default_sort = display_config.get("default_sort", "market_value")
if default_sort in display_df.columns:
    ascending = display_config.get("default_sort_ascending", False)
    display_df.sort_values(default_sort, ascending=ascending, inplace=True)

if display_config.get("hide_zero_positions", True):
    display_df = display_df[display_df["shares"] > 0]

display_columns = columns.render_column_selector(display_df)
display_df, display_columns, columns_config = columns.apply_display_formatting(display_df, display_columns)

st.dataframe(
    display_df[display_columns],
    column_config=columns_config,
    width="stretch",
    hide_index=True,
    height=min(len(display_df) * 35 + 38, 800),
)

# ── Charts ───────────────────────────────────────────────────────────────────

chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    st.subheader("Sector Allocation")
    sector_fig = charts.sector_allocation_figure(df)
    if sector_fig is not None:
        st.plotly_chart(sector_fig, width="stretch")

with chart_col2:
    perf_window = st.selectbox(
        "Performers window",
        list(charts.PERFORMERS_COL_MAP.keys()),
        index=0,
        key="perf_window",
    )
    perf_fig = charts.performers_figure(df, charts.PERFORMERS_COL_MAP[perf_window])
    if perf_fig is not None:
        st.plotly_chart(perf_fig, width="stretch")

# ── Portfolio performance chart ─────────────────────────────────────────────

st.subheader("Portfolio Performance")

perf_col1, perf_col2 = st.columns([1, 3])

with perf_col1:
    period = st.selectbox("Time period", list(charts.PERIOD_MAP.keys()), index=0, key="chart_period")
    tickers = sorted(df["ticker"].tolist())
    selected_tickers = st.multiselect("Stocks", tickers, default=tickers, key="chart_tickers")
    normalize = st.checkbox("Normalize to 100", value=True, key="chart_normalize")
    show_spy = st.checkbox("Show SPY", value=True, key="chart_spy")
    show_portfolio = st.checkbox("Show Portfolio", value=True, key="chart_portfolio")

with perf_col2:
    perf_fig = charts.portfolio_performance_figure(
        df,
        cache,
        period,
        selected_tickers,
        normalize=normalize,
        show_spy=show_spy,
        show_portfolio=show_portfolio,
    )
    if perf_fig is not None:
        st.plotly_chart(perf_fig, width="stretch")
    else:
        st.info("Select at least one stock to display.")

# ── Footer ───────────────────────────────────────────────────────────────────

st.caption(f"Data source: {source} | Prices: yfinance (delayed)")

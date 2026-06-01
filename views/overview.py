"""Overview page — holdings table, allocation/geo charts, performance.

Registered via ``st.navigation`` from ``app.py``; the single
``st.set_page_config`` call lives in that router, not here.
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
from data.market_hours import is_extended_hours, market_session
from data.snapshots import write_snapshot
from ui import charts, columns, summary

st.title("RoboDashboard")

# ── Config + clients ─────────────────────────────────────────────────────────

config, cache, reader, messages = get_clients()
display_config = config.get("display", {})
lq_config = config.get("live_quotes", {})
render_client_messages(messages)

# ── Account selector (consolidated by default; filter to one/several) ─────────
# Outside the auto-refresh fragment: changing the selection reruns the page.

account_options = get_account_options()  # [(number, label)]
selected_numbers = None
if len(account_options) > 1:
    label_to_num = {label: num for num, label in account_options}
    all_labels = [label for _, label in account_options]
    chosen = st.multiselect("Accounts", all_labels, default=all_labels, key="account_filter")
    # A strict subset filters; all (or none) selected = consolidated.
    if chosen and len(chosen) < len(all_labels):
        selected_numbers = tuple(label_to_num[label] for label in chosen)


def _render_freshness_badge(source: str) -> None:
    """Honest data-freshness line: positions cadence vs live price cadence."""
    refresh_min = max(1, int(lq_config.get("refresh_seconds", 900)) // 60)
    if lq_config.get("enabled", True) and is_extended_hours():
        st.caption(
            f"🟢 Live prices — {market_session()} session · yfinance ~15-min delayed · "
            f"auto-refresh every {refresh_min} min · positions via SnapTrade daily sync"
        )
    else:
        st.caption("⚪ Market closed — showing last close · positions via SnapTrade daily sync")


# ── Live data view — re-pulls quotes every `refresh_seconds` while markets are
#    open (incl. pre/post). `run_every=None` off-hours means no polling. ───────

_auto = lq_config.get("enabled", True) and is_extended_hours()
_interval = int(lq_config.get("refresh_seconds", 900)) if _auto else None


@st.fragment(run_every=_interval)
def render_portfolio() -> None:
    with st.spinner("Loading portfolio data..."):
        df, source = get_portfolio(selected_numbers)

    if df.empty:
        st.error("No portfolio data available. Link a brokerage account or check cached data.")
        return

    if "cached" in source:
        st.warning(f"Showing cached data — {source}")
    _render_freshness_badge(source)

    # ── Record daily snapshot — always all-accounts, independent of the view ──
    try:
        all_df, _ = get_portfolio(None)
        spy_hist = cache.get_spy_history()
        spy_close = float(spy_hist["Close"].iloc[-1]) if not spy_hist.empty else None
        # Record true NAV (positions + cash) from IBKR's authoritative per-account
        # totals, so the History series reconciles to the breakdown. Falls back to
        # positions-only when no breakdown is available (offline/cached).
        breakdown = get_account_breakdown()
        nav_total = sum(r["total"] for r in breakdown) if breakdown else None
        write_snapshot(all_df, spy_close=spy_close, source=source, nav=nav_total)
    except Exception as e:  # snapshotting is best-effort; never block the dashboard
        logging.getLogger(__name__).warning("Snapshot write failed: %s", e)

    _render_portfolio_body(df, source)


def _render_portfolio_body(df, source) -> None:
    # ── Summary ──────────────────────────────────────────────────────────────
    summary.render_summary_cards(df)
    summary.render_account_breakdown(get_account_breakdown())

    # ── Holdings table ───────────────────────────────────────────────────────
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

    # ── Charts ───────────────────────────────────────────────────────────────
    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        st.subheader("Sector Allocation")
        sector_fig = charts.sector_allocation_figure(df)
        if sector_fig is not None:
            st.plotly_chart(sector_fig, width="stretch")

    with chart_col2:
        pw_col, unit_col, count_col = st.columns([2, 1, 1])
        with pw_col:
            perf_window = st.selectbox(
                "Performers window",
                list(charts.PERFORMERS_COL_MAP.keys()),
                index=0,
                key="perf_window",
            )
        with unit_col:
            perf_unit = st.radio("Show", ["%", "$"], horizontal=True, key="perf_unit")
        with count_col:
            # Count taken from EACH end (top N gainers + bottom N losers); "All"
            # shows every holding.
            perf_count_label = st.radio("Count", ["5", "10", "All"], horizontal=True, key="perf_count")
        perf_n = None if perf_count_label == "All" else int(perf_count_label)
        perf_fig = charts.performers_figure(
            df, charts.PERFORMERS_COL_MAP[perf_window], n=perf_n, dollars=(perf_unit == "$")
        )
        if perf_fig is not None:
            st.plotly_chart(perf_fig, width="stretch")

    # ── Geographic exposure (US vs International by domicile) ─────────────────
    st.subheader("Geographic Exposure")
    geo_col1, geo_col2 = st.columns([2, 1])
    with geo_col1:
        geo_fig = charts.geo_exposure_figure(df)
        if geo_fig is not None:
            st.plotly_chart(geo_fig, width="stretch")
        else:
            st.info("No domicile data available.")
    with geo_col2:
        if "domicile" in df.columns and df["market_value"].sum() > 0:
            by_geo = df.groupby("domicile")["market_value"].sum()
            total_mv = by_geo.sum()
            st.caption("US vs International — by company domicile (ADRs count as International).")
            for label in ("US", "International", "Unknown"):
                if label in by_geo.index:
                    st.metric(label, f"{by_geo[label] / total_mv * 100:.1f}%", f"${by_geo[label]:,.0f}")

    # ── Portfolio performance chart ──────────────────────────────────────────
    st.subheader("Portfolio Performance")

    perf_col1, perf_col2 = st.columns([1, 3])

    with perf_col1:
        period = st.selectbox("Time period", list(charts.PERIOD_MAP.keys()), index=0, key="chart_period")
        tickers = sorted(df["ticker"].tolist())
        selected_tickers = st.multiselect("Stocks", tickers, default=tickers, key="chart_tickers")
        normalize = st.checkbox("Normalize to 100", value=True, key="chart_normalize")
        show_spy = st.checkbox("Show SPY", value=True, key="chart_spy")
        show_portfolio = st.checkbox(
            "Aggregate as one line",
            value=True,
            key="chart_portfolio",
            help="On: a single market-value-weighted portfolio line. Off: each selected stock plotted individually.",
        )

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

    # ── Footer ───────────────────────────────────────────────────────────────
    st.caption(f"Data source: {source} | Prices: yfinance (delayed)")


render_portfolio()

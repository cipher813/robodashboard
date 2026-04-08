"""RoboDashboard — personal portfolio analytics.

Streamlit dashboard that connects to brokerage accounts via SnapTrade,
aggregates holdings, and displays institutional-grade metrics.

Usage:
    streamlit run app.py
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yaml
from dotenv import load_dotenv

from data.price_cache import PriceCache
from loaders.portfolio_loader import load_portfolio
from snaptrade_reader import SnapTradeReader

load_dotenv()
logging.basicConfig(level=logging.INFO)

# ── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(page_title="RoboDashboard", page_icon=":chart_with_upwards_trend:", layout="wide")
st.title("RoboDashboard")

# ── Load config ──────────────────────────────────────────────────────────────

CONFIG_PATH = Path("config.yaml")
if CONFIG_PATH.exists():
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f) or {}
else:
    config = {}

display_config = config.get("display", {})
cache_config = config.get("cache", {})

# ── Initialize clients ──────────────────────────────────────────────────────

cache = PriceCache(
    cache_dir=cache_config.get("price_history_dir", "cache"),
    max_age_hours=cache_config.get("max_age_hours", 24),
    info_max_age_hours=cache_config.get("info_max_age_hours", 168),
)

reader = None
if os.environ.get("SNAPTRADE_CLIENT_ID"):
    try:
        reader = SnapTradeReader.from_env()
    except Exception as e:
        st.warning(f"SnapTrade connection failed: {e}. Using cached data.")
else:
    st.info("No SnapTrade credentials found. Set SNAPTRADE_* env vars or use cached data.")

# ── Load portfolio ───────────────────────────────────────────────────────────


@st.cache_data(ttl=300)
def _load_portfolio():
    return load_portfolio(reader, cache)


with st.spinner("Loading portfolio data..."):
    df, source = _load_portfolio()

if df.empty:
    st.error("No portfolio data available. Link a brokerage account or check cached data.")
    st.stop()

if "cached" in source:
    st.warning(f"Showing cached data — {source}")

# ── Account summary cards ────────────────────────────────────────────────────

total_nav = df["market_value"].sum()
total_pnl = df["unrealized_pnl"].sum()
total_cost = (df["avg_cost"] * df["shares"]).sum()
total_return_pct = (total_nav / total_cost - 1) if total_cost > 0 else 0

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total NAV", f"${total_nav:,.0f}")
col2.metric("Unrealized P&L", f"${total_pnl:,.0f}", delta=f"{total_return_pct:.1%}")
col3.metric("Positions", len(df))
col4.metric("Sectors", df["sector"].nunique())

# ── Per-account breakdown ────────────────────────────────────────────────────

if reader:
    with st.expander("Account breakdown"):
        try:
            balances = reader.get_balances()
            accounts = reader.get_accounts()
            acct_data = []
            for acct in accounts:
                cash = balances.get(acct["name"], 0)
                acct_data.append({
                    "Account": acct["name"],
                    "Type": acct["type"],
                    "Institution": acct["institution"],
                    "Cash": cash,
                })
            if acct_data:
                st.dataframe(pd.DataFrame(acct_data), width="stretch", hide_index=True)
            cash_total = balances.get("total", 0)
            if cash_total > 0:
                st.metric("Total Cash", f"${cash_total:,.0f}")
        except Exception as e:
            st.warning(f"Could not load account details: {e}")

# ── Holdings table ───────────────────────────────────────────────────────────

st.subheader("Holdings")

# Format columns for display
display_df = df.copy()

# Sort
default_sort = display_config.get("default_sort", "market_value")
if default_sort in display_df.columns:
    ascending = display_config.get("default_sort_ascending", False)
    display_df.sort_values(default_sort, ascending=ascending, inplace=True)

# Hide zero positions
if display_config.get("hide_zero_positions", True):
    display_df = display_df[display_df["shares"] > 0]

# ── Column definitions (all available indicators) ───────────────────────────

ALL_COLUMNS = {
    # Core (ticker always shown, rest selectable but default on)
    "ticker": {"label": "Ticker", "config": st.column_config.TextColumn("Ticker", width="small"), "group": "core", "always": True},
    "name": {"label": "Name", "config": st.column_config.TextColumn("Name", width="medium"), "group": "core"},
    "shares": {"label": "Shares", "config": st.column_config.NumberColumn("Shares", format="%.0f"), "group": "core"},
    "current_price": {"label": "Price", "config": st.column_config.NumberColumn("Price", format="$%.2f"), "group": "core"},
    "market_value": {"label": "Mkt Value", "config": st.column_config.NumberColumn("Mkt Value", format="$%,.0f"), "group": "core"},
    # Position
    "sector": {"label": "Sector", "config": st.column_config.TextColumn("Sector", width="medium"), "group": "position"},
    "weight_pct": {"label": "Weight %", "config": st.column_config.NumberColumn("Weight %", format="%.1f%%", help="Position as % of total NAV"), "group": "position", "pct": True},
    "avg_cost": {"label": "Avg Cost", "config": st.column_config.NumberColumn("Avg Cost", format="$%.2f"), "group": "position"},
    "unrealized_pnl": {"label": "P&L", "config": st.column_config.NumberColumn("P&L", format="$%,.0f"), "group": "position"},
    "est_acq_date": {"label": "Est. Acquired", "config": st.column_config.TextColumn("Est. Acquired", help="Estimated acquisition date based on avg cost"), "group": "position"},
    # Performance
    "return_pct": {"label": "My Return", "config": st.column_config.NumberColumn("My Return", format="%.1f%%", help="Personal return vs cost basis"), "group": "performance", "pct": True},
    "vs_spy": {"label": "vs SPY", "config": st.column_config.NumberColumn("vs SPY", format="%+.1f%%", help="Outperformance vs SPY since est. acquisition"), "group": "performance", "pct": True},
    "1y_return": {"label": "1Y Return", "config": st.column_config.NumberColumn("1Y", format="%.1f%%", help="Stock 1-year return"), "group": "performance", "pct": True},
    "3y_return": {"label": "3Y Return", "config": st.column_config.NumberColumn("3Y", format="%.1f%%", help="Stock 3-year annualized return"), "group": "performance", "pct": True},
    "5y_return": {"label": "5Y Return", "config": st.column_config.NumberColumn("5Y", format="%.1f%%", help="Stock 5-year annualized return"), "group": "performance", "pct": True},
    "10y_return": {"label": "10Y Return", "config": st.column_config.NumberColumn("10Y", format="%.1f%%", help="Stock 10-year annualized return"), "group": "performance", "pct": True},
    # Valuation
    "pe_ratio": {"label": "P/E", "config": st.column_config.NumberColumn("P/E", format="%.1f", help="Trailing P/E ratio"), "group": "valuation"},
    "forward_pe": {"label": "Fwd P/E", "config": st.column_config.NumberColumn("Fwd P/E", format="%.1f", help="Forward P/E ratio"), "group": "valuation"},
    "peg_ratio": {"label": "PEG", "config": st.column_config.NumberColumn("PEG", format="%.2f", help="P/E to Growth ratio"), "group": "valuation"},
    "ev_to_ebitda": {"label": "EV/EBITDA", "config": st.column_config.NumberColumn("EV/EBITDA", format="%.1f", help="Enterprise value to EBITDA"), "group": "valuation"},
    "earnings_growth": {"label": "EPS Growth", "config": st.column_config.NumberColumn("EPS Growth", format="%.1f%%", help="Year-over-year earnings growth"), "group": "valuation", "pct_raw": True},
    "revenue_growth": {"label": "Rev Growth", "config": st.column_config.NumberColumn("Rev Growth", format="%.1f%%", help="Year-over-year revenue growth"), "group": "valuation", "pct_raw": True},
    # Fundamentals
    "debt_to_equity": {"label": "D/E", "config": st.column_config.NumberColumn("D/E", format="%.1f", help="Debt-to-equity ratio"), "group": "fundamentals"},
    # Technical
    "beta": {"label": "Beta", "config": st.column_config.NumberColumn("Beta", format="%.2f", help="1-year beta vs SPY"), "group": "technical"},
    "rsi": {"label": "RSI (14d)", "config": st.column_config.NumberColumn("RSI", format="%.0f", help="14-day RSI"), "group": "technical"},
    "pct_from_52w_high": {"label": "vs 52W High", "config": st.column_config.NumberColumn("vs 52W Hi", format="%.1f%%", help="% from 52-week high"), "group": "technical", "pct": True},
    # Income
    "dividend_yield": {"label": "Div Yield", "config": st.column_config.NumberColumn("Div Yield", format="%.2f%%", help="Forward dividend yield"), "group": "income"},
}

COLUMN_GROUPS = {
    "Core": [k for k, v in ALL_COLUMNS.items() if v["group"] == "core" and not v.get("always")],
    "Position": [k for k, v in ALL_COLUMNS.items() if v["group"] == "position"],
    "Performance": [k for k, v in ALL_COLUMNS.items() if v["group"] == "performance"],
    "Valuation": [k for k, v in ALL_COLUMNS.items() if v["group"] == "valuation"],
    "Fundamentals": [k for k, v in ALL_COLUMNS.items() if v["group"] == "fundamentals"],
    "Technical": [k for k, v in ALL_COLUMNS.items() if v["group"] == "technical"],
    "Income": [k for k, v in ALL_COLUMNS.items() if v["group"] == "income"],
}

DEFAULT_ON = {"name", "shares", "current_price", "market_value", "sector", "weight_pct",
              "unrealized_pnl", "return_pct", "vs_spy", "pe_ratio", "dividend_yield",
              "pct_from_52w_high"}

# ── Column selector ─────────────────────────────────────────────────────────

with st.expander("Customize columns"):
    selected_optional = []
    group_names = list(COLUMN_GROUPS.keys())
    cols = st.columns(len(group_names))
    for i, group_name in enumerate(group_names):
        with cols[i]:
            st.markdown(f"**{group_name}**")
            for col_key in COLUMN_GROUPS[group_name]:
                if col_key not in display_df.columns:
                    continue
                col_def = ALL_COLUMNS[col_key]
                checked = st.checkbox(col_def["label"], value=col_key in DEFAULT_ON, key=f"col_{col_key}")
                if checked:
                    selected_optional.append(col_key)

always_cols = [k for k, v in ALL_COLUMNS.items() if v.get("always")]
display_columns = always_cols + selected_optional

# ── Apply formatting ────────────────────────────────────────────────────────

for col_key in display_columns:
    col_def = ALL_COLUMNS.get(col_key, {})
    if col_def.get("pct") and col_key in display_df.columns:
        display_df[col_key] = display_df[col_key].apply(lambda x: x * 100 if pd.notna(x) else None)
    elif col_def.get("pct_raw") and col_key in display_df.columns:
        display_df[col_key] = display_df[col_key].apply(lambda x: x * 100 if pd.notna(x) else None)

columns_config = {k: ALL_COLUMNS[k]["config"] for k in display_columns if k in ALL_COLUMNS}
display_columns = [c for c in display_columns if c in display_df.columns]

st.dataframe(
    display_df[display_columns],
    column_config=columns_config,
    width="stretch",
    hide_index=True,
    height=min(len(display_df) * 35 + 38, 800),
)

# ── Charts ───────────────────────────────────────────────────────────────────

chart_col1, chart_col2 = st.columns(2)

# Sector allocation
with chart_col1:
    st.subheader("Sector Allocation")
    sector_df = df.groupby("sector")["market_value"].sum().reset_index()
    sector_df = sector_df[sector_df["sector"] != ""]
    sector_df["pct"] = sector_df["market_value"] / sector_df["market_value"].sum() * 100
    sector_df.sort_values("pct", ascending=False, inplace=True)
    if not sector_df.empty:
        fig = px.pie(sector_df, values="market_value", names="sector", hole=0.4)
        fig.update_traces(textposition="inside", textinfo="label+percent")
        fig.update_layout(showlegend=False, margin=dict(t=0, b=0, l=0, r=0), height=400)
        st.plotly_chart(fig, width="stretch")

# Top/bottom performers
with chart_col2:
    perf_window = st.selectbox("Performers window", ["My Return (since acquisition)", "LTM", "1Y", "3Y", "5Y", "10Y"], index=0, key="perf_window")
    perf_col_map = {
        "My Return (since acquisition)": "return_pct",
        "LTM": "1y_return",
        "1Y": "1y_return",
        "3Y": "3y_return",
        "5Y": "5y_return",
        "10Y": "10y_return",
    }
    perf_col = perf_col_map[perf_window]
    perf_df = df[df[perf_col].notna()].copy()
    perf_df["return_display"] = perf_df[perf_col] * 100
    perf_df.sort_values("return_display", inplace=True)
    n_show = min(5, len(perf_df))
    show_df = pd.concat([perf_df.head(n_show), perf_df.tail(n_show)]).drop_duplicates()
    show_df.sort_values("return_display", inplace=True)
    if not show_df.empty:
        fig = px.bar(show_df, x="return_display", y="ticker", orientation="h",
                     color="return_display", color_continuous_scale=["#ef4444", "#22c55e"],
                     labels={"return_display": "Return %", "ticker": ""})
        fig.update_layout(showlegend=False, coloraxis_showscale=False,
                          margin=dict(t=0, b=0, l=0, r=0), height=400)
        st.plotly_chart(fig, width="stretch")

# ── Portfolio performance chart ─────────────────────────────────────────────

st.subheader("Portfolio Performance")

PERIOD_MAP = {
    "LTM": 252,
    "YTD": None,  # special case
    "1Y": 252,
    "3Y": 756,
    "5Y": 1260,
    "10Y": 2520,
}

perf_col1, perf_col2 = st.columns([1, 3])

with perf_col1:
    period = st.selectbox("Time period", list(PERIOD_MAP.keys()), index=0, key="chart_period")
    tickers = sorted(df["ticker"].tolist())
    selected_tickers = st.multiselect("Stocks", tickers, default=tickers, key="chart_tickers")
    normalize = st.checkbox("Normalize to 100", value=True, key="chart_normalize")
    show_spy = st.checkbox("Show SPY", value=True, key="chart_spy")
    show_portfolio = st.checkbox("Show Portfolio", value=True, key="chart_portfolio")

with perf_col2:
    if selected_tickers:
        fig = go.Figure()

        # Determine date cutoff
        if period == "YTD":
            cutoff_date = pd.Timestamp(f"{datetime.now().year}-01-01")
        else:
            trading_days = PERIOD_MAP[period]
            cutoff_date = None  # will use trading day count

        def _trim_series(series):
            """Trim a price series to the selected period."""
            if cutoff_date is not None:
                if series.index.tz is not None:
                    ct = cutoff_date.tz_localize(series.index.tz)
                else:
                    ct = cutoff_date
                return series[series.index >= ct]
            return series.iloc[-trading_days:] if len(series) >= trading_days else series

        # Load price series for each ticker
        ticker_series = {}
        for ticker in selected_tickers:
            hist = cache.get_history(ticker)
            if hist.empty:
                continue
            close = _trim_series(hist["Close"])
            if close.empty:
                continue
            # Normalize to date-only index (drop tz) so cross-exchange dates align
            close = close.copy()
            close.index = close.index.tz_localize(None) if close.index.tz is not None else close.index
            close.index = close.index.normalize()
            close = close[~close.index.duplicated(keep="last")]
            ticker_series[ticker] = close

        # Plot individual tickers
        for ticker, close in ticker_series.items():
            if normalize:
                plot_vals = (close / close.iloc[0]) * 100
            else:
                plot_vals = close
            fig.add_trace(go.Scatter(
                x=plot_vals.index, y=plot_vals.values,
                mode="lines", name=ticker,
            ))

        # Portfolio aggregate (market-value-weighted)
        if show_portfolio and len(ticker_series) > 1:
            shares_map = dict(zip(df["ticker"], df["shares"]))
            portfolio_components = {}
            for ticker, close in ticker_series.items():
                shares = shares_map.get(ticker, 0)
                if shares > 0:
                    portfolio_components[ticker] = close * shares
            if portfolio_components:
                combined = pd.DataFrame(portfolio_components)
                combined = combined.ffill().dropna()
                portfolio_value = combined.sum(axis=1)
                if not portfolio_value.empty:
                    if normalize:
                        port_vals = (portfolio_value / portfolio_value.iloc[0]) * 100
                    else:
                        port_vals = portfolio_value
                    fig.add_trace(go.Scatter(
                        x=port_vals.index, y=port_vals.values,
                        mode="lines", name="Portfolio",
                        line=dict(color="white", width=3),
                    ))

        # Add SPY
        if show_spy:
            spy_hist = cache.get_spy_history()
            if not spy_hist.empty:
                spy_close = _trim_series(spy_hist["Close"])
                if not spy_close.empty:
                    spy_close = spy_close.copy()
                    spy_close.index = spy_close.index.tz_localize(None) if spy_close.index.tz is not None else spy_close.index
                    spy_close.index = spy_close.index.normalize()
                    spy_close = spy_close[~spy_close.index.duplicated(keep="last")]
                    if normalize:
                        spy_vals = (spy_close / spy_close.iloc[0]) * 100
                    else:
                        spy_vals = spy_close
                    fig.add_trace(go.Scatter(
                        x=spy_vals.index, y=spy_vals.values,
                        mode="lines", name="SPY",
                        line=dict(color="gray", width=2, dash="dash"),
                    ))

        y_label = "Indexed (100 = start)" if normalize else "Price ($)"
        fig.update_layout(
            height=500,
            margin=dict(t=10, b=40, l=60, r=10),
            yaxis_title=y_label,
            xaxis_title="",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            hovermode="x unified",
        )
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("Select at least one stock to display.")

# ── Footer ───────────────────────────────────────────────────────────────────

st.caption(f"Data source: {source} | Prices: yfinance (delayed)")

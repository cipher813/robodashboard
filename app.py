"""RoboDashboard — personal portfolio analytics.

Streamlit dashboard that connects to brokerage accounts via SnapTrade,
aggregates holdings, and displays institutional-grade metrics.

Usage:
    streamlit run app.py
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pandas as pd
import plotly.express as px
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
                st.dataframe(pd.DataFrame(acct_data), use_container_width=True, hide_index=True)
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

# Select and rename columns for display
columns_config = {
    "ticker": st.column_config.TextColumn("Ticker", width="small"),
    "name": st.column_config.TextColumn("Name", width="medium"),
    "sector": st.column_config.TextColumn("Sector", width="medium"),
    "shares": st.column_config.NumberColumn("Shares", format="%.0f"),
    "avg_cost": st.column_config.NumberColumn("Avg Cost", format="$%.2f"),
    "current_price": st.column_config.NumberColumn("Price", format="$%.2f"),
    "market_value": st.column_config.NumberColumn("Mkt Value", format="$%.0f"),
    "weight_pct": st.column_config.NumberColumn("Weight %", format="%.1f%%", help="Position as % of total NAV"),
    "unrealized_pnl": st.column_config.NumberColumn("P&L", format="$%.0f"),
    "return_pct": st.column_config.NumberColumn("Return", format="%.1f%%", help="Personal return vs cost basis"),
    "1y_return": st.column_config.NumberColumn("1Y", format="%.1f%%", help="Stock 1-year return"),
    "3y_return": st.column_config.NumberColumn("3Y", format="%.1f%%", help="Stock 3-year annualized return"),
    "5y_return": st.column_config.NumberColumn("5Y", format="%.1f%%", help="Stock 5-year annualized return"),
    "10y_return": st.column_config.NumberColumn("10Y", format="%.1f%%", help="Stock 10-year annualized return"),
    "beta": st.column_config.NumberColumn("Beta", format="%.2f", help="1-year beta vs SPY"),
    "rsi": st.column_config.NumberColumn("RSI", format="%.0f", help="14-day RSI"),
    "dividend_yield": st.column_config.NumberColumn("Div Yield", format="%.2f%%", help="Forward dividend yield"),
    "pct_from_52w_high": st.column_config.NumberColumn("vs 52W Hi", format="%.1f%%", help="% from 52-week high"),
}

# Convert percentage columns from decimal to display (multiply by 100)
pct_cols = ["weight_pct", "return_pct", "1y_return", "3y_return", "5y_return", "10y_return",
            "dividend_yield", "pct_from_52w_high"]
for col in pct_cols:
    if col in display_df.columns:
        display_df[col] = display_df[col].apply(lambda x: x * 100 if pd.notna(x) else None)

display_columns = [c for c in columns_config if c in display_df.columns]

st.dataframe(
    display_df[display_columns],
    column_config=columns_config,
    use_container_width=True,
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
        st.plotly_chart(fig, use_container_width=True)

# Top/bottom performers
with chart_col2:
    st.subheader("Top / Bottom Performers")
    perf_df = df[df["return_pct"].notna()].copy()
    perf_df["return_display"] = perf_df["return_pct"] * 100
    perf_df.sort_values("return_display", inplace=True)
    # Show bottom 5 + top 5
    n_show = min(5, len(perf_df))
    show_df = pd.concat([perf_df.head(n_show), perf_df.tail(n_show)]).drop_duplicates()
    show_df.sort_values("return_display", inplace=True)
    if not show_df.empty:
        colors = ["#ef4444" if x < 0 else "#22c55e" for x in show_df["return_display"]]
        fig = px.bar(show_df, x="return_display", y="ticker", orientation="h",
                     color="return_display", color_continuous_scale=["#ef4444", "#22c55e"],
                     labels={"return_display": "Return %", "ticker": ""})
        fig.update_layout(showlegend=False, coloraxis_showscale=False,
                          margin=dict(t=0, b=0, l=0, r=0), height=400)
        st.plotly_chart(fig, use_container_width=True)

# ── Footer ───────────────────────────────────────────────────────────────────

st.caption(f"Data source: {source} | Prices: yfinance (delayed)")

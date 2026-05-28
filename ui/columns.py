"""Holdings-table column registry, selector, and display formatting.

ALL_COLUMNS is the single source of truth for every available indicator: its
display label, Streamlit column_config, group, and formatting flags. The
selector and formatting helpers read from it.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

# Every available indicator. Flags:
#   always   — always shown, not user-selectable (ticker only)
#   pct      — value is a decimal ratio; multiply by 100 for a "%"-formatted column
#   pct_raw  — same as pct (kept distinct for provenance: already-percentage-ish source)
ALL_COLUMNS: dict[str, dict] = {
    # Core
    "ticker": {
        "label": "Ticker",
        "config": st.column_config.TextColumn("Ticker", width="small"),
        "group": "core",
        "always": True,
    },
    "name": {"label": "Name", "config": st.column_config.TextColumn("Name", width="medium"), "group": "core"},
    "shares": {"label": "Shares", "config": st.column_config.NumberColumn("Shares", format="%.0f"), "group": "core"},
    "current_price": {
        "label": "Price",
        "config": st.column_config.NumberColumn("Price", format="$%.2f"),
        "group": "core",
    },
    "market_value": {
        "label": "Mkt Value",
        "config": st.column_config.NumberColumn("Mkt Value", format="$%,.0f"),
        "group": "core",
    },
    # Position
    "sector": {"label": "Sector", "config": st.column_config.TextColumn("Sector", width="medium"), "group": "position"},
    "weight_pct": {
        "label": "Weight %",
        "config": st.column_config.NumberColumn("Weight %", format="%.1f%%", help="Position as % of total NAV"),
        "group": "position",
        "pct": True,
    },
    "avg_cost": {
        "label": "Avg Cost",
        "config": st.column_config.NumberColumn("Avg Cost", format="$%.2f"),
        "group": "position",
    },
    "unrealized_pnl": {
        "label": "P&L",
        "config": st.column_config.NumberColumn("P&L", format="$%,.0f"),
        "group": "position",
    },
    "est_acq_date": {
        "label": "Est. Acquired",
        "config": st.column_config.TextColumn("Est. Acquired", help="Estimated acquisition date based on avg cost"),
        "group": "position",
    },
    # Performance
    "return_pct": {
        "label": "My Return",
        "config": st.column_config.NumberColumn("My Return", format="%.1f%%", help="Personal return vs cost basis"),
        "group": "performance",
        "pct": True,
    },
    "vs_spy": {
        "label": "vs SPY",
        "config": st.column_config.NumberColumn(
            "vs SPY", format="%+.1f%%", help="Outperformance vs SPY since est. acquisition"
        ),
        "group": "performance",
        "pct": True,
    },
    "1y_return": {
        "label": "1Y Return",
        "config": st.column_config.NumberColumn("1Y", format="%.1f%%", help="Stock 1-year return"),
        "group": "performance",
        "pct": True,
    },
    "3y_return": {
        "label": "3Y Return",
        "config": st.column_config.NumberColumn("3Y", format="%.1f%%", help="Stock 3-year annualized return"),
        "group": "performance",
        "pct": True,
    },
    "5y_return": {
        "label": "5Y Return",
        "config": st.column_config.NumberColumn("5Y", format="%.1f%%", help="Stock 5-year annualized return"),
        "group": "performance",
        "pct": True,
    },
    "10y_return": {
        "label": "10Y Return",
        "config": st.column_config.NumberColumn("10Y", format="%.1f%%", help="Stock 10-year annualized return"),
        "group": "performance",
        "pct": True,
    },
    # Valuation
    "pe_ratio": {
        "label": "P/E",
        "config": st.column_config.NumberColumn("P/E", format="%.1f", help="Trailing P/E ratio"),
        "group": "valuation",
    },
    "forward_pe": {
        "label": "Fwd P/E",
        "config": st.column_config.NumberColumn("Fwd P/E", format="%.1f", help="Forward P/E ratio"),
        "group": "valuation",
    },
    "peg_ratio": {
        "label": "PEG",
        "config": st.column_config.NumberColumn("PEG", format="%.2f", help="P/E to Growth ratio"),
        "group": "valuation",
    },
    "ev_to_ebitda": {
        "label": "EV/EBITDA",
        "config": st.column_config.NumberColumn("EV/EBITDA", format="%.1f", help="Enterprise value to EBITDA"),
        "group": "valuation",
    },
    "earnings_growth": {
        "label": "EPS Growth",
        "config": st.column_config.NumberColumn("EPS Growth", format="%.1f%%", help="Year-over-year earnings growth"),
        "group": "valuation",
        "pct_raw": True,
    },
    "revenue_growth": {
        "label": "Rev Growth",
        "config": st.column_config.NumberColumn("Rev Growth", format="%.1f%%", help="Year-over-year revenue growth"),
        "group": "valuation",
        "pct_raw": True,
    },
    # Fundamentals
    "debt_to_equity": {
        "label": "D/E",
        "config": st.column_config.NumberColumn("D/E", format="%.1f", help="Debt-to-equity ratio"),
        "group": "fundamentals",
    },
    # Technical
    "beta": {
        "label": "Beta",
        "config": st.column_config.NumberColumn("Beta", format="%.2f", help="1-year beta vs SPY"),
        "group": "technical",
    },
    "rsi": {
        "label": "RSI (14d)",
        "config": st.column_config.NumberColumn("RSI", format="%.0f", help="14-day RSI"),
        "group": "technical",
    },
    "pct_from_52w_high": {
        "label": "vs 52W High",
        "config": st.column_config.NumberColumn("vs 52W Hi", format="%.1f%%", help="% from 52-week high"),
        "group": "technical",
        "pct": True,
    },
    # Income
    "dividend_yield": {
        "label": "Div Yield",
        "config": st.column_config.NumberColumn("Div Yield", format="%.2f%%", help="Forward dividend yield"),
        "group": "income",
    },
}

# Group label → ordered list of selectable column keys (excludes always-on).
COLUMN_GROUPS: dict[str, list[str]] = {
    "Core": [k for k, v in ALL_COLUMNS.items() if v["group"] == "core" and not v.get("always")],
    "Position": [k for k, v in ALL_COLUMNS.items() if v["group"] == "position"],
    "Performance": [k for k, v in ALL_COLUMNS.items() if v["group"] == "performance"],
    "Valuation": [k for k, v in ALL_COLUMNS.items() if v["group"] == "valuation"],
    "Fundamentals": [k for k, v in ALL_COLUMNS.items() if v["group"] == "fundamentals"],
    "Technical": [k for k, v in ALL_COLUMNS.items() if v["group"] == "technical"],
    "Income": [k for k, v in ALL_COLUMNS.items() if v["group"] == "income"],
}

# Columns checked on by default in the selector.
DEFAULT_ON: set[str] = {
    "name",
    "shares",
    "current_price",
    "market_value",
    "sector",
    "weight_pct",
    "unrealized_pnl",
    "return_pct",
    "vs_spy",
    "pe_ratio",
    "dividend_yield",
    "pct_from_52w_high",
}


def render_column_selector(display_df: pd.DataFrame) -> list[str]:  # pragma: no cover
    """Render the grouped checkbox selector and return chosen column keys.

    Always-on columns (ticker) are prepended to the returned list.
    """
    selected_optional: list[str] = []
    with st.expander("Customize columns"):
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
    return always_cols + selected_optional


def apply_display_formatting(
    display_df: pd.DataFrame, display_columns: list[str]
) -> tuple[pd.DataFrame, list[str], dict]:
    """Scale percentage columns to whole-number percent and build column_config.

    Returns:
        (formatted_df, present_columns, columns_config) where present_columns is
        display_columns filtered to those actually in the DataFrame.
    """
    for col_key in display_columns:
        col_def = ALL_COLUMNS.get(col_key, {})
        if (col_def.get("pct") or col_def.get("pct_raw")) and col_key in display_df.columns:
            display_df[col_key] = display_df[col_key].apply(lambda x: x * 100 if pd.notna(x) else None)

    present_columns = [c for c in display_columns if c in display_df.columns]
    columns_config = {k: ALL_COLUMNS[k]["config"] for k in present_columns if k in ALL_COLUMNS}
    return display_df, present_columns, columns_config

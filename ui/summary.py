"""Summary cards and per-account breakdown rendering."""

from __future__ import annotations

import pandas as pd
import streamlit as st


def portfolio_totals(df: pd.DataFrame) -> dict:
    """Compute headline portfolio totals from the enriched DataFrame."""
    total_nav = df["market_value"].sum()
    total_pnl = df["unrealized_pnl"].sum()
    total_cost = (df["avg_cost"] * df["shares"]).sum()
    total_return_pct = (total_nav / total_cost - 1) if total_cost > 0 else 0
    return {
        "nav": total_nav,
        "pnl": total_pnl,
        "cost": total_cost,
        "return_pct": total_return_pct,
        "n_positions": len(df),
        "n_sectors": df["sector"].nunique(),
    }


def render_summary_cards(df: pd.DataFrame) -> None:  # pragma: no cover
    """Render the four headline metric cards."""
    t = portfolio_totals(df)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total NAV", f"${t['nav']:,.0f}")
    col2.metric("Unrealized P&L", f"${t['pnl']:,.0f}", delta=f"{t['return_pct']:.1%}")
    col3.metric("Positions", t["n_positions"])
    col4.metric("Sectors", t["n_sectors"])


def render_account_breakdown(reader) -> None:  # pragma: no cover
    """Render the expandable per-account cash breakdown (requires a reader)."""
    if not reader:
        return
    with st.expander("Account breakdown"):
        try:
            balances = reader.get_balances()
            accounts = reader.get_accounts()
            acct_data = [
                {
                    "Account": acct["name"],
                    "Type": acct["type"],
                    "Institution": acct["institution"],
                    "Cash": balances.get(acct["name"], 0),
                }
                for acct in accounts
            ]
            if acct_data:
                st.dataframe(pd.DataFrame(acct_data), width="stretch", hide_index=True)
            cash_total = balances.get("total", 0)
            if cash_total > 0:
                st.metric("Total Cash", f"${cash_total:,.0f}")
        except Exception as e:
            st.warning(f"Could not load account details: {e}")

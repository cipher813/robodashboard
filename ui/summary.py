"""Summary cards and per-account breakdown rendering."""

from __future__ import annotations

import pandas as pd
import streamlit as st


def portfolio_totals(df: pd.DataFrame) -> dict:
    """Compute headline portfolio totals from the enriched DataFrame."""
    total_nav = df["market_value"].sum()
    total_pnl = df["unrealized_pnl"].sum()
    # Cost basis in USD. market_value and unrealized_pnl are both already
    # USD-converted, so cost = NAV − P&L. Do NOT sum avg_cost×shares — avg_cost
    # is in each holding's NATIVE currency, so summing across currencies (e.g.
    # adding an HKD cost as if USD) overstates cost and flips return % negative
    # on a real gain.
    total_cost = total_nav - total_pnl
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


def account_label(account: dict, labels: dict | None) -> str:
    """Friendly label for an account.

    Looks up the user-configured label by account number first, then by raw
    SnapTrade name; falls back to the SnapTrade name when unmapped.
    """
    labels = labels or {}
    number = str(account.get("number", ""))
    name = account.get("name", "")
    return labels.get(number) or labels.get(name) or name


def render_account_breakdown(reader, labels: dict | None = None) -> None:  # pragma: no cover
    """Render the expandable per-account cash breakdown (requires a reader).

    ``labels`` maps an account number (or raw name) to a friendly display
    label (from config ``accounts:``); unmapped accounts show their raw name.
    """
    if not reader:
        return
    with st.expander("Account breakdown"):
        try:
            balances = reader.get_balances()
            accounts = reader.get_accounts()
            acct_data = [
                {
                    "Account": account_label(acct, labels),
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

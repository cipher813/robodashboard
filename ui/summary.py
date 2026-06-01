"""Summary cards and per-account breakdown rendering."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import streamlit as st


def humanize_age(ts: str | datetime | None, now: datetime | None = None) -> str:
    """Format a sync timestamp as a short relative age, e.g. ``"8h ago"``.

    Accepts an ISO-8601 string (with ``Z`` or offset) or a datetime; returns
    ``"unknown"`` for None/unparseable input. Used to show how stale each
    account's SnapTrade-synced positions are.
    """
    if ts is None:
        return "unknown"
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return "unknown"
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    now = now or datetime.now(UTC)
    secs = (now - ts).total_seconds()
    if secs < 0:
        return "just now"
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{int(secs // 60)}m ago"
    if secs < 86400:
        return f"{int(secs // 3600)}h ago"
    return f"{int(secs // 86400)}d ago"


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


def render_account_breakdown(rows: list[dict] | None) -> None:  # pragma: no cover
    """Render the expandable per-account breakdown: positions + cash + total (USD).

    ``rows`` come from ``loaders.portfolio_loader.account_breakdown`` — each has
    label / positions / cash / total (all USD).
    """
    if not rows:
        return
    with st.expander("Account breakdown"):
        table = [
            {
                "Account": r["label"],
                "Positions": r["positions"],
                "Cash": r["cash"],
                "Total": r["total"],
                "Synced": humanize_age(r.get("last_sync")),
            }
            for r in rows
        ]
        st.dataframe(
            pd.DataFrame(table),
            width="stretch",
            hide_index=True,
            column_config={
                "Positions": st.column_config.NumberColumn("Positions", format="$%,.0f"),
                "Cash": st.column_config.NumberColumn("Cash", format="$%,.0f"),
                "Total": st.column_config.NumberColumn("Total", format="$%,.0f"),
                "Synced": st.column_config.TextColumn(
                    "Synced", help="When SnapTrade last refreshed this account's holdings from the broker."
                ),
            },
        )
        grand_total = sum(r["total"] for r in rows)
        st.metric("Total (positions + cash)", f"${grand_total:,.0f}")

"""Daily portfolio snapshot persistence.

The live dashboard reconstructs "portfolio performance" from current share
counts applied to historical prices — which silently assumes you always held
today's exact positions. To show *real* historical NAV (actual holdings as they
were each day), we persist a small daily summary row on every dashboard load.

Storage: a single append-style parquet (``cache/snapshots/history.parquet``)
with one row per calendar date. Writes are idempotent per day — re-running the
dashboard multiple times in a day overwrites that day's row rather than
duplicating it.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

HISTORY_FILENAME = "history.parquet"

# Columns persisted per daily snapshot row.
SNAPSHOT_COLUMNS = ["date", "nav", "cost", "pnl", "return_pct", "n_positions", "spy_close", "source"]


def _history_path(snapshots_dir: str | Path) -> Path:
    return Path(snapshots_dir) / HISTORY_FILENAME


def build_snapshot_row(
    df: pd.DataFrame,
    *,
    spy_close: float | None,
    source: str,
    nav: float | None = None,
    today: date | None = None,
) -> dict:
    """Build one daily snapshot row from the enriched portfolio DataFrame.

    Args:
        nav: IBKR's authoritative total account value (USD, positions + cash, at
            broker prices). When given, it's recorded as NAV — fixing both the
            missing-cash and the yfinance-price gap in one figure. When omitted
            (e.g. offline/cached mode with no balance data), NAV falls back to
            positions-only at yfinance prices.

    All money figures are USD. ``cost`` uses each holding's ``fx_to_usd`` so foreign
    cost basis isn't summed at face value, and ``return_pct`` is the unrealized
    return on positions (``pnl / cost``). ``cost``/``pnl`` are yfinance-derived
    analytics (secondary); ``nav`` is the authoritative broker total the History
    series plots — they come from different sources and aren't expected to tie
    exactly, so no derived cash plug is stored (it would just absorb that gap).
    """
    today = today or date.today()
    nav_total = float(nav) if nav is not None else float(df["market_value"].sum())
    fx = df["fx_to_usd"] if "fx_to_usd" in df.columns else 1.0
    cost = float((df["avg_cost"] * df["shares"] * fx).sum())
    pnl = float(df["unrealized_pnl"].sum())
    return {
        "date": pd.Timestamp(today).normalize(),
        "nav": nav_total,
        "cost": cost,
        "pnl": pnl,
        "return_pct": (pnl / cost) if cost > 0 else 0.0,
        "n_positions": int(len(df)),
        "spy_close": float(spy_close) if spy_close is not None else None,
        "source": source,
    }


def load_history(snapshots_dir: str | Path = "cache/snapshots") -> pd.DataFrame:
    """Load persisted snapshot history, sorted by date. Empty if none yet."""
    path = _history_path(snapshots_dir)
    if not path.exists():
        return pd.DataFrame(columns=SNAPSHOT_COLUMNS)
    df = pd.read_parquet(path)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
        df.sort_values("date", inplace=True)
        df.reset_index(drop=True, inplace=True)
    return df


def write_snapshot(
    df: pd.DataFrame,
    *,
    spy_close: float | None,
    source: str,
    nav: float | None = None,
    snapshots_dir: str | Path = "cache/snapshots",
    today: date | None = None,
) -> pd.DataFrame:
    """Persist today's snapshot row (idempotent per day) and return full history.

    ``nav`` is IBKR's authoritative total account value (positions + cash); when
    omitted, NAV falls back to positions-only. If a row for ``today`` already
    exists it is replaced — so repeated loads in a single day keep the latest
    figures without duplicating dates.
    """
    if df.empty:
        return load_history(snapshots_dir)

    row = build_snapshot_row(df, spy_close=spy_close, source=source, nav=nav, today=today)
    history = load_history(snapshots_dir)

    if not history.empty:
        history = history[history["date"] != row["date"]]
    history = pd.concat([history, pd.DataFrame([row])], ignore_index=True)
    history["date"] = pd.to_datetime(history["date"])
    history.sort_values("date", inplace=True)
    history.reset_index(drop=True, inplace=True)

    path = _history_path(snapshots_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    history.to_parquet(path, index=False)
    logger.info("Wrote snapshot for %s (nav=%.2f) — %d days of history", row["date"].date(), row["nav"], len(history))
    return history

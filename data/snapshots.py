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
    today: date | None = None,
) -> dict:
    """Build one daily snapshot row from the enriched portfolio DataFrame."""
    today = today or date.today()
    nav = float(df["market_value"].sum())
    cost = float((df["avg_cost"] * df["shares"]).sum())
    pnl = float(df["unrealized_pnl"].sum())
    return {
        "date": pd.Timestamp(today).normalize(),
        "nav": nav,
        "cost": cost,
        "pnl": pnl,
        "return_pct": (nav / cost - 1) if cost > 0 else 0.0,
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
    snapshots_dir: str | Path = "cache/snapshots",
    today: date | None = None,
) -> pd.DataFrame:
    """Persist today's snapshot row (idempotent per day) and return full history.

    If a row for ``today`` already exists it is replaced — so repeated loads in a
    single day keep the latest figures without duplicating dates.
    """
    if df.empty:
        return load_history(snapshots_dir)

    row = build_snapshot_row(df, spy_close=spy_close, source=source, today=today)
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

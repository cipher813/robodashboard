"""Headless daily portfolio snapshot.

Run by the robodashboard-snapshot.timer so the History page's real NAV-vs-SPY
series accrues every day regardless of whether anyone opens the dashboard.
Writes one idempotent row per day to cache/snapshots/history.parquet.

Usage:
    python scripts/daily_snapshot.py
"""

from __future__ import annotations

import logging
import os
import sys

# Allow `python scripts/daily_snapshot.py` from the repo root by putting the
# repo root (this file's parent's parent) on the path before app imports.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

from app_config import init_clients, load_config
from data.snapshots import write_snapshot
from loaders.portfolio_loader import load_portfolio

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("daily_snapshot")


def main() -> int:
    load_dotenv()
    config = load_config()
    cache, reader, _ = init_clients(config)

    df, source = load_portfolio(reader, cache)
    if df.empty:
        logger.error("No portfolio data (source=%s) — nothing to snapshot", source)
        return 1

    spy_hist = cache.get_spy_history()
    spy_close = float(spy_hist["Close"].iloc[-1]) if not spy_hist.empty else None

    history = write_snapshot(df, spy_close=spy_close, source=source)
    logger.info("Snapshot written (source=%s) — %d days of history", source, len(history))
    return 0


if __name__ == "__main__":
    sys.exit(main())

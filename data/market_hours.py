"""US market-session gating for live-quote fetches.

Pure and dependency-free (stdlib ``zoneinfo``). Used to decide whether to spend
a yfinance intraday pull: we only fetch live quotes during extended trading
hours (pre-market through post-market) and fall back to the daily close
otherwise — so nothing polls Yahoo overnight or on weekends, when the latest
meaningful price is just the prior close.

No holiday calendar is modeled: a market holiday simply yields a wasted fetch
that returns the prior close (harmless, and rare). Foreign exchanges are not
modeled either — the US extended window is the gate; foreign positions still
get whatever latest intraday bar yfinance has during the window, and fall back
to the daily close when none is available.

Extended-hours boundaries (America/New_York):
    pre-market     04:00 – 09:30
    regular        09:30 – 16:00
    post-market    16:00 – 20:00
    closed         otherwise (incl. all of Sat/Sun)
"""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

PRE_OPEN = time(4, 0)
REGULAR_OPEN = time(9, 30)
REGULAR_CLOSE = time(16, 0)
POST_CLOSE = time(20, 0)


def _to_et(now: datetime | None) -> datetime:
    """Coerce ``now`` to an America/New_York datetime (naive → assumed ET)."""
    if now is None:
        return datetime.now(ET)
    if now.tzinfo is None:
        return now.replace(tzinfo=ET)
    return now.astimezone(ET)


def market_session(now: datetime | None = None) -> str:
    """Return ``'pre' | 'regular' | 'post' | 'closed'`` for US extended hours."""
    dt = _to_et(now)
    if dt.weekday() >= 5:  # Saturday/Sunday
        return "closed"
    t = dt.time()
    if PRE_OPEN <= t < REGULAR_OPEN:
        return "pre"
    if REGULAR_OPEN <= t < REGULAR_CLOSE:
        return "regular"
    if REGULAR_CLOSE <= t < POST_CLOSE:
        return "post"
    return "closed"


def is_extended_hours(now: datetime | None = None) -> bool:
    """True during pre-market, regular, or post-market hours on a weekday."""
    return market_session(now) != "closed"

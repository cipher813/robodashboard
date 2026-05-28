"""Glue layer: SnapTrade positions + price cache + metrics → enriched DataFrame.

Loads positions from SnapTrade (or cache fallback), enriches with yfinance
price data and computed metrics, returns a single DataFrame ready for display.
"""

from __future__ import annotations

import logging

import pandas as pd

from data.metrics import (
    compute_beta,
    compute_personal_return,
    compute_returns,
    compute_rsi,
    compute_vs_spy,
    estimate_acquisition_date,
    pct_from_52w_high,
)
from data.price_cache import PriceCache
from snaptrade_reader import SnapTradeReader

logger = logging.getLogger(__name__)

# SnapTrade → yfinance ticker normalization
# SnapTrade uses exchange-specific suffixes that differ from yfinance conventions
TICKER_MAP = {
    ".SP": ".SI",  # Singapore Exchange: SnapTrade uses .SP, yfinance uses .SI
    ".TO": ".TO",  # Toronto (same)
    ".L": ".L",  # London (same)
}


def _normalize_ticker(ticker: str) -> str:
    """Convert SnapTrade ticker format to yfinance format."""
    for snap_suffix, yf_suffix in TICKER_MAP.items():
        if ticker.endswith(snap_suffix):
            return ticker[: -len(snap_suffix)] + yf_suffix
    return ticker


def load_portfolio(reader: SnapTradeReader | None, cache: PriceCache) -> tuple[pd.DataFrame, str]:
    """Load and enrich portfolio data.

    Args:
        reader: SnapTradeReader instance, or None for offline mode.
        cache: PriceCache for historical prices and fundamentals.

    Returns:
        (enriched_df, source) where source is "live" or "cached ({timestamp})".
    """
    # Get positions
    if reader:
        try:
            holdings = reader.get_aggregated_holdings()
            source = "live"
        except Exception as e:
            logger.warning("SnapTrade fetch failed: %s — falling back to cache", e)
            holdings, ts = SnapTradeReader.load_cached_holdings()
            source = f"cached ({ts})" if ts else "cached"
    else:
        holdings, ts = SnapTradeReader.load_cached_holdings()
        source = f"cached ({ts})" if ts else "no data"

    if holdings.empty:
        return holdings, source

    # Get SPY history for beta computation
    spy_hist = cache.get_spy_history()
    spy_close = spy_hist["Close"] if not spy_hist.empty else pd.Series(dtype=float)

    # Enrich each ticker
    enriched_rows = []
    for _, row in holdings.iterrows():
        ticker = _normalize_ticker(row["ticker"])
        shares = row["shares"]
        avg_cost = row.get("avg_cost", 0)

        # Price history + info
        hist = cache.get_history(ticker)
        info = cache.get_info(ticker)
        close = hist["Close"] if not hist.empty else pd.Series(dtype=float)
        current_price = float(close.iloc[-1]) if not close.empty else 0

        # Compute metrics
        returns = compute_returns(close) if not close.empty else {}
        beta = compute_beta(close, spy_close) if not close.empty and not spy_close.empty else None
        rsi = compute_rsi(close) if not close.empty else None
        personal_ret = compute_personal_return(current_price, avg_cost)
        market_value = shares * current_price
        unrealized_pnl = market_value - (shares * avg_cost) if avg_cost else 0
        pct_52w = pct_from_52w_high(current_price, info.get("fifty_two_week_high"))
        acq_date = estimate_acquisition_date(close, avg_cost)
        vs_spy = compute_vs_spy(close, spy_close, acq_date)

        enriched_rows.append(
            {
                "ticker": ticker,
                "name": info.get("name", ticker),
                "sector": info.get("sector", ""),
                "shares": shares,
                "avg_cost": avg_cost,
                "current_price": current_price,
                "market_value": market_value,
                "unrealized_pnl": unrealized_pnl,
                "return_pct": personal_ret,
                "vs_spy": vs_spy,
                "est_acq_date": acq_date,
                "1y_return": returns.get(1),
                "3y_return": returns.get(3),
                "5y_return": returns.get(5),
                "10y_return": returns.get(10),
                "beta": beta,
                "rsi": rsi,
                "dividend_yield": info.get("dividend_yield"),
                "52w_high": info.get("fifty_two_week_high"),
                "52w_low": info.get("fifty_two_week_low"),
                "pct_from_52w_high": pct_52w,
                "pe_ratio": info.get("pe_ratio"),
                "forward_pe": info.get("forward_pe"),
                "peg_ratio": info.get("peg_ratio"),
                "ev_to_ebitda": info.get("ev_to_ebitda"),
                "earnings_growth": info.get("earnings_growth"),
                "revenue_growth": info.get("revenue_growth"),
                "debt_to_equity": info.get("debt_to_equity"),
                "n_accounts": row.get("n_accounts", 1),
            }
        )

    df = pd.DataFrame(enriched_rows)

    # Compute weight %
    total_value = df["market_value"].sum()
    df["weight_pct"] = df["market_value"] / total_value if total_value > 0 else 0

    return df, source

"""Historical price data fetching and caching via yfinance.

Caches 10-year daily OHLCV history as parquet files. On subsequent loads,
only fetches the delta since last cache date. Fundamentals (sector, name,
dividend yield, etc.) are cached separately with weekly invalidation.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path("cache")
PRICE_HISTORY_PERIOD = "10y"
INFO_CACHE_MAX_AGE_HOURS = 168  # 1 week


class PriceCache:
    """Fetch and cache historical prices from yfinance."""

    def __init__(
        self, cache_dir: str = "cache", max_age_hours: int = 24, info_max_age_hours: int = INFO_CACHE_MAX_AGE_HOURS
    ):
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._prices_dir = self._cache_dir / "prices"
        self._prices_dir.mkdir(exist_ok=True)
        self._info_dir = self._cache_dir / "info"
        self._info_dir.mkdir(exist_ok=True)
        self._max_age_hours = max_age_hours
        self._info_max_age_hours = info_max_age_hours

    def get_history(self, ticker: str, period: str = PRICE_HISTORY_PERIOD) -> pd.DataFrame:
        """Return daily OHLCV DataFrame, fetching + caching as needed."""
        cache_path = self._prices_dir / f"{ticker}.parquet"

        if cache_path.exists():
            cached = pd.read_parquet(cache_path)
            cache_age = time.time() - cache_path.stat().st_mtime
            if cache_age < self._max_age_hours * 3600 and not cached.empty:
                return cached
            # Fetch delta only
            last_date = cached.index.max()
            start = (last_date + timedelta(days=1)).strftime("%Y-%m-%d")
            try:
                delta = yf.Ticker(ticker).history(start=start)
                if not delta.empty:
                    combined = pd.concat([cached, delta])
                    combined = combined[~combined.index.duplicated(keep="last")]
                    combined.sort_index(inplace=True)
                    combined.to_parquet(cache_path)
                    return combined
                else:
                    # Touch file to update mtime (no new data but cache is fresh)
                    cache_path.touch()
                    return cached
            except Exception as e:
                logger.warning("Failed to fetch delta for %s: %s — using cache", ticker, e)
                return cached

        # Full fetch
        try:
            hist = yf.Ticker(ticker).history(period=period)
            if not hist.empty:
                hist.to_parquet(cache_path)
            return hist
        except Exception as e:
            logger.warning("Failed to fetch history for %s: %s", ticker, e)
            return pd.DataFrame()

    def get_info(self, ticker: str) -> dict:
        """Get company info (name, sector, dividend yield, 52w high/low, beta).

        Cached with weekly invalidation.
        """
        cache_path = self._info_dir / f"{ticker}.json"

        if cache_path.exists():
            cache_age = time.time() - cache_path.stat().st_mtime
            if cache_age < self._info_max_age_hours * 3600:
                return json.loads(cache_path.read_text())

        try:
            info = yf.Ticker(ticker).info or {}
            result = {
                "name": info.get("shortName") or info.get("longName", ticker),
                "sector": info.get("sector", ""),
                "industry": info.get("industry", ""),
                "dividend_yield": info.get("dividendYield"),
                "forward_dividend": info.get("dividendRate"),
                "beta": info.get("beta"),
                "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
                "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
                "market_cap": info.get("marketCap"),
                "pe_ratio": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "peg_ratio": info.get("trailingPegRatio") or info.get("pegRatio"),
                "ev_to_ebitda": info.get("enterpriseToEbitda"),
                "earnings_growth": info.get("earningsGrowth"),
                "revenue_growth": info.get("revenueGrowth"),
                "debt_to_equity": info.get("debtToEquity"),
                "fetched_at": datetime.now().isoformat(),
            }
            cache_path.write_text(json.dumps(result, indent=2))
            return result
        except Exception as e:
            logger.warning("Failed to fetch info for %s: %s", ticker, e)
            # Return cached if available, even if stale
            if cache_path.exists():
                return json.loads(cache_path.read_text())
            return {
                "name": ticker,
                "sector": "",
                "dividend_yield": None,
                "beta": None,
                "fifty_two_week_high": None,
                "fifty_two_week_low": None,
            }

    def refresh_all(self, tickers: list[str]) -> None:
        """Batch refresh price history and info for all tickers."""
        logger.info("Refreshing price data for %d tickers", len(tickers))
        for ticker in tickers:
            self.get_history(ticker)
            self.get_info(ticker)

    def get_spy_history(self) -> pd.DataFrame:
        """Get SPY history (used for beta computation)."""
        return self.get_history("SPY")

    def get_fx_rate(self, currency: str) -> float:
        """Return the conversion rate from ``currency`` to USD (USD per 1 unit).

        USD → 1.0. Other currencies use yfinance's ``{CCY}USD=X`` pair (e.g.
        ``SGDUSD=X`` ≈ 0.74 USD per SGD), reusing the cached history fetch.
        Returns 1.0 if the rate can't be determined (fail-soft so the dashboard
        still renders; the local amount is always shown alongside).
        """
        if not currency or currency.upper() == "USD":
            return 1.0
        pair = f"{currency.upper()}USD=X"
        hist = self.get_history(pair)
        if hist.empty or "Close" not in hist or hist["Close"].dropna().empty:
            logger.warning("No FX rate for %s (%s) — falling back to 1.0", currency, pair)
            return 1.0
        return float(hist["Close"].dropna().iloc[-1])

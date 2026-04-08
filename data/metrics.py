"""Per-stock and portfolio metric computation.

All metrics are computed from cached price history (pandas DataFrames).
No API calls are made in this module.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_returns(prices: pd.Series, years: list[int] | None = None) -> dict[int, float | None]:
    """Compute annualized returns over multiple periods.

    Args:
        prices: Daily close prices (DatetimeIndex).
        years: Periods to compute (default: [1, 3, 5, 10]).

    Returns:
        {1: 0.15, 3: 0.12, ...} — annualized returns, None if insufficient data.
    """
    if years is None:
        years = [1, 3, 5, 10]

    results = {}
    for y in years:
        trading_days = y * 252
        if len(prices) < trading_days * 0.95:  # Allow 5% tolerance for holidays/gaps
            results[y] = None
            continue
        idx = min(trading_days, len(prices) - 1)
        start_price = prices.iloc[-idx]
        end_price = prices.iloc[-1]
        if start_price <= 0:
            results[y] = None
            continue
        total_return = end_price / start_price - 1
        results[y] = (1 + total_return) ** (1 / y) - 1
    return results


def compute_beta(stock_prices: pd.Series, spy_prices: pd.Series, window: int = 252) -> float | None:
    """Compute beta vs SPY using trailing daily returns.

    Args:
        stock_prices: Daily close prices for the stock.
        spy_prices: Daily close prices for SPY.
        window: Number of trading days to use (default: 252 = 1 year).

    Returns:
        Beta value, or None if insufficient data.
    """
    if len(stock_prices) < window or len(spy_prices) < window:
        return None

    stock_ret = stock_prices.iloc[-window:].pct_change().dropna()
    spy_ret = spy_prices.iloc[-window:].pct_change().dropna()

    # Align on common dates
    common = stock_ret.index.intersection(spy_ret.index)
    if len(common) < 30:
        return None

    stock_ret = stock_ret.loc[common]
    spy_ret = spy_ret.loc[common]

    cov_matrix = np.cov(stock_ret, spy_ret)
    if cov_matrix[1, 1] == 0:
        return None
    return round(float(cov_matrix[0, 1] / cov_matrix[1, 1]), 3)


def compute_rsi(prices: pd.Series, period: int = 14) -> float | None:
    """Compute current RSI (Relative Strength Index).

    Args:
        prices: Daily close prices.
        period: RSI lookback period (default: 14).

    Returns:
        RSI value (0-100), or None if insufficient data.
    """
    if len(prices) < period + 1:
        return None

    delta = prices.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()

    last_gain = gain.iloc[-1]
    last_loss = loss.iloc[-1]

    if last_loss == 0:
        return 100.0
    rs = last_gain / last_loss
    return round(100 - (100 / (1 + rs)), 1)


def pct_from_52w_high(current_price: float, high_52w: float | None) -> float | None:
    """Compute percentage below 52-week high.

    Returns:
        Negative percentage (e.g., -0.15 means 15% below high), or None.
    """
    if not high_52w or high_52w <= 0 or not current_price:
        return None
    return round((current_price / high_52w) - 1, 4)


def compute_personal_return(current_price: float, avg_cost: float) -> float | None:
    """Compute personal return based on cost basis.

    Returns:
        Return as decimal (e.g., 0.25 = 25%), or None if no cost basis.
    """
    if not avg_cost or avg_cost <= 0:
        return None
    return round((current_price / avg_cost) - 1, 4)


def estimate_acquisition_date(prices: pd.Series, avg_cost: float) -> str | None:
    """Estimate acquisition date by finding the date closest to avg_cost.

    Searches backward from recent prices to find the last date where
    the closing price crossed the avg_cost level.

    Returns:
        ISO date string, or None if cannot determine.
    """
    if prices.empty or not avg_cost or avg_cost <= 0:
        return None
    diffs = (prices - avg_cost).abs()
    best_idx = diffs.idxmin()
    if best_idx is not None:
        return best_idx.strftime("%Y-%m-%d")
    return None


def compute_vs_spy(stock_prices: pd.Series, spy_prices: pd.Series, acq_date: str | None) -> float | None:
    """Compute stock return vs SPY return since acquisition date.

    Returns:
        Excess return as decimal (e.g., 0.05 = 5% outperformance), or None.
    """
    if not acq_date or stock_prices.empty or spy_prices.empty:
        return None
    try:
        start = pd.Timestamp(acq_date)
        # Match timezone if index is tz-aware
        if stock_prices.index.tz is not None:
            start = start.tz_localize(stock_prices.index.tz)
        stock_after = stock_prices[stock_prices.index >= start]

        start_spy = pd.Timestamp(acq_date)
        if spy_prices.index.tz is not None:
            start_spy = start_spy.tz_localize(spy_prices.index.tz)
        spy_after = spy_prices[spy_prices.index >= start_spy]

        if stock_after.empty or spy_after.empty:
            return None
        stock_ret = float(stock_after.iloc[-1] / stock_after.iloc[0] - 1)
        spy_ret = float(spy_after.iloc[-1] / spy_after.iloc[0] - 1)
        return round(stock_ret - spy_ret, 4)
    except Exception:
        return None

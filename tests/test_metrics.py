"""Tests for data/metrics.py — return, beta, RSI computation."""

import numpy as np
import pandas as pd

from data.metrics import (
    compute_beta,
    compute_personal_return,
    compute_returns,
    compute_rsi,
    pct_from_52w_high,
)


def _make_prices(start: float, end: float, n: int) -> pd.Series:
    """Generate a linearly spaced price series with DatetimeIndex."""
    dates = pd.date_range(end="2026-04-07", periods=n, freq="B")
    return pd.Series(np.linspace(start, end, n), index=dates)


class TestComputeReturns:
    def test_positive_return(self):
        prices = _make_prices(100, 115, 252)  # 15% over 1 year
        result = compute_returns(prices, [1])
        assert result[1] is not None
        assert abs(result[1] - 0.15) < 0.01

    def test_negative_return(self):
        prices = _make_prices(100, 85, 252)
        result = compute_returns(prices, [1])
        assert result[1] is not None
        assert result[1] < 0

    def test_insufficient_data(self):
        prices = _make_prices(100, 110, 50)
        result = compute_returns(prices, [1])
        assert result[1] is None

    def test_multi_year(self):
        prices = _make_prices(100, 200, 252 * 3)
        result = compute_returns(prices, [1, 3])
        assert result[1] is not None
        assert result[3] is not None
        # 3-year annualized should be less than total return
        assert result[3] < (200 / 100 - 1)

    def test_default_years(self):
        prices = _make_prices(100, 150, 252 * 10)
        result = compute_returns(prices)
        assert set(result.keys()) == {1, 3, 5, 10}


class TestComputeBeta:
    def test_correlated_stock(self):
        np.random.seed(42)
        spy_returns = np.random.randn(300) * 0.01
        spy = pd.Series(100 * np.cumprod(1 + spy_returns), index=pd.date_range(end="2026-04-07", periods=300, freq="B"))
        # Stock moves 1.5x the market
        stock_returns = spy_returns * 1.5
        stock = pd.Series(100 * np.cumprod(1 + stock_returns), index=spy.index)
        beta = compute_beta(stock, spy)
        assert beta is not None
        assert abs(beta - 1.5) < 0.15

    def test_spy_vs_spy(self):
        spy = _make_prices(100, 115, 300)
        beta = compute_beta(spy, spy)
        assert beta is not None
        assert abs(beta - 1.0) < 0.01

    def test_insufficient_data(self):
        spy = _make_prices(100, 110, 20)
        stock = _make_prices(100, 112, 20)
        beta = compute_beta(stock, spy)
        assert beta is None


class TestComputeRSI:
    def test_all_gains(self):
        prices = _make_prices(100, 200, 30)  # monotonically increasing
        rsi = compute_rsi(prices)
        assert rsi is not None
        assert rsi > 90  # should be near 100

    def test_all_losses(self):
        prices = _make_prices(200, 100, 30)  # monotonically decreasing
        rsi = compute_rsi(prices)
        assert rsi is not None
        assert rsi < 10  # should be near 0

    def test_insufficient_data(self):
        prices = _make_prices(100, 110, 5)
        rsi = compute_rsi(prices)
        assert rsi is None

    def test_range(self):
        np.random.seed(42)
        prices = pd.Series(
            100 + np.random.randn(100).cumsum(), index=pd.date_range(end="2026-04-07", periods=100, freq="B")
        )
        rsi = compute_rsi(prices)
        assert rsi is not None
        assert 0 <= rsi <= 100


class TestPctFrom52wHigh:
    def test_at_high(self):
        result = pct_from_52w_high(150, 150)
        assert result == 0.0

    def test_below_high(self):
        result = pct_from_52w_high(135, 150)
        assert result is not None
        assert abs(result - (-0.10)) < 0.001

    def test_none_high(self):
        assert pct_from_52w_high(100, None) is None

    def test_zero_high(self):
        assert pct_from_52w_high(100, 0) is None


class TestPersonalReturn:
    def test_gain(self):
        result = compute_personal_return(120, 100)
        assert result == 0.2

    def test_loss(self):
        result = compute_personal_return(80, 100)
        assert result == -0.2

    def test_no_cost(self):
        assert compute_personal_return(100, 0) is None
        assert compute_personal_return(100, None) is None

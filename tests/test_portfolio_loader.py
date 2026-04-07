"""Tests for loaders/portfolio_loader.py — aggregation and enrichment."""

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from loaders.portfolio_loader import load_portfolio


def _mock_cache():
    """Create a mock PriceCache that returns synthetic data."""
    cache = MagicMock()
    dates = pd.date_range(end="2026-04-07", periods=300, freq="B")
    spy_prices = pd.Series(np.linspace(400, 500, 300), index=dates)
    stock_prices = pd.Series(np.linspace(100, 130, 300), index=dates)

    cache.get_spy_history.return_value = pd.DataFrame({"Close": spy_prices})
    cache.get_history.return_value = pd.DataFrame({"Close": stock_prices})
    cache.get_info.return_value = {
        "name": "Test Corp",
        "sector": "Technology",
        "dividend_yield": 0.015,
        "beta": 1.1,
        "fifty_two_week_high": 135,
        "fifty_two_week_low": 90,
        "pe_ratio": 25,
    }
    return cache


def _mock_reader(holdings_df: pd.DataFrame):
    """Create a mock SnapTradeReader."""
    reader = MagicMock()
    reader.get_aggregated_holdings.return_value = holdings_df
    return reader


class TestLoadPortfolio:
    def test_basic_enrichment(self):
        holdings = pd.DataFrame([
            {"ticker": "AAPL", "shares": 100, "avg_cost": 110, "market_value": 13000, "n_accounts": 2},
        ])
        reader = _mock_reader(holdings)
        cache = _mock_cache()

        df, source = load_portfolio(reader, cache)

        assert source == "live"
        assert len(df) == 1
        assert df.iloc[0]["ticker"] == "AAPL"
        assert df.iloc[0]["name"] == "Test Corp"
        assert df.iloc[0]["sector"] == "Technology"
        assert df.iloc[0]["shares"] == 100
        assert df.iloc[0]["current_price"] > 0
        assert df.iloc[0]["beta"] is not None
        assert df.iloc[0]["rsi"] is not None
        assert "weight_pct" in df.columns

    def test_weight_sums_to_one(self):
        holdings = pd.DataFrame([
            {"ticker": "AAPL", "shares": 100, "avg_cost": 110, "market_value": 13000, "n_accounts": 1},
            {"ticker": "MSFT", "shares": 50, "avg_cost": 300, "market_value": 17500, "n_accounts": 1},
        ])
        reader = _mock_reader(holdings)
        cache = _mock_cache()

        df, _ = load_portfolio(reader, cache)

        assert len(df) == 2
        assert abs(df["weight_pct"].sum() - 1.0) < 0.001

    def test_offline_fallback(self):
        cache = _mock_cache()

        with patch("loaders.portfolio_loader.SnapTradeReader") as mock_cls:
            mock_cls.load_cached_holdings.return_value = (pd.DataFrame(), "")
            df, source = load_portfolio(None, cache)

        assert df.empty
        assert "no data" in source

    def test_snaptrade_error_falls_back(self):
        reader = MagicMock()
        reader.get_aggregated_holdings.side_effect = ConnectionError("API down")
        cache = _mock_cache()

        with patch("loaders.portfolio_loader.SnapTradeReader") as mock_cls:
            cached_df = pd.DataFrame([
                {"ticker": "AAPL", "shares": 100, "avg_cost": 110, "market_value": 13000, "n_accounts": 1},
            ])
            mock_cls.load_cached_holdings.return_value = (cached_df, "2026-04-06T12:00:00")
            df, source = load_portfolio(reader, cache)

        assert "cached" in source
        assert len(df) == 1

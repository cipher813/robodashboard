"""Tests for loaders/portfolio_loader.py — aggregation and enrichment."""

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from loaders.portfolio_loader import account_breakdown, load_portfolio


def _mock_cache():
    """Create a mock PriceCache that returns synthetic data."""
    cache = MagicMock()
    dates = pd.date_range(end="2026-04-07", periods=300, freq="B")
    spy_prices = pd.Series(np.linspace(400, 500, 300), index=dates)
    stock_prices = pd.Series(np.linspace(100, 130, 300), index=dates)

    cache.get_spy_history.return_value = pd.DataFrame({"Close": spy_prices})
    cache.get_history.return_value = pd.DataFrame({"Close": stock_prices})
    cache.get_fx_rate.return_value = 1.0
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
        holdings = pd.DataFrame(
            [
                {"ticker": "AAPL", "shares": 100, "avg_cost": 110, "market_value": 13000, "n_accounts": 2},
            ]
        )
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
        holdings = pd.DataFrame(
            [
                {"ticker": "AAPL", "shares": 100, "avg_cost": 110, "market_value": 13000, "n_accounts": 1},
                {"ticker": "MSFT", "shares": 50, "avg_cost": 300, "market_value": 17500, "n_accounts": 1},
            ]
        )
        reader = _mock_reader(holdings)
        cache = _mock_cache()

        df, _ = load_portfolio(reader, cache)

        assert len(df) == 2
        assert abs(df["weight_pct"].sum() - 1.0) < 0.001

    def test_non_usd_holding_converts_to_usd(self):
        # current_price comes from the mock cache (last close = 130).
        holdings = pd.DataFrame(
            [
                {
                    "ticker": "D05.SI",
                    "currency": "SGD",
                    "shares": 10,
                    "avg_cost": 60,
                    "market_value": 600,
                    "n_accounts": 1,
                },
            ]
        )
        reader = _mock_reader(holdings)
        cache = _mock_cache()
        cache.get_fx_rate.side_effect = lambda c: {"USD": 1.0, "SGD": 0.75}.get(c, 1.0)

        df, _ = load_portfolio(reader, cache)
        row = df.iloc[0]
        assert row["currency"] == "SGD"
        # local value = shares * native price; USD = local * fx
        assert row["market_value_local"] == row["shares"] * row["current_price"]
        assert abs(row["market_value"] - row["market_value_local"] * 0.75) < 1e-6
        assert row["market_value"] < row["market_value_local"]  # SGD worth less than USD

    def test_defaults_to_usd_when_currency_absent(self):
        holdings = pd.DataFrame(
            [{"ticker": "AAPL", "shares": 10, "avg_cost": 110, "market_value": 1300, "n_accounts": 1}],
        )
        df, _ = load_portfolio(_mock_reader(holdings), _mock_cache())
        assert df.iloc[0]["currency"] == "USD"
        assert df.iloc[0]["market_value"] == df.iloc[0]["market_value_local"]  # fx 1.0

    def test_load_portfolio_passes_account_filter(self):
        holdings = pd.DataFrame(
            [
                {
                    "ticker": "AAPL",
                    "currency": "USD",
                    "shares": 10,
                    "avg_cost": 100,
                    "market_value": 1000,
                    "n_accounts": 1,
                }
            ]
        )
        reader = _mock_reader(holdings)
        df, source = load_portfolio(reader, _mock_cache(), ["U1"])
        reader.get_aggregated_holdings.assert_called_once_with(["U1"])
        assert source == "live"
        assert len(df) == 1

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
            cached_df = pd.DataFrame(
                [
                    {"ticker": "AAPL", "shares": 100, "avg_cost": 110, "market_value": 13000, "n_accounts": 1},
                ]
            )
            mock_cls.load_cached_holdings.return_value = (cached_df, "2026-04-06T12:00:00")
            df, source = load_portfolio(reader, cache)

        assert "cached" in source
        assert len(df) == 1


def test_account_breakdown_cash_positions_total():
    reader = MagicMock()
    reader.get_all_holdings.return_value = pd.DataFrame(
        [
            {
                "account_id": "a1",
                "account_number": "U1",
                "ticker": "AAPL",
                "currency": "USD",
                "shares": 10,
                "avg_cost": 100,
                "market_value": 1000,
            },
            {
                "account_id": "a2",
                "account_number": "U2",
                "ticker": "MSFT",
                "currency": "USD",
                "shares": 5,
                "avg_cost": 300,
                "market_value": 1500,
            },
        ]
    )
    reader.get_balances.return_value = {"IRA": 500.0, "Roth": 0.0, "total": 500.0}
    reader.get_accounts.return_value = [
        {"number": "U1", "name": "IRA", "type": "", "institution": ""},
        {"number": "U2", "name": "Roth", "type": "", "institution": ""},
    ]
    rows = account_breakdown(reader, _mock_cache(), {"U1": "Trad IRA"})
    by = {r["number"]: r for r in rows}
    assert by["U1"]["label"] == "Trad IRA"  # labeled by number
    assert by["U2"]["label"] == "Roth"  # raw-name fallback
    assert by["U1"]["cash"] == 500.0
    # positions = shares * current_price (mock last close 130) * fx 1.0
    assert by["U1"]["positions"] == 10 * 130.0
    assert by["U1"]["total"] == 10 * 130.0 + 500.0


def test_account_breakdown_no_reader():
    assert account_breakdown(None, _mock_cache()) == []

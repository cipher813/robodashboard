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

    def test_live_quote_overrides_daily_close(self):
        # Daily close from the mock cache is 130; a live quote of 200 should win
        # and flow into market_value / unrealized_pnl.
        holdings = pd.DataFrame(
            [{"ticker": "AAPL", "shares": 10, "avg_cost": 110, "market_value": 1300, "n_accounts": 1}]
        )
        df, _ = load_portfolio(
            _mock_reader(holdings),
            _mock_cache(),
            quotes_fn=lambda symbols: {"AAPL": 200.0},
        )
        row = df.iloc[0]
        assert row["current_price"] == 200.0
        assert row["market_value"] == 10 * 200.0  # fx 1.0
        assert row["unrealized_pnl"] == 10 * (200.0 - 110)

    def test_live_quote_symbols_include_fx_pairs(self):
        # The quotes_fn must be asked for the FX pair of any non-USD currency.
        holdings = pd.DataFrame(
            [
                {
                    "ticker": "AAPL",
                    "currency": "USD",
                    "shares": 10,
                    "avg_cost": 100,
                    "market_value": 1000,
                    "n_accounts": 1,
                },
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
        seen = {}

        def spy(symbols):
            seen["symbols"] = symbols
            return {}

        load_portfolio(_mock_reader(holdings), _mock_cache(), quotes_fn=spy)
        assert "AAPL" in seen["symbols"]
        assert "D05.SI" in seen["symbols"]
        assert "SGDUSD=X" in seen["symbols"]

    def test_live_fx_rate_overrides_cached(self):
        # A live FX quote (SGDUSD=X) overrides the cache's daily rate (0.75 → 0.80).
        holdings = pd.DataFrame(
            [
                {
                    "ticker": "D05.SI",
                    "currency": "SGD",
                    "shares": 10,
                    "avg_cost": 60,
                    "market_value": 600,
                    "n_accounts": 1,
                }
            ]
        )
        cache = _mock_cache()
        cache.get_fx_rate.side_effect = lambda c: {"USD": 1.0, "SGD": 0.75}.get(c, 1.0)
        df, _ = load_portfolio(
            _mock_reader(holdings),
            cache,
            quotes_fn=lambda symbols: {"SGDUSD=X": 0.80},
        )
        row = df.iloc[0]
        assert row["fx_to_usd"] == 0.80
        assert abs(row["market_value"] - row["market_value_local"] * 0.80) < 1e-6

    def test_quotes_fn_failure_falls_back_to_close(self):
        # If quotes_fn raises, the daily close (130) is used — never crash.
        holdings = pd.DataFrame(
            [{"ticker": "AAPL", "shares": 10, "avg_cost": 110, "market_value": 1300, "n_accounts": 1}]
        )

        def boom(symbols):
            raise RuntimeError("yfinance down")

        df, _ = load_portfolio(_mock_reader(holdings), _mock_cache(), quotes_fn=boom)
        assert df.iloc[0]["current_price"] == 130  # mock daily close, unchanged

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
    # IBKR's authoritative per-account total (positions + cash, IBKR FX).
    reader.get_accounts.return_value = [
        {"number": "U1", "name": "IRA", "type": "", "institution": "", "balance_total": 1500.0},
        {"number": "U2", "name": "Roth", "type": "", "institution": "", "balance_total": 1500.0},
    ]
    rows = account_breakdown(reader, _mock_cache(), {"U1": "Trad IRA"})
    by = {r["number"]: r for r in rows}
    assert by["U1"]["label"] == "Trad IRA"  # labeled by number
    assert by["U2"]["label"] == "Roth"  # raw-name fallback
    # positions = broker market_value (1000) * fx 1.0; total is authoritative;
    # cash is derived as total - positions.
    assert by["U1"]["positions"] == 1000.0
    assert by["U1"]["total"] == 1500.0
    assert by["U1"]["cash"] == 500.0
    # U2: market_value 1500 → positions 1500, cash plug 0.
    assert by["U2"]["positions"] == 1500.0
    assert by["U2"]["cash"] == 0.0


def test_account_breakdown_multi_currency_cash_is_fx_aware():
    """Regression: foreign-currency cash must NOT be summed at face value.

    Mirrors the Roth IRA bug — an account holding a foreign-currency position
    plus mixed-currency cash. Cash is derived from IBKR's authoritative total
    minus FX-converted positions, never HKD + SGD + USD added as dollars.
    """
    reader = MagicMock()
    # One HKD position worth 100,000 HKD locally.
    reader.get_all_holdings.return_value = pd.DataFrame(
        [
            {
                "account_id": "a1",
                "account_number": "U1",
                "ticker": "1299.HK",
                "currency": "HKD",
                "shares": 1000,
                "avg_cost": 90,
                "current_price": 100,
                "market_value": 100_000,  # 1000 * 100, native HKD
            }
        ]
    )
    reader.get_accounts.return_value = [
        {"number": "U1", "name": "Roth", "type": "", "institution": "", "balance_total": 13_000.0},
    ]
    cache = MagicMock()
    cache.get_fx_rate.return_value = 0.128  # HKD → USD

    rows = account_breakdown(reader, cache, None)
    r = rows[0]
    # positions = 100,000 HKD * 0.128 = $12,800 (FX-converted, not face value)
    assert abs(r["positions"] - 12_800.0) < 1e-6
    # cash = authoritative total 13,000 - 12,800 = $200 (a plausible USD plug),
    # NOT the face-value sum of foreign cash buckets.
    assert abs(r["cash"] - 200.0) < 1e-6
    assert abs(r["total"] - 13_000.0) < 1e-6


def test_account_breakdown_carries_last_sync():
    """The per-account holdings sync timestamp flows through to the breakdown row."""
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
            }
        ]
    )
    reader.get_accounts.return_value = [
        {
            "number": "U1",
            "name": "IRA",
            "type": "",
            "institution": "",
            "balance_total": 1500.0,
            "last_holdings_sync": "2026-06-01T10:00:00+00:00",
        }
    ]
    rows = account_breakdown(reader, _mock_cache(), None)
    assert rows[0]["last_sync"] == "2026-06-01T10:00:00+00:00"


def test_account_breakdown_no_reader():
    assert account_breakdown(None, _mock_cache()) == []

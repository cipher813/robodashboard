"""Tests for FX handling in PriceCache.get_fx_rate."""

from unittest.mock import MagicMock

import pandas as pd

from data.price_cache import PriceCache


def test_usd_is_identity(tmp_path):
    cache = PriceCache(cache_dir=str(tmp_path))
    assert cache.get_fx_rate("USD") == 1.0
    assert cache.get_fx_rate("usd") == 1.0
    assert cache.get_fx_rate("") == 1.0


def test_non_usd_uses_pair_close(tmp_path, monkeypatch):
    cache = PriceCache(cache_dir=str(tmp_path))
    captured = {}

    def fake_history(pair, *a, **k):
        captured["pair"] = pair
        return pd.DataFrame({"Close": [0.70, 0.74]})

    monkeypatch.setattr(cache, "get_history", fake_history)
    rate = cache.get_fx_rate("SGD")
    assert captured["pair"] == "SGDUSD=X"
    assert rate == 0.74


def test_falls_back_to_one_when_no_data(tmp_path, monkeypatch):
    cache = PriceCache(cache_dir=str(tmp_path))
    monkeypatch.setattr(cache, "get_history", lambda *a, **k: pd.DataFrame())
    assert cache.get_fx_rate("HKD") == 1.0


def test_aggregate_holdings_filters_by_account():
    from snaptrade_reader import aggregate_holdings

    raw = pd.DataFrame(
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
                "ticker": "AAPL",
                "currency": "USD",
                "shares": 5,
                "avg_cost": 110,
                "market_value": 550,
            },
            {
                "account_id": "a2",
                "account_number": "U2",
                "ticker": "MSFT",
                "currency": "USD",
                "shares": 2,
                "avg_cost": 300,
                "market_value": 600,
            },
        ]
    )
    only_u1 = aggregate_holdings(raw, ["U1"]).set_index("ticker")
    assert set(only_u1.index) == {"AAPL"}
    assert only_u1.loc["AAPL", "shares"] == 10

    both = aggregate_holdings(raw, ["U1", "U2"]).set_index("ticker")
    assert both.loc["AAPL", "shares"] == 15  # summed across accounts
    assert set(both.index) == {"AAPL", "MSFT"}

    assert len(aggregate_holdings(raw, None)) == 2  # all accounts


def test_aggregated_holdings_carry_currency():
    """SnapTradeReader aggregation preserves per-ticker currency."""
    from snaptrade_reader import SnapTradeReader

    reader = SnapTradeReader.__new__(SnapTradeReader)  # skip __init__/network
    raw = pd.DataFrame(
        [
            {
                "account_id": "a1",
                "ticker": "D05.SP",
                "currency": "SGD",
                "shares": 10,
                "avg_cost": 60,
                "market_value": 600,
            },
            {
                "account_id": "a2",
                "ticker": "D05.SP",
                "currency": "SGD",
                "shares": 5,
                "avg_cost": 62,
                "market_value": 310,
            },
            {
                "account_id": "a1",
                "ticker": "AAPL",
                "currency": "USD",
                "shares": 2,
                "avg_cost": 100,
                "market_value": 200,
            },
        ]
    )
    reader.get_all_holdings = MagicMock(return_value=raw)
    agg = reader.get_aggregated_holdings()
    by_ticker = agg.set_index("ticker")
    assert by_ticker.loc["D05.SP", "currency"] == "SGD"
    assert by_ticker.loc["D05.SP", "shares"] == 15
    assert by_ticker.loc["AAPL", "currency"] == "USD"

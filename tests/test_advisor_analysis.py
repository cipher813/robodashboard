"""Tests for advisor/analysis.py — deterministic gap analysis."""

from __future__ import annotations

import pandas as pd

from advisor.analysis import analyze, coarse_signature
from advisor.profile import InvestorProfile


def _df():
    # NAV = 10,000. US 70% / Intl 30%. AAPL 40% (concentration breach at 10%).
    return pd.DataFrame(
        {
            "ticker": ["AAPL", "MSFT", "ASML", "TSM"],
            "market_value": [4000.0, 3000.0, 2000.0, 1000.0],
            "domicile": ["US", "US", "International", "International"],
            "sector": ["Technology", "Technology", "Technology", "Technology"],
            "weight_pct": [0.40, 0.30, 0.20, 0.10],
            "dividend_yield": [0.5, 0.8, 0.0, 2.0],  # percent numbers
        }
    )


def _profile():
    return InvestorProfile(
        target_allocation={"us_equity": 0.60, "international": 0.15},  # → 80/20 within equity
        overweight_sectors=["Technology"],
        avoid_sectors=["Energy"],
        income_target=500.0,
        max_single_position=0.10,
    )


def test_geo_gap_vs_normalized_equity_target():
    a = analyze(_df(), _profile())
    assert round(a.geo.us_pct, 0) == 70
    assert round(a.geo.intl_pct, 0) == 30
    assert round(a.geo.us_target_pct, 0) == 80
    # 70% actual − 80% target = −10pp (under target on US).
    assert round(a.geo.us_gap_pp, 0) == -10
    assert round(a.geo.intl_gap_pp, 0) == 10


def test_geo_gap_none_targets_without_profile():
    a = analyze(_df(), None)
    assert a.geo.us_target_pct is None
    assert a.geo.us_gap_pp is None


def test_concentration_flags_positions_over_limit():
    a = analyze(_df(), _profile())
    tickers = [c.ticker for c in a.concentration]
    # AAPL 40% and MSFT 30% exceed the 10% cap; ASML 20% too; TSM exactly 10% does not.
    assert "AAPL" in tickers and "TSM" not in tickers
    assert a.concentration[0].ticker == "AAPL"  # sorted desc
    assert a.concentration[0].limit_pct == 10.0


def test_sector_flags_overweight_and_avoid():
    df = _df()
    df.loc[df["ticker"] == "TSM", "sector"] = "Energy"
    a = analyze(df, _profile())
    by_sector = {s.sector: s.flag for s in a.sectors}
    assert by_sector["Technology"] == "overweight_pref"
    assert by_sector["Energy"] == "avoid_violation"


def test_income_uses_percent_dividend_yield():
    a = analyze(_df(), _profile())
    # income = 0.5%*4000 + 0.8%*3000 + 0 + 2.0%*1000 = 20 + 24 + 0 + 20 = 64
    assert round(a.income.annual_income, 1) == 64.0
    assert round(a.income.portfolio_yield_pct, 3) == 0.64
    assert round(a.income.income_gap, 0) == 436  # 500 target − 64


def test_to_dict_is_json_serializable():
    import json

    a = analyze(_df(), _profile())
    json.dumps(a.to_dict())  # must not raise


def test_coarse_signature_stable_under_trivial_price_drift():
    df = _df()
    base = coarse_signature(analyze(df, _profile()), "claude-sonnet-4-6", "educational")
    # Nudge every position by a few dollars (sub-$10k NAV bucket, sub-1pp weight).
    drift = df.copy()
    drift["market_value"] = drift["market_value"] + [3.0, -2.0, 1.0, -1.0]
    after = coarse_signature(analyze(drift, _profile()), "claude-sonnet-4-6", "educational")
    assert base == after  # trivial drift must NOT trigger a new LLM call


def test_coarse_signature_changes_on_material_shift_and_knobs():
    df = _df()
    base = coarse_signature(analyze(df, _profile()), "claude-sonnet-4-6", "educational")
    # Material reallocation: swap 1500 of US (MSFT) into intl (ASML) → geo pct moves >1pp.
    moved = df.copy()
    moved.loc[moved["ticker"] == "MSFT", "market_value"] = 1500.0
    moved.loc[moved["ticker"] == "ASML", "market_value"] = 3500.0
    assert coarse_signature(analyze(moved, _profile()), "claude-sonnet-4-6", "educational") != base
    # Posture/model are part of the key too.
    assert coarse_signature(analyze(df, _profile()), "claude-sonnet-4-6", "candid") != base

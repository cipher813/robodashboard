"""Tests for ui/summary.py totals."""

import pandas as pd

from ui import summary


def test_portfolio_totals():
    df = pd.DataFrame({
        "market_value": [2000.0, 1500.0],
        "unrealized_pnl": [500.0, -100.0],
        "avg_cost": [100.0, 200.0],
        "shares": [15, 8],
        "sector": ["Technology", "Energy"],
    })
    t = summary.portfolio_totals(df)
    assert t["nav"] == 3500.0
    assert t["pnl"] == 400.0
    assert t["cost"] == 100.0 * 15 + 200.0 * 8
    assert t["n_positions"] == 2
    assert t["n_sectors"] == 2


def test_portfolio_totals_zero_cost_safe():
    df = pd.DataFrame({
        "market_value": [100.0],
        "unrealized_pnl": [0.0],
        "avg_cost": [0.0],
        "shares": [1],
        "sector": ["Technology"],
    })
    t = summary.portfolio_totals(df)
    assert t["return_pct"] == 0

"""Tests for ui/summary.py totals."""

import pandas as pd

from ui import summary


def test_portfolio_totals():
    df = pd.DataFrame(
        {
            "market_value": [2000.0, 1500.0],
            "unrealized_pnl": [500.0, -100.0],
            "avg_cost": [100.0, 200.0],
            "shares": [15, 8],
            "sector": ["Technology", "Energy"],
        }
    )
    t = summary.portfolio_totals(df)
    assert t["nav"] == 3500.0
    assert t["pnl"] == 400.0
    assert t["cost"] == 100.0 * 15 + 200.0 * 8
    assert t["n_positions"] == 2
    assert t["n_sectors"] == 2


def test_account_label_by_number():
    acct = {"number": "U12345678", "name": "Interactive Brokers (Long Name)"}
    labels = {"U12345678": "Roth IRA"}
    assert summary.account_label(acct, labels) == "Roth IRA"


def test_account_label_by_name_fallback():
    acct = {"number": "U999", "name": "Interactive Brokers (X)"}
    labels = {"Interactive Brokers (X)": "Taxable"}
    assert summary.account_label(acct, labels) == "Taxable"


def test_account_label_falls_back_to_raw_name():
    acct = {"number": "U000", "name": "Interactive Brokers (Y)"}
    assert summary.account_label(acct, {}) == "Interactive Brokers (Y)"
    assert summary.account_label(acct, None) == "Interactive Brokers (Y)"


def test_portfolio_totals_zero_cost_safe():
    df = pd.DataFrame(
        {
            "market_value": [100.0],
            "unrealized_pnl": [0.0],
            "avg_cost": [0.0],
            "shares": [1],
            "sector": ["Technology"],
        }
    )
    t = summary.portfolio_totals(df)
    assert t["return_pct"] == 0

"""Tests for ui/summary.py totals."""

from datetime import UTC, datetime, timedelta

import pandas as pd

from ui import summary


class TestHumanizeAge:
    NOW = datetime(2026, 6, 1, 18, 0, tzinfo=UTC)

    def test_none_is_unknown(self):
        assert summary.humanize_age(None, now=self.NOW) == "unknown"

    def test_unparseable_is_unknown(self):
        assert summary.humanize_age("not-a-date", now=self.NOW) == "unknown"

    def test_minutes(self):
        ts = (self.NOW - timedelta(minutes=8)).isoformat()
        assert summary.humanize_age(ts, now=self.NOW) == "8m ago"

    def test_hours(self):
        ts = (self.NOW - timedelta(hours=20)).isoformat()
        assert summary.humanize_age(ts, now=self.NOW) == "20h ago"

    def test_days(self):
        ts = (self.NOW - timedelta(days=2, hours=3)).isoformat()
        assert summary.humanize_age(ts, now=self.NOW) == "2d ago"

    def test_just_now(self):
        ts = (self.NOW - timedelta(seconds=10)).isoformat()
        assert summary.humanize_age(ts, now=self.NOW) == "just now"

    def test_z_suffix_parsed(self):
        # SnapTrade-style timestamps may use a trailing Z.
        ts = "2026-06-01T10:00:00Z"
        assert summary.humanize_age(ts, now=self.NOW) == "8h ago"

    def test_naive_string_assumed_utc(self):
        ts = "2026-06-01T17:00:00"
        assert summary.humanize_age(ts, now=self.NOW) == "1h ago"

    def test_accepts_datetime(self):
        assert summary.humanize_age(self.NOW - timedelta(hours=3), now=self.NOW) == "3h ago"


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


def test_return_pct_uses_usd_cost_not_native_currency():
    # Regression for B1: a USD gainer + a non-USD holding. Summing native
    # avg_cost*shares (2nd row is HKD) would overstate cost and flip the return
    # negative on a real net gain. cost must be NAV - P&L (USD).
    df = pd.DataFrame(
        {
            "market_value": [10000.0, 12585.0],  # USD
            "unrealized_pnl": [4000.0, -125.0],  # USD → net +3875 gain
            "avg_cost": [50.0, 82.96],  # 2nd is native HKD
            "shares": [100, 1200],
            "sector": ["Tech", "Financials"],
        }
    )
    t = summary.portfolio_totals(df)
    assert t["pnl"] == 3875.0
    assert t["cost"] == 22585.0 - 3875.0  # USD cost, not 50*100 + 82.96*1200
    assert t["return_pct"] > 0  # a gain, not the buggy negative


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

"""Tests for ui/charts.py figure builders."""

from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from ui import charts


def _portfolio_df():
    return pd.DataFrame(
        {
            "ticker": ["AAPL", "MSFT", "XOM"],
            "shares": [10, 5, 20],
            "market_value": [2000.0, 1500.0, 1800.0],
            "sector": ["Technology", "Technology", "Energy"],
            "return_pct": [0.25, 0.10, -0.05],
            "unrealized_pnl": [400.0, 130.0, -90.0],
            "1y_return": [0.30, 0.15, 0.02],
            "3y_return": [0.20, 0.12, 0.08],
            "5y_return": [0.18, 0.14, 0.06],
            "10y_return": [0.16, 0.13, 0.05],
        }
    )


class _FakeCache:
    """Minimal price-cache stand-in with deterministic series."""

    def __init__(self):
        dates = pd.date_range(end="2026-04-07", periods=300, freq="B")
        self._series = {
            "AAPL": pd.Series(np.linspace(100, 160, 300), index=dates),
            "MSFT": pd.Series(np.linspace(200, 240, 300), index=dates),
            "XOM": pd.Series(np.linspace(80, 76, 300), index=dates),
            "SPY": pd.Series(np.linspace(400, 500, 300), index=dates),
        }

    def get_history(self, ticker):
        s = self._series.get(ticker)
        return pd.DataFrame({"Close": s}) if s is not None else pd.DataFrame()

    def get_spy_history(self):
        return self.get_history("SPY")


def test_sector_allocation_figure_groups_by_sector():
    fig = charts.sector_allocation_figure(_portfolio_df())
    assert fig is not None
    # Two sectors → two donut slices.
    assert set(fig.data[0].labels) == {"Technology", "Energy"}


def test_sector_allocation_figure_empty_when_no_sectors():
    df = _portfolio_df()
    df["sector"] = ""
    assert charts.sector_allocation_figure(df) is None


def test_performers_figure_orders_low_to_high():
    fig = charts.performers_figure(_portfolio_df(), "return_pct", n=5)
    assert fig is not None
    y_vals = list(fig.data[0].y)
    # Sorted ascending by return → worst (XOM) first.
    assert y_vals[0] == "XOM"


def test_performers_figure_none_for_missing_column():
    assert charts.performers_figure(_portfolio_df(), "nonexistent_col") is None


def test_performers_figure_dollars_mode_uses_unrealized_pnl():
    fig = charts.performers_figure(_portfolio_df(), "return_pct", dollars=True)
    assert fig is not None
    assert fig.layout.xaxis.title.text == "Return $"
    # x values are the dollar P&L (worst first after ascending sort) — XOM -90.
    assert fig.data[0].x[0] == pytest.approx(-90.0)


def test_portfolio_performance_figure_returns_none_without_tickers():
    assert charts.portfolio_performance_figure(_portfolio_df(), _FakeCache(), "1Y", []) is None


def test_show_portfolio_plots_only_aggregate_line():
    fig = charts.portfolio_performance_figure(
        _portfolio_df(),
        _FakeCache(),
        "1Y",
        ["AAPL", "MSFT", "XOM"],
        show_spy=False,
        show_portfolio=True,
    )
    assert {t.name for t in fig.data} == {"Portfolio"}  # no individual lines


def test_unchecked_portfolio_plots_individual_lines_sorted_desc():
    fig = charts.portfolio_performance_figure(
        _portfolio_df(),
        _FakeCache(),
        "1Y",
        ["AAPL", "MSFT", "XOM"],
        normalize=True,
        show_spy=False,
        show_portfolio=False,
    )
    order = [t.name for t in fig.data]
    # End values: AAPL +60% > MSFT +20% > XOM -5% → sorted high→low (F6).
    assert order == ["AAPL", "MSFT", "XOM"]


def test_show_portfolio_with_spy_has_both():
    fig = charts.portfolio_performance_figure(
        _portfolio_df(),
        _FakeCache(),
        "1Y",
        ["AAPL", "MSFT", "XOM"],
        show_spy=True,
        show_portfolio=True,
    )
    assert {t.name for t in fig.data} == {"Portfolio", "SPY"}


def test_portfolio_performance_figure_normalize_starts_at_100():
    fig = charts.portfolio_performance_figure(
        _portfolio_df(),
        _FakeCache(),
        "1Y",
        ["AAPL"],
        normalize=True,
        show_spy=False,
        show_portfolio=False,
    )
    aapl = next(t for t in fig.data if t.name == "AAPL")
    assert aapl.y[0] == pytest.approx(100.0)


def test_portfolio_performance_figure_can_hide_spy():
    fig = charts.portfolio_performance_figure(
        _portfolio_df(),
        _FakeCache(),
        "1Y",
        ["AAPL"],
        show_spy=False,
        show_portfolio=False,
    )
    assert "SPY" not in {t.name for t in fig.data}


def test_ytd_trimmer_uses_supplied_now():
    trim = charts._make_trimmer("YTD", now=datetime(2026, 4, 7))
    dates = pd.date_range("2025-06-01", "2026-04-07", freq="B")
    series = pd.Series(range(len(dates)), index=dates)
    trimmed = trim(series)
    assert trimmed.index.min() >= pd.Timestamp("2026-01-01")

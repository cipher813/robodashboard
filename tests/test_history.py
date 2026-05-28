"""Tests for ui/history.py figure + summary builders."""

import pandas as pd
import pytest

from ui import history as history_ui


def _history(navs, spys=None):
    n = len(navs)
    data = {"date": pd.date_range("2026-04-01", periods=n, freq="D"), "nav": navs}
    if spys is not None:
        data["spy_close"] = spys
    return pd.DataFrame(data)


def test_figure_none_with_single_snapshot():
    assert history_ui.nav_vs_spy_figure(_history([1000.0])) is None


def test_figure_includes_portfolio_and_spy():
    fig = history_ui.nav_vs_spy_figure(_history([1000.0, 1100.0, 1050.0], [500.0, 510.0, 505.0]))
    assert fig is not None
    assert {"Portfolio", "SPY"}.issubset({t.name for t in fig.data})


def test_figure_normalizes_to_100():
    fig = history_ui.nav_vs_spy_figure(_history([1000.0, 1200.0], [500.0, 525.0]), normalize=True)
    port = next(t for t in fig.data if t.name == "Portfolio")
    assert port.y[0] == pytest.approx(100.0)
    assert port.y[-1] == pytest.approx(120.0)


def test_figure_without_spy_column():
    fig = history_ui.nav_vs_spy_figure(_history([1000.0, 1100.0]))
    assert fig is not None
    assert "SPY" not in {t.name for t in fig.data}


def test_summary_computes_alpha():
    s = history_ui.history_summary(_history([1000.0, 1200.0], [500.0, 550.0]))
    assert s["port_return"] == pytest.approx(0.20)
    assert s["spy_return"] == pytest.approx(0.10)
    assert s["alpha"] == pytest.approx(0.10)
    assert s["n_days"] == 2


def test_summary_none_with_single_snapshot():
    assert history_ui.history_summary(_history([1000.0])) is None


def test_summary_alpha_none_without_spy():
    s = history_ui.history_summary(_history([1000.0, 1100.0]))
    assert s["spy_return"] is None
    assert s["alpha"] is None

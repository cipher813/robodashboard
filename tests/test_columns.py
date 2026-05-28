"""Tests for ui/columns.py registry + formatting."""

import pandas as pd

from ui import columns


def test_registry_groups_cover_all_non_always_columns():
    grouped = {k for keys in columns.COLUMN_GROUPS.values() for k in keys}
    non_always = {k for k, v in columns.ALL_COLUMNS.items() if not v.get("always")}
    assert grouped == non_always


def test_ticker_is_the_only_always_on_column():
    always = [k for k, v in columns.ALL_COLUMNS.items() if v.get("always")]
    assert always == ["ticker"]


def test_currency_columns_present_and_default_on():
    for k in ("currency", "market_value_local", "market_value"):
        assert k in columns.ALL_COLUMNS
        assert k in columns.DEFAULT_ON
    assert "USD" in columns.ALL_COLUMNS["market_value"]["label"]


def test_apply_display_formatting_scales_pct_columns():
    df = pd.DataFrame(
        {
            "ticker": ["AAPL"],
            "return_pct": [0.25],
            "pe_ratio": [30.0],
        }
    )
    out, present, cfg = columns.apply_display_formatting(df, ["ticker", "return_pct", "pe_ratio"])
    assert out["return_pct"].iloc[0] == 25.0  # scaled ×100
    assert out["pe_ratio"].iloc[0] == 30.0  # untouched (not a pct column)
    assert present == ["ticker", "return_pct", "pe_ratio"]
    assert set(cfg) == {"ticker", "return_pct", "pe_ratio"}


def test_apply_display_formatting_drops_absent_columns():
    df = pd.DataFrame({"ticker": ["AAPL"], "return_pct": [0.1]})
    _, present, cfg = columns.apply_display_formatting(df, ["ticker", "return_pct", "beta"])
    assert "beta" not in present
    assert "beta" not in cfg


def test_apply_display_formatting_preserves_nan():
    df = pd.DataFrame({"ticker": ["AAPL"], "vs_spy": [None]})
    out, _, _ = columns.apply_display_formatting(df, ["ticker", "vs_spy"])
    assert pd.isna(out["vs_spy"].iloc[0])

"""Tests for data/snapshots.py persistence."""

from datetime import date

import pandas as pd

from data import snapshots


def _df(nav_price=110.0):
    return pd.DataFrame(
        {
            "ticker": ["AAPL", "MSFT"],
            "shares": [10, 5],
            "avg_cost": [100.0, 200.0],
            "current_price": [nav_price, 220.0],
            "market_value": [10 * nav_price, 5 * 220.0],
            "unrealized_pnl": [10 * (nav_price - 100.0), 5 * 20.0],
        }
    )


def test_build_snapshot_row_computes_totals():
    row = snapshots.build_snapshot_row(_df(), spy_close=500.0, source="live", today=date(2026, 4, 7))
    assert row["nav"] == 10 * 110.0 + 5 * 220.0
    assert row["cost"] == 10 * 100.0 + 5 * 200.0
    assert row["spy_close"] == 500.0
    assert row["n_positions"] == 2
    assert row["source"] == "live"


def test_build_snapshot_row_records_authoritative_nav():
    """When authoritative NAV is given (positions + cash), it's recorded as NAV."""
    positions = 10 * 110.0 + 5 * 220.0  # 2200
    row = snapshots.build_snapshot_row(
        _df(), spy_close=500.0, source="live", nav=positions + 300.0, today=date(2026, 4, 7)
    )
    assert row["nav"] == positions + 300.0  # authoritative total, not positions-only
    # return_pct is the unrealized return on positions (pnl/cost), not nav/cost.
    expected_cost = 10 * 100.0 + 5 * 200.0
    expected_pnl = 10 * 10.0 + 5 * 20.0
    assert abs(row["return_pct"] - expected_pnl / expected_cost) < 1e-9


def test_build_snapshot_row_cost_is_fx_aware():
    """Foreign cost basis must be FX-converted, not summed at face value."""
    df = pd.DataFrame(
        {
            "ticker": ["1299.HK"],
            "shares": [1000],
            "avg_cost": [90.0],  # native HKD
            "current_price": [100.0],
            "fx_to_usd": [0.128],
            "market_value": [1000 * 100.0 * 0.128],  # USD
            "unrealized_pnl": [1000 * 10.0 * 0.128],  # USD
        }
    )
    row = snapshots.build_snapshot_row(df, spy_close=None, source="live", today=date(2026, 4, 7))
    # cost = 90 * 1000 * 0.128 = $11,520 (FX-converted), not $90,000.
    assert abs(row["cost"] - 90.0 * 1000 * 0.128) < 1e-6


def test_load_history_empty_when_absent(tmp_path):
    h = snapshots.load_history(tmp_path / "snapshots")
    assert h.empty


def test_write_snapshot_persists_and_reloads(tmp_path):
    d = tmp_path / "snapshots"
    snapshots.write_snapshot(_df(), spy_close=500.0, source="live", snapshots_dir=d, today=date(2026, 4, 6))
    snapshots.write_snapshot(_df(), spy_close=510.0, source="live", snapshots_dir=d, today=date(2026, 4, 7))
    h = snapshots.load_history(d)
    assert len(h) == 2
    assert list(h["spy_close"]) == [500.0, 510.0]


def test_write_snapshot_idempotent_per_day(tmp_path):
    d = tmp_path / "snapshots"
    snapshots.write_snapshot(
        _df(nav_price=110.0), spy_close=500.0, source="live", snapshots_dir=d, today=date(2026, 4, 7)
    )
    # Same day, updated figures → replaces, not duplicates.
    h = snapshots.write_snapshot(
        _df(nav_price=115.0), spy_close=505.0, source="live", snapshots_dir=d, today=date(2026, 4, 7)
    )
    assert len(h) == 1
    assert h["nav"].iloc[0] == 10 * 115.0 + 5 * 220.0
    assert h["spy_close"].iloc[0] == 505.0


def test_write_snapshot_sorts_by_date(tmp_path):
    d = tmp_path / "snapshots"
    snapshots.write_snapshot(_df(), spy_close=510.0, source="live", snapshots_dir=d, today=date(2026, 4, 7))
    snapshots.write_snapshot(_df(), spy_close=500.0, source="live", snapshots_dir=d, today=date(2026, 4, 6))
    h = snapshots.load_history(d)
    assert list(h["date"]) == sorted(h["date"])


def test_write_snapshot_empty_df_is_noop(tmp_path):
    d = tmp_path / "snapshots"
    h = snapshots.write_snapshot(pd.DataFrame(), spy_close=500.0, source="live", snapshots_dir=d)
    assert h.empty

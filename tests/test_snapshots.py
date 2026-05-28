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

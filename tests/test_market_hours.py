"""Tests for data/market_hours.py — US extended-hours session gating."""

from datetime import datetime
from zoneinfo import ZoneInfo

from data.market_hours import ET, is_extended_hours, market_session


def _et(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=ET)


class TestMarketSession:
    # 2026-06-01 is a Monday.
    def test_premarket(self):
        assert market_session(_et(2026, 6, 1, 5, 0)) == "pre"

    def test_regular(self):
        assert market_session(_et(2026, 6, 1, 10, 30)) == "regular"

    def test_post(self):
        assert market_session(_et(2026, 6, 1, 17, 0)) == "post"

    def test_before_premarket_is_closed(self):
        assert market_session(_et(2026, 6, 1, 3, 59)) == "closed"

    def test_after_post_is_closed(self):
        assert market_session(_et(2026, 6, 1, 20, 0)) == "closed"

    def test_boundaries_are_half_open(self):
        # Open boundaries belong to the starting session; close boundaries roll over.
        assert market_session(_et(2026, 6, 1, 4, 0)) == "pre"
        assert market_session(_et(2026, 6, 1, 9, 30)) == "regular"
        assert market_session(_et(2026, 6, 1, 16, 0)) == "post"

    def test_weekend_closed(self):
        # 2026-06-06 is a Saturday, 2026-06-07 a Sunday — closed even midday.
        assert market_session(_et(2026, 6, 6, 11, 0)) == "closed"
        assert market_session(_et(2026, 6, 7, 11, 0)) == "closed"


class TestIsExtendedHours:
    def test_true_during_sessions(self):
        for hh in (4, 9, 12, 16, 19):
            assert is_extended_hours(_et(2026, 6, 1, hh, 5)) is True

    def test_false_off_hours_and_weekends(self):
        assert is_extended_hours(_et(2026, 6, 1, 2, 0)) is False
        assert is_extended_hours(_et(2026, 6, 6, 12, 0)) is False

    def test_naive_datetime_assumed_et(self):
        # A naive datetime is treated as ET, not UTC.
        assert market_session(datetime(2026, 6, 1, 10, 30)) == "regular"

    def test_utc_input_converted(self):
        # 14:30 UTC == 10:30 ET (EDT) → regular session.
        utc = datetime(2026, 6, 1, 14, 30, tzinfo=ZoneInfo("UTC"))
        assert market_session(utc) == "regular"

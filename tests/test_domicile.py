"""Tests for US-vs-International domicile classification."""

from __future__ import annotations

from loaders.domicile import INTERNATIONAL, UNKNOWN, US, classify_domicile


def test_us_country_is_us():
    assert classify_domicile("AAPL", "United States") == US


def test_foreign_country_is_international():
    # ADRs: US-listed but foreign-domiciled → International.
    assert classify_domicile("RIO", "United Kingdom") == INTERNATIONAL
    assert classify_domicile("ASML", "Netherlands") == INTERNATIONAL
    assert classify_domicile("TSM", "Taiwan") == INTERNATIONAL


def test_missing_country_falls_back_to_non_us_suffix():
    assert classify_domicile("D05.SI", "") == INTERNATIONAL
    assert classify_domicile("RMS.PA", None) == INTERNATIONAL


def test_missing_country_and_us_style_ticker_is_unknown():
    assert classify_domicile("DIVI", "") == UNKNOWN


def test_override_wins_over_automatic():
    # DIVI is a US-domiciled international-exposure ETF; operator forces Intl.
    assert classify_domicile("DIVI", "", {"DIVI": "International"}) == INTERNATIONAL
    # Override also beats a present country.
    assert classify_domicile("AAPL", "United States", {"AAPL": "International"}) == INTERNATIONAL


def test_override_case_insensitive_keys_and_values():
    assert classify_domicile("divi", "", {"DIVI": "intl"}) == INTERNATIONAL
    assert classify_domicile("FOO", "Canada", {"foo": "US"}) == US

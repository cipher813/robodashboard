"""Tests for advisor/profile.py."""

from __future__ import annotations

from advisor.profile import InvestorProfile, load_profile


def test_load_profile_none_when_absent():
    assert load_profile({}) is None
    assert load_profile({"investor_profile": {}}) is None


def test_load_profile_parses_block():
    cfg = {
        "investor_profile": {
            "strategy": "growth with income",
            "target_allocation": {"us_equity": 0.60, "international": 0.15},
            "sector_preferences": {"overweight": ["Technology"], "avoid": ["Energy"]},
            "income_target": 25000,
            "max_single_position": 0.10,
        }
    }
    p = load_profile(cfg)
    assert isinstance(p, InvestorProfile)
    assert p.strategy == "growth with income"
    assert p.overweight_sectors == ["Technology"]
    assert p.avoid_sectors == ["Energy"]
    assert p.income_target == 25000
    assert p.max_single_position == 0.10


def test_equity_geo_targets_normalizes_to_equity_sleeve():
    # us_equity 0.60 + international 0.15 = 0.75 equity → 80% US / 20% Intl within equity.
    p = InvestorProfile(target_allocation={"us_equity": 0.60, "international": 0.15})
    us, intl = p.equity_geo_targets()
    assert round(us, 1) == 80.0
    assert round(intl, 1) == 20.0


def test_equity_geo_targets_none_without_targets():
    assert InvestorProfile().equity_geo_targets() is None

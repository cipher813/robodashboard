"""Tests for advisor/profile.py."""

from __future__ import annotations

from advisor.profile import InvestorProfile, load_profile, load_saved_block, save_profile


def test_load_profile_none_when_absent(tmp_path):
    # Explicit empty store path isolates from any real cache/investor_profile.json.
    store = tmp_path / "none.json"
    assert load_profile({}, store_path=store) is None
    assert load_profile({"investor_profile": {}}, store_path=store) is None


def test_load_profile_parses_block(tmp_path):
    cfg = {
        "investor_profile": {
            "strategy": "growth with income",
            "target_allocation": {"us_equity": 0.60, "international": 0.15},
            "sector_preferences": {"overweight": ["Technology"], "avoid": ["Energy"]},
            "income_target": 25000,
            "max_single_position": 0.10,
        }
    }
    p = load_profile(cfg, store_path=tmp_path / "none.json")
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


def test_to_config_block_omits_empty_fields():
    p = InvestorProfile(strategy="growth", max_single_position=0.10)
    block = p.to_config_block()
    assert block == {"strategy": "growth", "max_single_position": 0.10}
    # No empty strings / empty dicts / None leak through.
    assert "risk_tolerance" not in block
    assert "target_allocation" not in block
    assert "sector_preferences" not in block


def test_to_config_block_round_trips_through_loader():
    p = InvestorProfile(
        strategy="growth with income",
        risk_tolerance="moderate",
        time_horizon="10+ years",
        target_allocation={"us_equity": 0.64, "international": 0.36},
        overweight_sectors=["Technology"],
        avoid_sectors=["Energy"],
        income_target=25000.0,
        max_single_position=0.10,
        rebalance_frequency="quarterly",
    )
    # Round-trip: a profile's block reloads to an equal profile.
    reloaded = load_profile({"investor_profile": p.to_config_block()})
    assert reloaded == p


def test_save_and_load_saved_block_round_trip(tmp_path):
    store = tmp_path / "investor_profile.json"
    p = InvestorProfile(strategy="income", target_allocation={"us_equity": 0.6, "international": 0.4})
    save_profile(p, store_path=store)
    assert store.exists()
    block = load_saved_block(store)
    assert block["strategy"] == "income"
    assert block["target_allocation"] == {"us_equity": 0.6, "international": 0.4}


def test_saved_store_overrides_config_seed(tmp_path):
    store = tmp_path / "investor_profile.json"
    save_profile(InvestorProfile(strategy="from-store"), store_path=store)
    config = {"investor_profile": {"strategy": "from-config"}}
    # Store wins over the config seed.
    assert load_profile(config, store_path=store).strategy == "from-store"


def test_load_profile_falls_back_to_config_when_no_store(tmp_path):
    store = tmp_path / "missing.json"
    config = {"investor_profile": {"strategy": "from-config"}}
    assert load_profile(config, store_path=store).strategy == "from-config"


def test_load_profile_none_when_neither_present(tmp_path):
    assert load_profile({}, store_path=tmp_path / "missing.json") is None


def test_load_saved_block_handles_corrupt_file(tmp_path):
    store = tmp_path / "investor_profile.json"
    store.write_text("{not valid json")
    assert load_saved_block(store) is None

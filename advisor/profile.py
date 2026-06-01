"""Investor profile — the stated targets the advisor compares the portfolio against.

Plain dataclass (no pydantic) so the deterministic substrate stays dependency-light
and unit-testable without the AI stack installed. Parsed from the ``investor_profile``
config block (see config.yaml.example).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Where the in-app Preferences form persists the profile. Lives under the
# gitignored cache/ dir so it survives `git reset --hard` deploys (git never
# touches ignored files) and is never committed. The config block (SSM/yaml)
# is only the SEED default — a saved store always wins over it.
PROFILE_STORE = Path("cache/investor_profile.json")


@dataclass
class InvestorProfile:
    """Stated investment preferences/targets. All fields optional — the advisor
    degrades to whatever the operator filled in."""

    strategy: str = ""
    risk_tolerance: str = ""
    time_horizon: str = ""
    # Fractions of total portfolio, e.g. {"us_equity": 0.60, "international": 0.15, ...}
    target_allocation: dict[str, float] = field(default_factory=dict)
    overweight_sectors: list[str] = field(default_factory=list)
    avoid_sectors: list[str] = field(default_factory=list)
    income_target: float | None = None  # annual dividend income target, USD
    max_single_position: float | None = None  # fraction, e.g. 0.10 = 10%
    rebalance_frequency: str = ""

    def to_config_block(self) -> dict:
        """Serialize back to the ``investor_profile`` config-block schema.

        Symmetric with ``_block_to_profile`` so a saved store round-trips through
        the same loader the config block uses. Omits empty/None fields to keep the
        JSON tidy and to let a blank field read as 'unset' rather than 0/"".
        """
        block: dict = {}
        if self.strategy:
            block["strategy"] = self.strategy
        if self.risk_tolerance:
            block["risk_tolerance"] = self.risk_tolerance
        if self.time_horizon:
            block["time_horizon"] = self.time_horizon
        if self.target_allocation:
            block["target_allocation"] = dict(self.target_allocation)
        sp: dict = {}
        if self.overweight_sectors:
            sp["overweight"] = list(self.overweight_sectors)
        if self.avoid_sectors:
            sp["avoid"] = list(self.avoid_sectors)
        if sp:
            block["sector_preferences"] = sp
        if self.income_target is not None:
            block["income_target"] = self.income_target
        if self.max_single_position is not None:
            block["max_single_position"] = self.max_single_position
        if self.rebalance_frequency:
            block["rebalance_frequency"] = self.rebalance_frequency
        return block

    def equity_geo_targets(self) -> tuple[float, float] | None:
        """Return (us_pct, intl_pct) targets *within the equity sleeve*, normalized.

        The dashboard sees only the brokerage equity holdings, while
        ``target_allocation`` is expressed as fractions of the whole portfolio
        (including fixed income / alternatives held elsewhere). Normalizing the
        US vs international equity targets to sum to 100% gives an apples-to-apples
        comparison against the visible equity geographic split. Returns None if the
        targets aren't set.
        """
        us = self.target_allocation.get("us_equity")
        intl = self.target_allocation.get("international")
        if us is None or intl is None or (us + intl) <= 0:
            return None
        total = us + intl
        return us / total * 100, intl / total * 100


def _block_to_profile(ip: dict) -> InvestorProfile:
    """Build an InvestorProfile from an ``investor_profile``-shaped dict."""
    sp = ip.get("sector_preferences", {}) or {}
    return InvestorProfile(
        strategy=ip.get("strategy", "") or "",
        risk_tolerance=ip.get("risk_tolerance", "") or "",
        time_horizon=ip.get("time_horizon", "") or "",
        target_allocation=ip.get("target_allocation", {}) or {},
        overweight_sectors=list(sp.get("overweight", []) or []),
        avoid_sectors=list(sp.get("avoid", []) or []),
        income_target=ip.get("income_target"),
        max_single_position=ip.get("max_single_position"),
        rebalance_frequency=ip.get("rebalance_frequency", "") or "",
    )


def load_saved_block(store_path: Path = PROFILE_STORE) -> dict | None:
    """Read the user-saved profile block from the local store, or None if absent.

    Returns None on a missing or unreadable file (fail-soft → caller falls back
    to the config seed).
    """
    if not store_path.exists():
        return None
    try:
        data = json.loads(store_path.read_text())
        return data if isinstance(data, dict) and data else None
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Could not read saved investor profile %s: %s", store_path, e)
        return None


def save_profile(profile: InvestorProfile, store_path: Path = PROFILE_STORE) -> None:
    """Persist the profile to the local store (gitignored, survives deploys)."""
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text(json.dumps(profile.to_config_block(), indent=2))
    logger.info("Saved investor profile to %s", store_path)


def load_profile(config: dict, store_path: Path = PROFILE_STORE) -> InvestorProfile | None:
    """Resolve the active InvestorProfile: saved store wins, else config seed.

    The in-app Preferences form writes ``store_path``; that always overrides the
    ``investor_profile`` config block (the seed/default shipped via SSM/yaml).
    Returns None only when BOTH are absent — the advisor then reports the gaps it
    can and the narrative notes the missing targets.
    """
    block = load_saved_block(store_path) or config.get("investor_profile")
    if not block:
        return None
    return _block_to_profile(block)

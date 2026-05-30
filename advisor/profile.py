"""Investor profile — the stated targets the advisor compares the portfolio against.

Plain dataclass (no pydantic) so the deterministic substrate stays dependency-light
and unit-testable without the AI stack installed. Parsed from the ``investor_profile``
config block (see config.yaml.example).
"""

from __future__ import annotations

from dataclasses import dataclass, field


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


def load_profile(config: dict) -> InvestorProfile | None:
    """Build an InvestorProfile from the ``investor_profile`` config block.

    Returns None when the block is absent/empty (advisor then reports gaps it can,
    and the narrative notes the missing targets).
    """
    ip = config.get("investor_profile")
    if not ip:
        return None
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

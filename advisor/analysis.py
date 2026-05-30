"""Deterministic portfolio gap-analysis — the shared substrate the AI layer sits on.

Pure functions over the already-enriched, cached portfolio ``df`` (the same frame
the Overview renders) plus an ``InvestorProfile``. No LLM, no network, no recompute
of anything the dashboard already has. Fully unit-tested; the Claude narrative
(advisor/llm.py) consumes the structured output of ``analyze`` — it never recomputes.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

import pandas as pd

from advisor.profile import InvestorProfile


@dataclass
class GeoGap:
    us_pct: float
    intl_pct: float
    unknown_pct: float
    us_target_pct: float | None
    intl_target_pct: float | None
    us_gap_pp: float | None  # actual − target, percentage points (+ = over)
    intl_gap_pp: float | None


@dataclass
class SectorWeight:
    sector: str
    weight_pct: float  # percent of NAV
    flag: str  # "overweight_pref" | "avoid_violation" | ""


@dataclass
class ConcentrationBreach:
    ticker: str
    weight_pct: float  # percent of NAV
    limit_pct: float  # percent of NAV


@dataclass
class IncomeGap:
    annual_income: float  # USD
    portfolio_yield_pct: float  # weighted dividend yield, percent
    income_target: float | None
    income_gap: float | None  # target − actual (+ = short of target)


@dataclass
class PortfolioAnalysis:
    nav: float
    n_holdings: int
    geo: GeoGap
    sectors: list[SectorWeight] = field(default_factory=list)
    concentration: list[ConcentrationBreach] = field(default_factory=list)
    income: IncomeGap | None = None

    def to_dict(self) -> dict:
        """JSON-serializable form — used to build the LLM payload + cache key."""
        return asdict(self)


def _geo_gap(df: pd.DataFrame, nav: float, profile: InvestorProfile | None) -> GeoGap:
    by_geo = df.groupby("domicile")["market_value"].sum() if "domicile" in df.columns else pd.Series(dtype=float)

    def pct(label: str) -> float:
        return float(by_geo.get(label, 0.0)) / nav * 100 if nav > 0 else 0.0

    us_pct, intl_pct, unk_pct = pct("US"), pct("International"), pct("Unknown")

    us_t = intl_t = us_gap = intl_gap = None
    if profile is not None:
        targets = profile.equity_geo_targets()
        if targets is not None:
            us_t, intl_t = targets
            us_gap, intl_gap = us_pct - us_t, intl_pct - intl_t
    return GeoGap(
        us_pct=us_pct,
        intl_pct=intl_pct,
        unknown_pct=unk_pct,
        us_target_pct=us_t,
        intl_target_pct=intl_t,
        us_gap_pp=us_gap,
        intl_gap_pp=intl_gap,
    )


def _sector_weights(df: pd.DataFrame, nav: float, profile: InvestorProfile | None) -> list[SectorWeight]:
    if "sector" not in df.columns or nav <= 0:
        return []
    over = {s.lower() for s in (profile.overweight_sectors if profile else [])}
    avoid = {s.lower() for s in (profile.avoid_sectors if profile else [])}
    grp = df[df["sector"].astype(str) != ""].groupby("sector")["market_value"].sum()
    out: list[SectorWeight] = []
    for sector, mv in grp.sort_values(ascending=False).items():
        s = str(sector)
        flag = "avoid_violation" if s.lower() in avoid else ("overweight_pref" if s.lower() in over else "")
        out.append(SectorWeight(sector=s, weight_pct=float(mv) / nav * 100, flag=flag))
    return out


def _concentration(df: pd.DataFrame, profile: InvestorProfile | None) -> list[ConcentrationBreach]:
    if profile is None or profile.max_single_position is None or "weight_pct" not in df.columns:
        return []
    limit = profile.max_single_position  # fraction
    breaches = df[df["weight_pct"] > limit]
    return [
        ConcentrationBreach(ticker=str(r["ticker"]), weight_pct=float(r["weight_pct"]) * 100, limit_pct=limit * 100)
        for _, r in breaches.sort_values("weight_pct", ascending=False).iterrows()
    ]


def _income(df: pd.DataFrame, nav: float, profile: InvestorProfile | None) -> IncomeGap:
    # dividend_yield is a PERCENT number (e.g. 5.16 = 5.16%), per the columns formatter.
    if "dividend_yield" in df.columns:
        yields = pd.to_numeric(df["dividend_yield"], errors="coerce").fillna(0.0)
        annual_income = float((yields / 100.0 * df["market_value"]).sum())
    else:
        annual_income = 0.0
    port_yield = annual_income / nav * 100 if nav > 0 else 0.0
    target = profile.income_target if profile else None
    gap = (target - annual_income) if target is not None else None
    return IncomeGap(annual_income=annual_income, portfolio_yield_pct=port_yield, income_target=target, income_gap=gap)


def analyze(df: pd.DataFrame, profile: InvestorProfile | None) -> PortfolioAnalysis:
    """Compute the deterministic gap analysis for ``df`` against ``profile``.

    ``df`` is the enriched portfolio frame (needs ``market_value``; uses ``domicile``,
    ``sector``, ``weight_pct``, ``dividend_yield`` when present). ``profile`` may be
    None — gaps that need targets are simply omitted.
    """
    nav = float(df["market_value"].sum()) if "market_value" in df.columns else 0.0
    return PortfolioAnalysis(
        nav=nav,
        n_holdings=int(len(df)),
        geo=_geo_gap(df, nav, profile),
        sectors=_sector_weights(df, nav, profile),
        concentration=_concentration(df, profile),
        income=_income(df, nav, profile),
    )


def coarse_signature(analysis: PortfolioAnalysis, model: str, posture: str) -> str:
    """Stable cache key that ignores trivial price drift.

    Buckets NAV to ~$10k, percentages/gaps to ~1pp, and income to ~$100 so a few
    cents of price movement maps to the SAME key — the LLM commentary is only
    regenerated when something materially changed (an allocation crossing a point,
    a position breaching the cap, a sector shifting). This is the cost chokepoint:
    combined with the explicit Generate button, an LLM call happens only on a
    deliberate click for a genuinely new portfolio state.
    """
    g = analysis.geo

    def b1(x: float | None) -> int | None:
        return round(x) if x is not None else None

    parts = {
        "nav_10k": round(analysis.nav / 10_000),
        "us": b1(g.us_pct),
        "intl": b1(g.intl_pct),
        "us_gap": b1(g.us_gap_pp),
        "intl_gap": b1(g.intl_gap_pp),
        "conc": sorted((c.ticker, round(c.weight_pct)) for c in analysis.concentration),
        "sectors": sorted((s.sector, round(s.weight_pct), s.flag) for s in analysis.sectors),
        "income_100": round(analysis.income.annual_income / 100) if analysis.income else 0,
        "income_gap_100": (
            round(analysis.income.income_gap / 100)
            if (analysis.income and analysis.income.income_gap is not None)
            else None
        ),
        "model": model,
        "posture": posture,
    }
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()

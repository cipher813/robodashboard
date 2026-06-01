"""Investor Preferences page — fill in the targets the AI Advisor compares against.

Registered by ``app.py`` when ``ai_advisor.enabled`` is true (the profile only
feeds the advisor's gap analysis). The form seeds from the resolved profile
(saved store, else the config block) and persists to the local store via
``advisor.profile.save_profile`` — which overrides the config seed and survives
deploys (cache/ is gitignored, untouched by ``git reset --hard``).
"""

from __future__ import annotations

import streamlit as st

from advisor.profile import InvestorProfile, load_profile, save_profile
from bootstrap import get_clients, get_portfolio

# yfinance sector vocabulary — the analysis matches overweight/avoid against the
# `sector` field on holdings (which comes from yfinance), so the options must use
# the same names for the flags to actually land on positions.
STANDARD_SECTORS = [
    "Technology",
    "Healthcare",
    "Financial Services",
    "Consumer Cyclical",
    "Consumer Defensive",
    "Communication Services",
    "Industrials",
    "Basic Materials",
    "Real Estate",
    "Utilities",
    "Energy",
]


def _index(options: list[str], value: str) -> int:
    """Index of ``value`` in ``options`` (0 if absent) — for selectbox defaults."""
    return options.index(value) if value in options else 0


st.title("Investor Preferences")
st.caption(
    "Set the targets the AI Advisor measures your portfolio against. Saved here, "
    "these override the shipped defaults and persist across restarts."
)

config, _, _, _ = get_clients()
profile = load_profile(config) or InvestorProfile()

# Sector options = standard vocabulary ∪ whatever's actually held ∪ current picks,
# so every existing selection remains a valid option (Streamlit requires that).
df, _ = get_portfolio()
held_sectors = sorted({s for s in df.get("sector", []) if s}) if not df.empty else []
sector_options = sorted(
    set(STANDARD_SECTORS) | set(held_sectors) | set(profile.overweight_sectors) | set(profile.avoid_sectors)
)

RISK_OPTIONS = ["", "conservative", "moderate", "aggressive"]
HORIZON_OPTIONS = ["", "< 3 years", "3–10 years", "10+ years"]
REBALANCE_OPTIONS = ["", "monthly", "quarterly", "semi-annually", "annually"]

alloc = profile.target_allocation

with st.form("investor_preferences"):
    st.subheader("Strategy")
    c1, c2, c3 = st.columns(3)
    strategy = c1.text_input("Strategy", value=profile.strategy, placeholder="e.g. growth with income")
    risk = c2.selectbox("Risk tolerance", RISK_OPTIONS, index=_index(RISK_OPTIONS, profile.risk_tolerance))
    horizon = c3.selectbox("Time horizon", HORIZON_OPTIONS, index=_index(HORIZON_OPTIONS, profile.time_horizon))

    st.subheader("Target allocation")
    st.caption("Percent of your TOTAL portfolio (including assets held outside this brokerage). Aim for ~100%.")
    a1, a2, a3, a4 = st.columns(4)
    us = a1.number_input(
        "US equity %", min_value=0.0, max_value=100.0, step=1.0, value=alloc.get("us_equity", 0.0) * 100
    )
    intl = a2.number_input(
        "International %", min_value=0.0, max_value=100.0, step=1.0, value=alloc.get("international", 0.0) * 100
    )
    fixed = a3.number_input(
        "Fixed income %", min_value=0.0, max_value=100.0, step=1.0, value=alloc.get("fixed_income", 0.0) * 100
    )
    alts = a4.number_input(
        "Alternatives %", min_value=0.0, max_value=100.0, step=1.0, value=alloc.get("alternatives", 0.0) * 100
    )
    total_alloc = us + intl + fixed + alts
    st.caption(
        f"Total: {total_alloc:.0f}%" + ("" if abs(total_alloc - 100) <= 1 or total_alloc == 0 else " ⚠ not ~100%")
    )

    st.subheader("Sectors")
    s1, s2 = st.columns(2)
    overweight = s1.multiselect("Overweight (preferred)", sector_options, default=profile.overweight_sectors)
    avoid = s2.multiselect("Avoid", sector_options, default=profile.avoid_sectors)

    st.subheader("Limits & income")
    l1, l2, l3 = st.columns(3)
    max_pos = l1.number_input(
        "Max single position %",
        min_value=0.0,
        max_value=100.0,
        step=1.0,
        value=(profile.max_single_position or 0.0) * 100,
        help="0 = no limit. Positions above this flag in the advisor's concentration check.",
    )
    income = l2.number_input(
        "Annual income target $",
        min_value=0.0,
        step=1000.0,
        value=float(profile.income_target or 0.0),
        help="0 = no target.",
    )
    rebalance = l3.selectbox(
        "Rebalance frequency", REBALANCE_OPTIONS, index=_index(REBALANCE_OPTIONS, profile.rebalance_frequency)
    )

    submitted = st.form_submit_button("💾 Save preferences", type="primary")

if submitted:
    target_allocation = {
        key: round(pct / 100, 4)
        for key, pct in (("us_equity", us), ("international", intl), ("fixed_income", fixed), ("alternatives", alts))
        if pct > 0
    }
    save_profile(
        InvestorProfile(
            strategy=strategy.strip(),
            risk_tolerance=risk,
            time_horizon=horizon,
            target_allocation=target_allocation,
            overweight_sectors=overweight,
            avoid_sectors=avoid,
            income_target=float(income) if income > 0 else None,
            max_single_position=round(max_pos / 100, 4) if max_pos > 0 else None,
            rebalance_frequency=rebalance,
        )
    )
    st.success("Preferences saved — the AI Advisor will use these.")
    st.rerun()

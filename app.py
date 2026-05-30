"""RoboDashboard — personal portfolio analytics (multipage router).

Single entrypoint: owns the one allowed ``st.set_page_config`` call and builds
the page list via ``st.navigation`` (Streamlit's SOTA multipage API). Each page
body lives in ``views/``. ``st.navigation`` is re-evaluated every rerun, which is
what lets future pages (e.g. a gated AI Advisor) be added/removed live from a
sidebar toggle.

Usage:
    streamlit run app.py
"""

from __future__ import annotations

import logging

import streamlit as st

from bootstrap import get_clients

logging.basicConfig(level=logging.INFO)

st.set_page_config(page_title="RoboDashboard", page_icon=":chart_with_upwards_trend:", layout="wide")

pages = [
    st.Page("views/overview.py", title="Overview", icon=":material/dashboard:", default=True),
    st.Page("views/history.py", title="History", icon=":material/show_chart:"),
    st.Page("views/alpha_engine.py", title="Alpha Engine", icon=":material/smart_toy:"),
]

# AI Advisor — two-level gating:
#   1. Provisioning: ai_advisor.enabled (default False). When false the page is
#      never registered and advisor.llm/anthropic are never imported — a commercial
#      build ships with zero AI footprint (SEC investment-adviser gate).
#   2. Runtime: a sidebar "AI insights" toggle (only shown when provisioned) flips
#      the experience live. st.navigation is re-evaluated each rerun, so flipping it
#      adds/removes the page instantly — for A/B'ing with vs without AI.
config, *_ = get_clients()
ai_cfg = config.get("ai_advisor", {})
if ai_cfg.get("enabled", False):
    ai_on = st.sidebar.toggle("AI insights", value=ai_cfg.get("default_on", True), key="ai_insights_on")
    if ai_on:
        pages.append(st.Page("views/ai_advisor.py", title="AI Advisor", icon=":material/auto_awesome:"))

st.navigation(pages).run()

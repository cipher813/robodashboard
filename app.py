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

logging.basicConfig(level=logging.INFO)

st.set_page_config(page_title="RoboDashboard", page_icon=":chart_with_upwards_trend:", layout="wide")

pages = [
    st.Page("views/overview.py", title="Overview", icon=":material/dashboard:", default=True),
    st.Page("views/history.py", title="History", icon=":material/show_chart:"),
    st.Page("views/alpha_engine.py", title="Alpha Engine", icon=":material/smart_toy:"),
]

st.navigation(pages).run()

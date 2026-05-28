"""Shared Streamlit bootstrap for the dashboard's pages.

Wraps the Streamlit-free helpers in ``app_config`` with Streamlit caching so the
Overview page (``app.py``) and every page under ``pages/`` share one set of
clients and one cached portfolio load.
"""

from __future__ import annotations

import streamlit as st
from dotenv import load_dotenv

from app_config import init_clients, load_config
from loaders.portfolio_loader import load_portfolio

load_dotenv()


@st.cache_resource
def get_clients():
    """Load config + construct cache/reader once per session.

    Returns:
        (config, cache, reader, messages) — messages are (level, text) tuples.
    """
    config = load_config()
    cache, reader, messages = init_clients(config)
    return config, cache, reader, messages


@st.cache_data(ttl=300)
def get_portfolio():
    """Load + enrich the portfolio, cached for 5 minutes. Returns (df, source)."""
    _, cache, reader, _ = get_clients()
    return load_portfolio(reader, cache)


def render_client_messages(messages) -> None:
    """Surface the (level, text) init messages via st.info / st.warning."""
    for level, text in messages:
        getattr(st, level)(text)

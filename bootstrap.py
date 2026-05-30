"""Shared Streamlit bootstrap for the dashboard's pages.

Wraps the Streamlit-free helpers in ``app_config`` with Streamlit caching so the
Overview page (``app.py``) and every page under ``pages/`` share one set of
clients and one cached portfolio load.
"""

from __future__ import annotations

import streamlit as st
from dotenv import load_dotenv

from app_config import init_clients, load_config
from loaders.portfolio_loader import account_breakdown, load_portfolio

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
def get_portfolio(account_numbers: tuple[str, ...] | None = None):
    """Load + enrich the portfolio, cached for 5 minutes. Returns (df, source).

    ``account_numbers`` restricts to those accounts (per-account / multi-account
    view); None = all accounts consolidated. A tuple keeps it hashable for cache.
    """
    config, cache, reader, _ = get_clients()
    return load_portfolio(
        reader,
        cache,
        list(account_numbers) if account_numbers else None,
        domicile_overrides=config.get("domicile_overrides"),
    )


@st.cache_data(ttl=300)
def get_account_breakdown():
    """Per-account cash + positions (USD) + total. Returns a list of dicts."""
    config, cache, reader, _ = get_clients()
    return account_breakdown(reader, cache, config.get("accounts"))


@st.cache_data(ttl=300)
def get_account_options() -> list[tuple[str, str]]:
    """Return [(account_number, label)] for the account selector, in API order."""
    config, _, reader, _ = get_clients()
    if reader is None:
        return []
    labels = config.get("accounts") or {}
    out: list[tuple[str, str]] = []
    try:
        for a in reader.get_accounts():
            number, name = a.get("number", ""), a.get("name", "")
            out.append((number, labels.get(number) or labels.get(name) or name))
    except Exception:
        return []
    return out


def render_client_messages(messages) -> None:
    """Surface the (level, text) init messages via st.info / st.warning."""
    for level, text in messages:
        getattr(st, level)(text)

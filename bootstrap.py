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


@st.cache_data(ttl=900)
def get_live_quotes(symbols: tuple[str, ...]) -> dict[str, float]:
    """Latest intraday prices per symbol, cached 15 minutes (the live cadence).

    Returns ``{}`` outside extended market hours, on error, or when live quotes
    are disabled in config — callers then fall back to the daily close. The TTL
    here is what bounds the Yahoo pull frequency to once per 15 minutes per
    distinct symbol set, regardless of how often pages rerun.
    """
    config, cache, _, _ = get_clients()
    lq = config.get("live_quotes", {})
    if not lq.get("enabled", True):
        return {}
    return cache.get_live_quotes(list(symbols), prepost=lq.get("prepost", True))


@st.cache_data(ttl=300)
def get_portfolio(account_numbers: tuple[str, ...] | None = None):
    """Load + enrich the portfolio, cached for 5 minutes. Returns (df, source).

    ``account_numbers`` restricts to those accounts (per-account / multi-account
    view); None = all accounts consolidated. A tuple keeps it hashable for cache.

    Live intraday quotes are overlaid via ``get_live_quotes`` (15-min cache), so
    market value / P&L / NAV reflect ~15-min-delayed prices during market hours
    while positions stay on SnapTrade's daily sync.
    """
    config, cache, reader, _ = get_clients()
    quotes_fn = get_live_quotes if config.get("live_quotes", {}).get("enabled", True) else None
    return load_portfolio(
        reader,
        cache,
        list(account_numbers) if account_numbers else None,
        domicile_overrides=config.get("domicile_overrides"),
        quotes_fn=quotes_fn,
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

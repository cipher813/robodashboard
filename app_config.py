"""App-level configuration and client initialization.

Pulls the YAML config and constructs the shared PriceCache + SnapTradeReader.
Kept free of Streamlit imports so it stays unit-testable; rendering of any
warning/info messages is left to the caller (app.py).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml

from data.price_cache import PriceCache
from snaptrade_reader import SnapTradeReader

logger = logging.getLogger(__name__)

CONFIG_PATH = Path("config.yaml")


def load_config(path: Path = CONFIG_PATH) -> dict:
    """Load YAML config, returning {} if the file is absent."""
    if path.exists():
        with open(path) as f:
            return yaml.safe_load(f) or {}
    return {}


def init_clients(config: dict) -> tuple[PriceCache, SnapTradeReader | None, list[tuple[str, str]]]:
    """Construct the shared PriceCache and (optional) SnapTradeReader.

    Args:
        config: Parsed config dict (see load_config).

    Returns:
        (cache, reader, messages) where messages is a list of
        (level, text) tuples — level is one of "info" / "warning" — that the
        caller should surface (e.g. via st.info / st.warning).
    """
    cache_config = config.get("cache", {})
    cache = PriceCache(
        cache_dir=cache_config.get("price_history_dir", "cache"),
        max_age_hours=cache_config.get("max_age_hours", 24),
        info_max_age_hours=cache_config.get("info_max_age_hours", 168),
    )

    messages: list[tuple[str, str]] = []
    reader: SnapTradeReader | None = None
    if os.environ.get("SNAPTRADE_CLIENT_ID"):
        try:
            reader = SnapTradeReader.from_env()
        except Exception as e:
            messages.append(("warning", f"SnapTrade connection failed: {e}. Using cached data."))
    else:
        messages.append(("info", "No SnapTrade credentials found. Set SNAPTRADE_* env vars or use cached data."))

    return cache, reader, messages

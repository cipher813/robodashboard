"""Tests for app_config.py — config load + client init."""

from pathlib import Path

from app_config import init_clients, load_config


def test_load_config_missing_file_returns_empty(tmp_path):
    assert load_config(tmp_path / "nope.yaml") == {}


def test_load_config_parses_yaml(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("display:\n  default_sort: market_value\n")
    cfg = load_config(p)
    assert cfg["display"]["default_sort"] == "market_value"


def test_init_clients_no_creds_emits_info(monkeypatch):
    monkeypatch.delenv("SNAPTRADE_CLIENT_ID", raising=False)
    cache, reader, messages = init_clients({})
    assert reader is None
    assert cache is not None
    assert ("info", messages[0][1]) == messages[0] or messages[0][0] == "info"
    assert any(level == "info" for level, _ in messages)


def test_init_clients_respects_cache_config(monkeypatch, tmp_path):
    monkeypatch.delenv("SNAPTRADE_CLIENT_ID", raising=False)
    cache, _, _ = init_clients({"cache": {"price_history_dir": str(tmp_path / "c")}})
    assert (tmp_path / "c").exists()

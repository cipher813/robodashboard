"""Tests for advisor/llm.py — Claude narrative layer (no network; injected client)."""

from __future__ import annotations

import pandas as pd
import pytest

from advisor import llm
from advisor.analysis import analyze
from advisor.llm import AdvisoryCommentary, AiAdvisorUnavailable, build_payload, generate_commentary
from advisor.profile import InvestorProfile


def _analysis():
    df = pd.DataFrame(
        {
            "ticker": ["AAPL", "ASML"],
            "market_value": [6000.0, 4000.0],
            "domicile": ["US", "International"],
            "sector": ["Technology", "Technology"],
            "weight_pct": [0.60, 0.40],
            "dividend_yield": [0.5, 0.0],
        }
    )
    return analyze(df, InvestorProfile(target_allocation={"us_equity": 0.6, "international": 0.15}))


class _Block:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Resp:
    def __init__(self, content):
        self.content = content


class _FakeMessages:
    def __init__(self, parent):
        self._parent = parent

    def create(self, **kwargs):
        self._parent.last_payload = kwargs
        if self._parent.error:
            raise self._parent.error
        return self._parent.response


class _FakeClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.last_payload = None
        self.messages = _FakeMessages(self)


def test_build_payload_forces_tool_and_caches_system():
    payload = build_payload(_analysis(), None, model="claude-sonnet-4-6", posture="educational")
    assert payload["tool_choice"] == {"type": "tool", "name": llm.TOOL_NAME}
    assert payload["tools"][0]["name"] == llm.TOOL_NAME
    assert payload["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert payload["model"] == "claude-sonnet-4-6"


def test_posture_switches_system_prompt():
    edu = build_payload(_analysis(), None, posture="educational")["system"][0]["text"]
    candid = build_payload(_analysis(), None, posture="candid")["system"][0]["text"]
    assert edu != candid
    assert "educational" in edu.lower()


def test_generate_commentary_parses_tool_use():
    block = _Block(
        type="tool_use", name=llm.TOOL_NAME, input={"narrative": "Over intl target.", "considerations": ["a", "b"]}
    )
    client = _FakeClient(response=_Resp([block]))
    out = generate_commentary(_analysis(), None, client=client)
    assert isinstance(out, AdvisoryCommentary)
    assert out.narrative == "Over intl target."
    assert out.considerations == ["a", "b"]


def test_generate_commentary_raises_when_no_tool_block():
    client = _FakeClient(response=_Resp([_Block(type="text", text="hi")]))
    with pytest.raises(AiAdvisorUnavailable):
        generate_commentary(_analysis(), None, client=client)


def test_generate_commentary_wraps_api_error():
    client = _FakeClient(error=RuntimeError("API down"))
    with pytest.raises(AiAdvisorUnavailable):
        generate_commentary(_analysis(), None, client=client)


def test_generate_commentary_requires_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(AiAdvisorUnavailable, match="ANTHROPIC_API_KEY"):
        generate_commentary(_analysis(), None)  # no injected client → checks env

"""Claude narrative layer for the AI Advisor.

Consumes the deterministic ``PortfolioAnalysis`` (advisor/analysis.py) + the
``InvestorProfile`` and produces a short narrative + "areas to consider". Mirrors
the alpha-engine SOTA Anthropic pattern: forced tool-use for structured output,
``cache_control`` ephemeral on the static system prompt, ``Anthropic(max_retries=5)``.
Self-contained (no alpha_engine_lib, no direct pydantic) to keep robodashboard portable.

The module is imported ONLY when the AI Advisor is provisioned + toggled on, so a
commercial build with ``ai_advisor.enabled: false`` never touches the anthropic SDK.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from advisor.analysis import PortfolioAnalysis
from advisor.profile import InvestorProfile

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 1500
TOOL_NAME = "emit_advisory"


class AiAdvisorUnavailable(RuntimeError):
    """Raised when the AI advisor cannot produce commentary (missing key, SDK,
    API error, or a malformed response). Mirrors loaders.alpha_engine.AlphaEngineUnavailable
    so the page can surface *why* rather than silently blanking."""


@dataclass
class AdvisoryCommentary:
    narrative: str
    considerations: list[str]


# Forced-tool schema (hand-written JSON Schema — no pydantic dependency).
_TOOL = {
    "name": TOOL_NAME,
    "description": "Emit the portfolio advisory commentary as structured fields.",
    "input_schema": {
        "type": "object",
        "properties": {
            "narrative": {
                "type": "string",
                "description": (
                    "2–4 short paragraphs discussing how the portfolio relates to the stated "
                    "investor profile (geographic split vs target, sector tilts, concentration, "
                    "dividend income). Plain text, no markdown headers."
                ),
            },
            "considerations": {
                "type": "array",
                "items": {"type": "string"},
                "description": "3–6 concise 'areas to consider' bullets. No specific buy/sell order sizes.",
            },
        },
        "required": ["narrative", "considerations"],
    },
}

_SYSTEM_COMMON = (
    "You are a portfolio-analysis assistant for a single user's personal dashboard. "
    "You are given a DETERMINISTIC gap analysis (already computed) and the user's stated "
    "investor profile. Discuss what the numbers imply relative to the profile. "
    "Do NOT recompute or invent figures — only reference the values provided. "
    "Do NOT give specific buy/sell order sizes or time-the-market calls. "
    "This output is informational/educational only and is not personalized investment advice."
)

_SYSTEM_EDUCATIONAL = (
    _SYSTEM_COMMON + " Use measured, educational framing ('the profile target suggests…', 'considerations include…'). "
    "Surface tradeoffs rather than directives."
)

_SYSTEM_CANDID = (
    _SYSTEM_COMMON + " Speak plainly and directly to the user about where the portfolio diverges from their stated "
    "targets (e.g. 'you're well over your international target'), while still avoiding specific order sizes."
)


def _system_prompt(posture: str) -> str:
    return _SYSTEM_CANDID if str(posture).lower() == "candid" else _SYSTEM_EDUCATIONAL


def _profile_summary(profile: InvestorProfile | None) -> dict:
    if profile is None:
        return {"note": "No investor profile configured — comment only on what the analysis shows."}
    return {
        "strategy": profile.strategy,
        "risk_tolerance": profile.risk_tolerance,
        "time_horizon": profile.time_horizon,
        "target_allocation": profile.target_allocation,
        "overweight_sectors": profile.overweight_sectors,
        "avoid_sectors": profile.avoid_sectors,
        "income_target": profile.income_target,
        "max_single_position": profile.max_single_position,
        "rebalance_frequency": profile.rebalance_frequency,
    }


def _user_content(analysis: PortfolioAnalysis, profile: InvestorProfile | None) -> str:
    payload = {"investor_profile": _profile_summary(profile), "gap_analysis": analysis.to_dict()}
    return (
        "Here is the deterministic gap analysis and the investor profile as JSON. "
        "Write the advisory via the emit_advisory tool.\n\n" + json.dumps(payload, indent=2, default=str)
    )


def build_payload(
    analysis: PortfolioAnalysis,
    profile: InvestorProfile | None,
    *,
    model: str = DEFAULT_MODEL,
    posture: str = "educational",
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> dict:
    """Construct the messages.create kwargs (cache_control on system + forced tool)."""
    return {
        "model": model,
        "max_tokens": max_tokens,
        "system": [{"type": "text", "text": _system_prompt(posture), "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": _user_content(analysis, profile)}],
        "tools": [_TOOL],
        "tool_choice": {"type": "tool", "name": TOOL_NAME},
    }


def _parse(response) -> AdvisoryCommentary:
    block = next(
        (b for b in getattr(response, "content", []) if getattr(b, "type", None) == "tool_use" and b.name == TOOL_NAME),
        None,
    )
    if block is None:
        raise AiAdvisorUnavailable("Model did not return structured advisory output.")
    data = block.input or {}
    return AdvisoryCommentary(
        narrative=str(data.get("narrative", "")).strip(),
        considerations=[str(c) for c in (data.get("considerations") or [])],
    )


def generate_commentary(
    analysis: PortfolioAnalysis,
    profile: InvestorProfile | None,
    *,
    model: str = DEFAULT_MODEL,
    posture: str = "educational",
    max_tokens: int = DEFAULT_MAX_TOKENS,
    client=None,
) -> AdvisoryCommentary:
    """Generate advisory commentary via Claude. ``client`` is injectable for tests.

    Raises AiAdvisorUnavailable on any failure (missing key/SDK, API error, malformed
    response) so the page degrades gracefully.
    """
    if client is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise AiAdvisorUnavailable("ANTHROPIC_API_KEY not set — add it to .env or SSM to enable the AI Advisor.")
        try:
            import anthropic
        except ImportError as e:
            raise AiAdvisorUnavailable("anthropic SDK not installed — `pip install anthropic`.") from e
        try:
            client = anthropic.Anthropic(max_retries=5)
        except Exception as e:  # noqa: BLE001 — surface any client-construction failure to the page
            raise AiAdvisorUnavailable(f"Anthropic client error: {e}") from e

    payload = build_payload(analysis, profile, model=model, posture=posture, max_tokens=max_tokens)
    try:
        response = client.messages.create(**payload)
    except Exception as e:  # noqa: BLE001 — wrap SDK/API errors as the named exception
        raise AiAdvisorUnavailable(f"Anthropic API error: {e}") from e
    return _parse(response)

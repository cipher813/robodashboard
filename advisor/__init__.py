"""AI Advisor — gated, runtime-toggleable portfolio advisory layer.

Deterministic gap analysis (advisor.analysis) is the shared substrate; the Claude
narrative (advisor.llm) sits on top and is imported only when provisioned + enabled.
"""

from __future__ import annotations

DISCLAIMER = (
    "**Informational only — not investment advice.** This AI commentary is generated "
    "from your stated profile and current holdings for educational purposes. It is not a "
    "recommendation to buy or sell any security and not personalized investment advice. "
    "Consult a licensed financial advisor before making investment decisions."
)

__all__ = ["DISCLAIMER"]

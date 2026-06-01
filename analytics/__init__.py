"""Portfolio analytics engine — front-end-agnostic, dependency-light.

This package is the durable institutional-analytics asset (v0 of the
commercialization plan): pure, unit-testable functions that *describe and
measure* a portfolio — performance, risk, attribution — with no data-source or
Streamlit coupling. It contains NO advisory logic (no buy/sell prescriptions),
so it sits squarely on the pre-SEC "analytics, not advice" side of the line.

Start small (return math), grow into factor risk / attribution / scenario.
"""

from __future__ import annotations

from analytics.returns import (
    CashFlow,
    ValuationPoint,
    annualize,
    cumulative_return,
    time_weighted_return,
    xirr,
)
from analytics.riskstats import max_drawdown, sharpe_ratio, sortino_ratio, volatility

__all__ = [
    "CashFlow",
    "ValuationPoint",
    "annualize",
    "cumulative_return",
    "time_weighted_return",
    "xirr",
    "max_drawdown",
    "sharpe_ratio",
    "sortino_ratio",
    "volatility",
]

"""Glue layer: SnapTrade positions + price cache + metrics → enriched DataFrame.

Loads positions from SnapTrade (or cache fallback), enriches with yfinance
price data and computed metrics, returns a single DataFrame ready for display.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import pandas as pd

from data.metrics import (
    compute_beta,
    compute_personal_return,
    compute_returns,
    compute_rsi,
    compute_vs_spy,
    estimate_acquisition_date,
    pct_from_52w_high,
)
from data.price_cache import PriceCache
from loaders.domicile import classify_domicile
from snaptrade_reader import SnapTradeReader, aggregate_holdings

logger = logging.getLogger(__name__)

# SnapTrade → yfinance ticker normalization
# SnapTrade uses exchange-specific suffixes that differ from yfinance conventions
TICKER_MAP = {
    ".SP": ".SI",  # Singapore Exchange: SnapTrade uses .SP, yfinance uses .SI
    ".TO": ".TO",  # Toronto (same)
    ".L": ".L",  # London (same)
}


def _normalize_ticker(ticker: str) -> str:
    """Convert SnapTrade ticker format to yfinance format."""
    for snap_suffix, yf_suffix in TICKER_MAP.items():
        if ticker.endswith(snap_suffix):
            return ticker[: -len(snap_suffix)] + yf_suffix
    return ticker


def load_portfolio(
    reader: SnapTradeReader | None,
    cache: PriceCache,
    account_numbers: list[str] | None = None,
    domicile_overrides: dict | None = None,
    quotes_fn: Callable[[tuple[str, ...]], dict[str, float]] | None = None,
) -> tuple[pd.DataFrame, str]:
    """Load and enrich portfolio data.

    Args:
        reader: SnapTradeReader instance, or None for offline mode.
        cache: PriceCache for historical prices and fundamentals.
        account_numbers: Restrict to these accounts before aggregating
            (per-account / multi-account view). None = all accounts (consolidated).
        domicile_overrides: Optional ``{ticker: "US"|"International"}`` map that
            wins over the automatic US/International domicile classification.
        quotes_fn: Optional callable mapping a tuple of yfinance symbols (equity
            tickers + ``{CCY}USD=X`` FX pairs) to ``{symbol: latest_price}``. When
            provided, the returned intraday quotes override the daily-close
            ``current_price`` (and FX rate) per position — making market value,
            P&L, weights, and NAV reflect ~15-min-delayed live prices during
            market hours. None (default) keeps the daily-close behavior, so
            offline mode and tests are unaffected.

    Returns:
        (enriched_df, source) where source is "live" or "cached ({timestamp})".
    """
    # Get positions, aggregated by ticker over the selected accounts.
    if reader:
        try:
            holdings = reader.get_aggregated_holdings(account_numbers)
            source = "live"
        except Exception as e:
            logger.warning("SnapTrade fetch failed: %s — falling back to cache", e)
            cached, ts = SnapTradeReader.load_cached_holdings()
            holdings = aggregate_holdings(cached, account_numbers)
            source = f"cached ({ts})" if ts else "cached"
    else:
        cached, ts = SnapTradeReader.load_cached_holdings()
        holdings = aggregate_holdings(cached, account_numbers)
        source = f"cached ({ts})" if ts else "no data"

    if holdings.empty:
        return holdings, source

    live_quotes = _fetch_live_quotes(holdings, quotes_fn)
    return _enrich(holdings, cache, domicile_overrides, live_quotes), source


def _fetch_live_quotes(
    holdings: pd.DataFrame, quotes_fn: Callable[[tuple[str, ...]], dict[str, float]] | None
) -> dict[str, float]:
    """Resolve the live-quote symbol set from holdings and call ``quotes_fn``.

    Symbols = normalized equity tickers + one ``{CCY}USD=X`` pair per distinct
    non-USD currency. Fail-soft: any error yields ``{}`` so the daily-close path
    is used.
    """
    if quotes_fn is None:
        return {}
    symbols = {_normalize_ticker(t) for t in holdings["ticker"]}
    if "currency" in holdings.columns:
        for ccy in holdings["currency"].dropna().unique():
            code = str(ccy).upper()
            if code and code != "USD":
                symbols.add(f"{code}USD=X")
    try:
        return quotes_fn(tuple(sorted(symbols))) or {}
    except Exception as e:
        logger.warning("Live quote overlay failed: %s — using daily close", e)
        return {}


def _enrich(
    holdings: pd.DataFrame,
    cache: PriceCache,
    domicile_overrides: dict | None = None,
    live_quotes: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Enrich per-ticker aggregated holdings with prices, metrics, USD values.

    When ``live_quotes`` carries a fresher intraday price (or FX rate) for a
    symbol, it overrides the daily close from the price cache.
    """
    live_quotes = live_quotes or {}
    # Get SPY history for beta computation
    spy_hist = cache.get_spy_history()
    spy_close = spy_hist["Close"] if not spy_hist.empty else pd.Series(dtype=float)

    # Enrich each ticker
    enriched_rows = []
    for _, row in holdings.iterrows():
        ticker = _normalize_ticker(row["ticker"])
        shares = row["shares"]
        avg_cost = row.get("avg_cost", 0)
        currency = row.get("currency", "USD") or "USD"

        # Price history + info
        hist = cache.get_history(ticker)
        info = cache.get_info(ticker)
        close = hist["Close"] if not hist.empty else pd.Series(dtype=float)
        current_price = float(close.iloc[-1]) if not close.empty else 0

        # Live-quote overlay: a fresher intraday price (~15-min delayed, incl.
        # pre/post-market) replaces the daily close. Historical metrics below
        # (returns/beta/rsi/vs_spy) keep using the daily series — only the
        # spot-price-derived values (market value, P&L, weight, % from 52w high)
        # pick up the live number.
        live_price = live_quotes.get(ticker)
        if live_price and live_price > 0:
            current_price = live_price

        # Compute metrics. current_price/avg_cost are in the security's native
        # currency; returns/ratios are currency-independent so they need no FX.
        returns = compute_returns(close) if not close.empty else {}
        beta = compute_beta(close, spy_close) if not close.empty and not spy_close.empty else None
        rsi = compute_rsi(close) if not close.empty else None
        personal_ret = compute_personal_return(current_price, avg_cost)
        pct_52w = pct_from_52w_high(current_price, info.get("fifty_two_week_high"))
        acq_date = estimate_acquisition_date(close, avg_cost)
        vs_spy = compute_vs_spy(close, spy_close, acq_date)

        # Value amounts: compute in native currency, then convert to USD so NAV,
        # weights, and P&L aggregate correctly across currencies. A live FX rate
        # (from the same intraday pull) overrides the cached daily rate.
        fx = cache.get_fx_rate(currency)
        if currency.upper() != "USD":
            live_fx = live_quotes.get(f"{currency.upper()}USD=X")
            if live_fx and live_fx > 0:
                fx = live_fx
        market_value_local = shares * current_price
        pnl_local = market_value_local - (shares * avg_cost) if avg_cost else 0
        market_value = market_value_local * fx
        unrealized_pnl = pnl_local * fx

        enriched_rows.append(
            {
                "ticker": ticker,
                "name": info.get("name", ticker),
                "sector": info.get("sector", ""),
                "country": info.get("country", ""),
                "domicile": classify_domicile(ticker, info.get("country", ""), domicile_overrides),
                "currency": currency,
                "fx_to_usd": fx,
                "shares": shares,
                "avg_cost": avg_cost,
                "current_price": current_price,
                "market_value_local": market_value_local,
                "market_value": market_value,
                "unrealized_pnl": unrealized_pnl,
                "return_pct": personal_ret,
                "vs_spy": vs_spy,
                "est_acq_date": acq_date,
                "1y_return": returns.get(1),
                "3y_return": returns.get(3),
                "5y_return": returns.get(5),
                "10y_return": returns.get(10),
                "beta": beta,
                "rsi": rsi,
                "dividend_yield": info.get("dividend_yield"),
                "52w_high": info.get("fifty_two_week_high"),
                "52w_low": info.get("fifty_two_week_low"),
                "pct_from_52w_high": pct_52w,
                "pe_ratio": info.get("pe_ratio"),
                "forward_pe": info.get("forward_pe"),
                "peg_ratio": info.get("peg_ratio"),
                "ev_to_ebitda": info.get("ev_to_ebitda"),
                "earnings_growth": info.get("earnings_growth"),
                "revenue_growth": info.get("revenue_growth"),
                "debt_to_equity": info.get("debt_to_equity"),
                "n_accounts": row.get("n_accounts", 1),
            }
        )

    df = pd.DataFrame(enriched_rows)

    # Compute weight %
    total_value = df["market_value"].sum()
    df["weight_pct"] = df["market_value"] / total_value if total_value > 0 else 0

    return df


def _positions_usd(all_holdings: pd.DataFrame, number: str, cache: PriceCache) -> float:
    """Sum a single account's position market values, FX-converted to USD.

    Uses SnapTrade's broker-reported ``market_value`` (units × current price in
    the security's native currency) rather than yfinance prices, so the figure
    is consistent with IBKR's own valuation — the cash plug derived from it then
    reconciles to IBKR's authoritative account total.
    """
    if all_holdings.empty or "account_number" not in all_holdings.columns:
        return 0.0
    sub = all_holdings[all_holdings["account_number"] == number]
    if sub.empty:
        return 0.0
    return float(
        sum(float(r["market_value"]) * cache.get_fx_rate(r.get("currency", "USD") or "USD") for _, r in sub.iterrows())
    )


def account_breakdown(reader: SnapTradeReader | None, cache: PriceCache, labels: dict | None = None) -> list[dict]:
    """Per-account balances: positions (USD) + derived cash + IBKR total.

    ``total`` is IBKR's authoritative per-account value (USD, positions + cash,
    converted with IBKR's own FX). ``positions`` is the broker-reported holdings
    value FX-converted to USD. ``cash`` is derived as ``total − positions`` — a
    plug against the authoritative total, NOT a face-value sum of per-currency
    cash buckets (which would add HKD/SGD/USD as if all were dollars and badly
    overstate cash). Pulls holdings once; returns [] when there's no reader.
    """
    if reader is None:
        return []
    labels = labels or {}
    try:
        all_holdings = reader.get_all_holdings()
        accounts = reader.get_accounts()
    except Exception as e:  # best-effort; the breakdown is secondary
        logger.warning("account_breakdown fetch failed: %s", e)
        return []

    rows = []
    for acct in accounts:
        number = acct.get("number", "")
        name = acct["name"]
        label = labels.get(number) or labels.get(name) or name
        total = float(acct.get("balance_total", 0.0))
        positions = _positions_usd(all_holdings, number, cache)
        cash = total - positions
        rows.append({"label": label, "number": number, "cash": cash, "positions": positions, "total": total})
    return rows

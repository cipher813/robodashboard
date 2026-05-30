"""Plotly figure builders for the dashboard charts.

These functions return Plotly figures (or None when there's nothing to plot)
and take a DataFrame plus, where needed, a price-cache-like object exposing
``get_history(ticker)`` and ``get_spy_history()``. They contain no Streamlit
calls so they can be unit-tested directly.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Trading-day counts per selectable window. YTD is special-cased (None).
PERIOD_MAP: dict[str, int | None] = {
    "LTM": 252,
    "YTD": None,
    "1Y": 252,
    "3Y": 756,
    "5Y": 1260,
    "10Y": 2520,
}

# Performers-window label → DataFrame column.
PERFORMERS_COL_MAP: dict[str, str] = {
    "My Return (since acquisition)": "return_pct",
    "LTM": "1y_return",
    "1Y": "1y_return",
    "3Y": "3y_return",
    "5Y": "5y_return",
    "10Y": "10y_return",
}


def sector_allocation_figure(df: pd.DataFrame) -> go.Figure | None:
    """Donut chart of portfolio market value by sector."""
    sector_df = df.groupby("sector")["market_value"].sum().reset_index()
    sector_df = sector_df[sector_df["sector"] != ""]
    if sector_df.empty:
        return None
    sector_df["pct"] = sector_df["market_value"] / sector_df["market_value"].sum() * 100
    sector_df.sort_values("pct", ascending=False, inplace=True)
    fig = px.pie(sector_df, values="market_value", names="sector", hole=0.4)
    fig.update_traces(textposition="inside", textinfo="label+percent")
    fig.update_layout(showlegend=False, margin=dict(t=0, b=0, l=0, r=0), height=400)
    return fig


def performers_figure(df: pd.DataFrame, perf_col: str, n: int | None = 5, *, dollars: bool = False) -> go.Figure | None:
    """Horizontal bar chart of performers.

    ``n`` is the count taken from EACH end (top ``n`` gainers + bottom ``n``
    losers). ``n=None`` shows ALL holdings. ``dollars=False`` plots ``perf_col``
    as a percentage; ``dollars=True`` plots the position's USD dollar gain
    (``unrealized_pnl``) instead.
    """
    value_col = "unrealized_pnl" if dollars else perf_col
    if value_col not in df.columns:
        return None
    perf_df = df[df[value_col].notna()].copy()
    if perf_df.empty:
        return None
    perf_df["return_display"] = perf_df[value_col] if dollars else perf_df[value_col] * 100
    perf_df.sort_values("return_display", inplace=True)
    if n is None:
        show_df = perf_df
    else:
        n_show = min(n, len(perf_df))
        show_df = pd.concat([perf_df.head(n_show), perf_df.tail(n_show)]).drop_duplicates()
    show_df = show_df.sort_values("return_display")
    if show_df.empty:
        return None
    axis_label = "Return $" if dollars else "Return %"
    fig = px.bar(
        show_df,
        x="return_display",
        y="ticker",
        orientation="h",
        color="return_display",
        color_continuous_scale=["#ef4444", "#22c55e"],
        labels={"return_display": axis_label, "ticker": ""},
    )
    # Scale height so all bars stay readable when showing many holdings.
    height = max(400, len(show_df) * 22 + 80)
    fig.update_layout(
        showlegend=False,
        coloraxis_showscale=False,
        margin=dict(t=0, b=0, l=0, r=0),
        height=height,
    )
    if dollars:
        fig.update_xaxes(tickprefix="$")
    return fig


# US / International / Unknown → fixed colors so the slice mapping is stable.
_GEO_COLORS = {"US": "#3b82f6", "International": "#f59e0b", "Unknown": "#9ca3af"}


def geo_exposure_figure(df: pd.DataFrame) -> go.Figure | None:
    """Donut of US vs International exposure by USD market value (by domicile).

    Reads the ``domicile`` column (US / International / Unknown). ADRs are
    International here because ``domicile`` is classified by the company's
    country, not its listing venue.
    """
    if "domicile" not in df.columns or "market_value" not in df.columns:
        return None
    geo_df = df[df["market_value"].notna()].copy()
    geo_df = geo_df[geo_df["domicile"].astype(str) != ""]
    if geo_df.empty:
        return None
    grp = geo_df.groupby("domicile")["market_value"].sum().reset_index()
    if grp.empty or grp["market_value"].sum() <= 0:
        return None
    # Stable slice order: US, International, then any Unknown.
    order = {"US": 0, "International": 1, "Unknown": 2}
    grp["__o"] = grp["domicile"].map(lambda d: order.get(d, 3))
    grp.sort_values("__o", inplace=True)
    fig = px.pie(
        grp,
        values="market_value",
        names="domicile",
        hole=0.4,
        color="domicile",
        color_discrete_map=_GEO_COLORS,
    )
    fig.update_traces(textposition="inside", textinfo="label+percent")
    fig.update_layout(showlegend=True, margin=dict(t=0, b=0, l=0, r=0), height=400)
    return fig


def _normalize_close_index(series: pd.Series) -> pd.Series:
    """Drop tz, normalize to date, de-duplicate so cross-exchange dates align."""
    series = series.copy()
    series.index = series.index.tz_localize(None) if series.index.tz is not None else series.index
    series.index = series.index.normalize()
    return series[~series.index.duplicated(keep="last")]


def _make_trimmer(period: str, now: datetime | None = None):
    """Return a function that trims a price series to the selected period."""
    if period == "YTD":
        year = (now or datetime.now()).year
        cutoff_date = pd.Timestamp(f"{year}-01-01")

        def trim(series: pd.Series) -> pd.Series:
            ct = cutoff_date.tz_localize(series.index.tz) if series.index.tz is not None else cutoff_date
            return series[series.index >= ct]
    else:
        trading_days = PERIOD_MAP[period]

        def trim(series: pd.Series) -> pd.Series:
            return series.iloc[-trading_days:] if len(series) >= trading_days else series

    return trim


def portfolio_performance_figure(
    df: pd.DataFrame,
    cache,
    period: str,
    selected_tickers: list[str],
    *,
    normalize: bool = True,
    show_spy: bool = True,
    show_portfolio: bool = True,
    now: datetime | None = None,
) -> go.Figure | None:
    """Interactive line chart of per-stock + portfolio + SPY price series.

    Args:
        df: Enriched portfolio DataFrame (needs ``ticker`` + ``shares``).
        cache: Object exposing ``get_history(ticker)`` + ``get_spy_history()``.
        period: One of PERIOD_MAP keys.
        selected_tickers: Tickers to plot.
        normalize: Index each series to 100 at its start.
        show_spy: Overlay SPY (dashed).
        show_portfolio: Overlay market-value-weighted portfolio aggregate.
        now: Reference date for the YTD cutoff (defaults to datetime.now()).

    Returns:
        A Plotly Figure, or None if no tickers were selected.
    """
    if not selected_tickers:
        return None

    trim = _make_trimmer(period, now)
    fig = go.Figure()

    # Load + normalize price series per ticker.
    ticker_series: dict[str, pd.Series] = {}
    for ticker in selected_tickers:
        hist = cache.get_history(ticker)
        if hist.empty:
            continue
        close = trim(hist["Close"])
        if close.empty:
            continue
        ticker_series[ticker] = _normalize_close_index(close)

    if show_portfolio:
        # Single market-value-weighted aggregate line only (no individual lines).
        shares_map = dict(zip(df["ticker"], df["shares"], strict=True))
        portfolio_components = {
            ticker: close * shares_map.get(ticker, 0)
            for ticker, close in ticker_series.items()
            if shares_map.get(ticker, 0) > 0
        }
        if portfolio_components:
            combined = pd.DataFrame(portfolio_components).ffill().dropna()
            portfolio_value = combined.sum(axis=1)
            if not portfolio_value.empty:
                port_vals = (portfolio_value / portfolio_value.iloc[0]) * 100 if normalize else portfolio_value
                fig.add_trace(
                    go.Scatter(
                        x=port_vals.index,
                        y=port_vals.values,
                        mode="lines",
                        name="Portfolio",
                        line=dict(color="white", width=3),
                    )
                )
    else:
        # Individual stock lines, added best→worst by end value so the unified
        # hover lists them highest-return first.
        def _end_value(close: pd.Series) -> float:
            vals = (close / close.iloc[0]) * 100 if normalize else close
            return float(vals.iloc[-1])

        for ticker, close in sorted(ticker_series.items(), key=lambda kv: _end_value(kv[1]), reverse=True):
            plot_vals = (close / close.iloc[0]) * 100 if normalize else close
            fig.add_trace(go.Scatter(x=plot_vals.index, y=plot_vals.values, mode="lines", name=ticker))

    # SPY overlay.
    if show_spy:
        spy_hist = cache.get_spy_history()
        if not spy_hist.empty:
            spy_close = trim(spy_hist["Close"])
            if not spy_close.empty:
                spy_close = _normalize_close_index(spy_close)
                spy_vals = (spy_close / spy_close.iloc[0]) * 100 if normalize else spy_close
                fig.add_trace(
                    go.Scatter(
                        x=spy_vals.index,
                        y=spy_vals.values,
                        mode="lines",
                        name="SPY",
                        line=dict(color="gray", width=2, dash="dash"),
                    )
                )

    y_label = "Indexed (100 = start)" if normalize else "Price ($)"
    fig.update_layout(
        height=500,
        margin=dict(t=10, b=40, l=60, r=10),
        yaxis_title=y_label,
        xaxis_title="",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified",
    )
    return fig

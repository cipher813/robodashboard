[![CI](https://github.com/cipher813/robodashboard/actions/workflows/ci.yml/badge.svg)](https://github.com/cipher813/robodashboard/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

# RoboDashboard

Personal portfolio analytics dashboard. Connects to brokerage accounts via SnapTrade, aggregates holdings across institutions, and displays customizable financial indicators with interactive performance charting.

## How it works

```
[Interactive Brokers] --SnapTrade API--> [snaptrade_reader.py] --> positions + cost basis
                                                |
[yfinance] --prices/fundamentals--> [price_cache.py] --> 10Y OHLCV + company data
                                                |
                                    [portfolio_loader.py] --> enriched DataFrame
                                                |
                                         [app.py] --> Streamlit dashboard
```

- **Brokerage data:** SnapTrade API (read-only, no trading) with offline cache fallback
- **Market data:** yfinance for historical prices, fundamentals, and technicals
- **Dashboard:** Streamlit + Plotly with customizable columns and interactive charts
- **Cost:** $0/month (SnapTrade free tier, yfinance free, runs locally)

## Quick start

```bash
git clone https://github.com/cipher813/robodashboard.git
cd robodashboard
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Copy and fill in credentials
cp .env.example .env
cp config.yaml.example config.yaml

# Link brokerage account (one-time)
python tools/link_account.py

# Run dashboard
streamlit run app.py
```

## Features

### Holdings table

25+ financial indicators organized into 7 toggleable groups:

| Group | Indicators |
|-------|------------|
| **Core** | Name, Shares, Price, Mkt Value |
| **Position** | Sector, Weight %, Avg Cost, P&L, Est. Acquired |
| **Performance** | My Return, vs SPY, 1Y/3Y/5Y/10Y Returns |
| **Valuation** | P/E, Fwd P/E, PEG, EV/EBITDA, EPS Growth, Rev Growth |
| **Fundamentals** | Debt-to-Equity |
| **Technical** | Beta, RSI (14d), vs 52W High |
| **Income** | Dividend Yield |

Only Ticker is always shown. All other columns are user-selectable via checkbox groups.

### Charts

- **Sector allocation** -- donut chart of portfolio by sector
- **Top/bottom performers** -- horizontal bar chart with selectable time window (My Return, LTM, 1Y, 3Y, 5Y, 10Y)
- **Portfolio performance** -- interactive line chart with:
  - Date range selector (LTM, YTD, 1Y, 3Y, 5Y, 10Y)
  - Per-stock toggle (select/deselect individual holdings)
  - Market-value-weighted portfolio aggregate line
  - SPY overlay (dashed)
  - Normalize to 100 toggle for indexed comparison

### Data pipeline

- **Multi-account aggregation** -- combines holdings across sub-accounts with weighted avg cost basis
- **Cross-exchange support** -- ticker normalization (SnapTrade `.SP` to yfinance `.SI` for SGX) and timezone alignment
- **Offline resilience** -- cached positions and prices with automatic fallback on API failures
- **Delta updates** -- price cache only fetches new data since last cache date

## Project structure

```
robodashboard/
├── app.py                      # Streamlit dashboard
├── snaptrade_reader.py         # Read-only SnapTrade API client
├── data/
│   ├── metrics.py              # Financial metric computation (no API calls)
│   └── price_cache.py          # 10Y OHLCV + fundamentals cache (yfinance)
├── loaders/
│   └── portfolio_loader.py     # Positions + prices + metrics enrichment
├── tools/
│   └── link_account.py         # One-time SnapTrade account linking
├── tests/
│   ├── test_smoke.py           # Import + config checks
│   ├── test_metrics.py         # Metric computation tests
│   └── test_portfolio_loader.py # Portfolio enrichment tests
├── cache/                      # Runtime cache (gitignored)
│   ├── prices/*.parquet        # Historical OHLCV
│   ├── info/*.json             # Company fundamentals (7-day TTL)
│   └── positions_latest.json   # Latest SnapTrade snapshot
├── config.yaml.example         # Display + cache configuration
├── .env.example                # Credentials template
└── .github/workflows/ci.yml   # pytest + gitleaks + pip-audit
```

## Metrics computed

| Metric | Source | Description |
|--------|--------|-------------|
| Personal return | cost basis vs current price | Your return since purchase |
| vs SPY | stock vs SPY since est. acquisition | Outperformance vs benchmark |
| Est. acquisition date | price history matching avg cost | Approximate purchase date |
| 1Y/3Y/5Y/10Y returns | price history | Annualized stock returns |
| Beta | 252-day covariance vs SPY | Market sensitivity |
| RSI | 14-day relative strength | Momentum indicator |
| P/E, Fwd P/E | yfinance | Trailing and forward earnings multiples |
| PEG | yfinance (trailingPegRatio) | Price-to-earnings-to-growth |
| EV/EBITDA | yfinance | Enterprise value multiple |
| EPS/Revenue growth | yfinance | Year-over-year growth rates |
| D/E | yfinance | Debt-to-equity ratio |
| Dividend yield | yfinance | Forward dividend yield |
| vs 52W high | yfinance | Distance from 52-week high |

## Configuration

### config.yaml

```yaml
display:
  default_sort: "market_value"
  default_sort_ascending: false
  hide_zero_positions: true

cache:
  price_history_dir: "cache"
  max_age_hours: 24              # price data refresh interval
  info_max_age_hours: 168        # fundamentals refresh (weekly)
```

### Environment variables

| Variable | Description |
|----------|-------------|
| `SNAPTRADE_CLIENT_ID` | SnapTrade app ID |
| `SNAPTRADE_CONSUMER_KEY` | SnapTrade API key |
| `SNAPTRADE_USER_ID` | Created during account linking |
| `SNAPTRADE_USER_SECRET` | Created during account linking |

## CI/CD

GitHub Actions runs on push to `main` and PRs:

1. **Tests** -- pytest on Python 3.11 + 3.12
2. **Secrets scan** -- gitleaks v2
3. **Dependency audit** -- pip-audit (with cryptography CVE exclusions from SnapTrade SDK pin)

## Stack

- [Streamlit](https://streamlit.io) -- dashboard framework
- [Plotly](https://plotly.com) -- interactive charts
- [SnapTrade SDK](https://github.com/passiv/snaptrade-sdks) -- brokerage API (read-only)
- [yfinance](https://github.com/ranaroussi/yfinance) -- market data
- [pandas](https://pandas.pydata.org) + [numpy](https://numpy.org) -- data processing
- [PyArrow](https://arrow.apache.org) -- parquet caching

## License

MIT

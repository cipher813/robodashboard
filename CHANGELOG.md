# Changelog

All notable changes to RoboDashboard are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Repo hardening for public release: `pyproject.toml` (ruff + pytest + coverage config),
  ruff lint + format gate and a 3.11/3.12/3.13 test matrix with a 90% coverage gate in CI,
  ruff pre-commit hooks, CodeQL workflow, Dependabot (pip + github-actions), `CONTRIBUTING.md`,
  `SECURITY.md`, this changelog, and `main`-branch protection.
- **Alpha Engine page** (`pages/2_Alpha_Engine.py`): overlays the alpha-engine research
  signals (ENTER/HOLD/EXIT + score + thesis) and predictor predictions (direction +
  confidence + 21d alpha + veto) onto real holdings; reads S3 via the default AWS profile;
  lists un-held buy candidates. Degrades gracefully when AWS/boto3 are unavailable.
- **History page** (`pages/1_History.py`): real NAV-vs-SPY time series from daily snapshots
  persisted to `cache/snapshots/history.parquet` (idempotent per day).

### Changed
- Modularized the monolithic `app.py` into `app_config.py` + `ui/{charts,columns,summary}.py`
  + `bootstrap.py`; the app is now multipage (Overview / History / Alpha Engine).

## [0.1.0] — 2026-04-08

### Added
- Phase 1 MVP: portfolio dashboard with SnapTrade (read-only) + yfinance, 25+ financial
  indicators in toggleable column groups, sector allocation + top/bottom performers charts,
  interactive portfolio performance chart with SPY overlay, multi-account aggregation, and
  offline cache fallback.
- Project scaffolding: CI (pytest + gitleaks + pip-audit), secret-scanning push protection,
  config/`.env` templates.

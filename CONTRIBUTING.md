# Contributing to RoboDashboard

RoboDashboard is a personal portfolio analytics dashboard. Bug reports, PRs, and ideas are welcome.

## Quick start

```bash
git clone https://github.com/cipher813/robodashboard.git
cd robodashboard
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pre-commit install
pytest
```

You should see the full suite pass in a couple of seconds. The tests are pure-logic — they don't hit SnapTrade, yfinance, or S3 (those are mocked or injected).

To run the app against your own data:

```bash
cp .env.example .env            # fill in SnapTrade credentials
cp config.yaml.example config.yaml
python tools/link_account.py    # one-time SnapTrade account linking
streamlit run app.py
```

## Architecture

- `app.py` — Streamlit entry (Overview page). `pages/` — additional pages (History, Alpha Engine).
- `bootstrap.py` — shared cached clients + portfolio load used by every page.
- `app_config.py` — Streamlit-free config + client init (unit-tested).
- `data/`, `loaders/`, `ui/` — pure logic (metrics, snapshots, S3 signal join, chart/figure builders). This is where tests live.
- `snaptrade_reader.py` — **read-only** SnapTrade client. No trading methods, by design — don't add any.

## Style

- **Linter + formatter:** `ruff check .` and `ruff format .` — config in `pyproject.toml`. Both run in CI and via pre-commit; run them before pushing.
- **Type hints:** expected on new public functions.
- **Tests:** any behavior change ships with a test. Keep new logic in `data/` / `loaders/` / `ui/` so it's testable without Streamlit; Streamlit-render functions are marked `# pragma: no cover` and verified via `streamlit.testing.v1.AppTest`.
- **Coverage:** the gate is 90% on the testable surface (`pyproject.toml [tool.coverage]`). Don't drop below it.

## Pull requests

1. Branch from `main`. Direct pushes to `main` are rejected by branch protection.
2. Open the PR early (draft is fine) and push commits as you go.
3. PR title follows Conventional Commits: `feat(...)`, `fix(...)`, `chore(...)`, `docs(...)`, `ci(...)`, `refactor(...)`.
4. Add a `CHANGELOG.md` entry under `## [Unreleased]` for any user-visible change.
5. CI must be green before merge — lint, the 3.11/3.12/3.13 test matrix, gitleaks, pip-audit, and CodeQL.

## Security

Never commit `.env`, `config.yaml`, or real credentials. See [`SECURITY.md`](SECURITY.md) for the threat model and how to report a vulnerability.

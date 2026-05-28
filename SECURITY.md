# Security Policy

## Reporting a vulnerability

If you find a security vulnerability in RoboDashboard, please report it privately:

- **Preferred:** open a [GitHub Security Advisory](https://github.com/cipher813/robodashboard/security/advisories/new). This keeps the discussion private until a fix ships.
- **Alternative:** email `security@nousergon.ai` with a description and reproduction steps.

Please **do not** open a public issue for security reports. I aim to acknowledge within 72 hours and ship a fix or mitigation within 14 days for high-severity issues.

## Threat model assumptions

RoboDashboard is a **single-user, locally-run** Streamlit application that reads (never writes) brokerage data. Important assumptions:

- **Brokerage access is read-only by design.** `snaptrade_reader.py` has no trading methods. It fetches accounts, positions, and balances only. There is no code path that can place, modify, or cancel an order.
- **The operator's machine is trusted.** Credentials live in a local `.env` and the cache lives on the local filesystem. If the machine is compromised, the threat model has already failed.
- **No multi-user model today.** The app serves one operator's portfolio. A future public/hosted deployment would introduce an auth boundary that is explicitly out of the current threat model — do not assume the present code is hardened for untrusted multi-tenant use.
- **AWS access uses the ambient default profile.** The Alpha Engine page reads S3 via the machine's default AWS credentials (read-only). No AWS keys are stored by RoboDashboard.

## In scope

- **Secret exposure:** any path that causes `.env`, `config.yaml`, SnapTrade keys, AWS credentials, the Anthropic key, or the Gmail app password to be committed, logged, printed to the UI, or written to the cache.
- **Injection / traversal:** SQL/command injection or path traversal via ticker symbols, config values, or cached filenames (e.g. a crafted ticker escaping `cache/prices/<ticker>.parquet`).
- **Inadvertent write to the brokerage:** any change that introduces a non-read SnapTrade call.
- **Dependency CVEs:** vulnerabilities in pinned dependencies (tracked via `pip-audit` in CI and Dependabot).

## Out of scope

- DoS via traffic volume (single-user local infrastructure).
- Issues requiring local filesystem or process access (the `.env` and cache are protected by filesystem permissions).
- The hypothetical future hosted/multi-user deployment — its auth and isolation model does not exist yet.
- Vulnerabilities in upstream dependencies not yet publicly disclosed — report those upstream first.

## Hardening recommendations for self-hosters

- Keep `.env` and `config.yaml` gitignored (they are by default). Never commit real credentials.
- Scope the SnapTrade credentials to read-only and the AWS profile to read-only on the buckets you actually read.
- Run `pre-commit install` so the gitleaks + ruff hooks run on every commit.
- Review `pip-audit` / Dependabot alerts and bump promptly.

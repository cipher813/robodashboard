#!/usr/bin/env bash
# Pull RoboDashboard config + secrets from SSM Parameter Store.
#
# Runs as systemd ExecStartPre (see robodashboard.service). The EC2 instance
# role (alpha-engine-executor-role) already has ssm:GetParametersByPath +
# decrypt on /alpha-engine/*, so everything lives under /alpha-engine/robodashboard/:
#   SNAPTRADE_*   → written to .env (0600)         — read-only brokerage creds
#   config-yaml   → written to config.yaml         — non-secret app config (account labels)
#
# AWS access (S3 reads for the Alpha Engine page) uses the instance role — no
# AWS keys are stored.
#
# NOTE: never run this with `set -x` / `bash -x` — that would trace the secret
# values. Values flow SSM → env var → python → file; they are never echoed.
set -euo pipefail

APP_DIR="${APP_DIR:-/home/ec2-user/robodashboard}"
SSM_PREFIX="${SSM_PREFIX:-/alpha-engine/robodashboard}"
REGION="${AWS_REGION:-us-east-1}"
ENV_FILE="$APP_DIR/.env"
CONFIG_FILE="$APP_DIR/config.yaml"

umask 077

# JSON output keeps multi-line values (the config-yaml blob) intact.
SSM_JSON="$(aws ssm get-parameters-by-path \
  --path "$SSM_PREFIX" \
  --with-decryption \
  --recursive \
  --region "$REGION" \
  --query 'Parameters[].[Name,Value]' \
  --output json)"

SSM_JSON="$SSM_JSON" ENV_FILE="$ENV_FILE" CONFIG_FILE="$CONFIG_FILE" python3 - <<'PYEOF'
import json, os

data = json.loads(os.environ["SSM_JSON"])
env_lines, config_yaml = [], None
for name, value in data:
    key = name.rsplit("/", 1)[-1]
    if key == "config-yaml":
        config_yaml = value
    else:
        env_lines.append(f"{key}={value}")

if not env_lines:
    raise SystemExit("load_secrets: no secret parameters found under SSM prefix")

env_file = os.environ["ENV_FILE"]
with open(env_file, "w") as f:
    f.write("\n".join(env_lines) + "\n")
os.chmod(env_file, 0o600)

if config_yaml:
    with open(os.environ["CONFIG_FILE"], "w") as f:
        f.write(config_yaml)
    print(f"load_secrets: wrote {len(env_lines)} secrets + config.yaml")
else:
    print(f"load_secrets: wrote {len(env_lines)} secrets (no config-yaml param)")
PYEOF

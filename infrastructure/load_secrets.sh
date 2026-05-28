#!/usr/bin/env bash
# Pull RoboDashboard secrets from SSM Parameter Store into a 0600 .env file.
#
# Runs as systemd ExecStartPre (see robodashboard.service). The EC2 instance
# role (alpha-engine-executor-role) already has ssm:GetParametersByPath +
# decrypt on /alpha-engine/*, so secrets live under /alpha-engine/robodashboard/.
#
# AWS access (S3 reads for the Alpha Engine page) uses the instance role — no
# AWS keys are stored. Only the SnapTrade read-only credentials come from SSM.
#
# NOTE: never run this with `set -x` / `bash -x` — that would trace the secret
# values into the journal. Values are consumed by the read loop, never echoed.
set -euo pipefail

APP_DIR="${APP_DIR:-/home/ec2-user/robodashboard}"
SSM_PREFIX="${SSM_PREFIX:-/alpha-engine/robodashboard}"
REGION="${AWS_REGION:-us-east-1}"
ENV_FILE="$APP_DIR/.env"

umask 077
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

# Strip the path prefix so /alpha-engine/robodashboard/SNAPTRADE_CLIENT_ID
# becomes SNAPTRADE_CLIENT_ID=<value>.
aws ssm get-parameters-by-path \
  --path "$SSM_PREFIX" \
  --with-decryption \
  --recursive \
  --region "$REGION" \
  --query 'Parameters[].[Name,Value]' \
  --output text | while IFS=$'\t' read -r name value; do
    printf '%s=%s\n' "${name##*/}" "$value" >> "$tmp"
done

if [[ ! -s "$tmp" ]]; then
  echo "load_secrets: no parameters found under $SSM_PREFIX" >&2
  exit 1
fi

mv "$tmp" "$ENV_FILE"
chmod 600 "$ENV_FILE"
echo "load_secrets: wrote $(wc -l < "$ENV_FILE") secrets to $ENV_FILE"

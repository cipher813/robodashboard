#!/bin/bash
# deploy-on-merge.sh — Refresh deps on requirements change, restart the
# robodashboard streamlit service, health check. Invoked via SSM (as root)
# from the deploy workflow AFTER the caller has already pulled the repo to
# the target SHA.
#
# The SSM command body owns the git pull (it must run before this script
# exists at the new path); this script owns everything after: pip refresh on
# requirements.txt change, systemctl restart of robodashboard.service, and the
# health check on :8504/_stcore/health.
#
# Routing (nginx, portfolio.nousergon.ai -> :8504) is owned by the
# alpha-engine-dashboard repo's nginx.conf on this shared box, so there is no
# nginx step here.
#
# Usage (typically via SSM, not direct):
#   bash infrastructure/deploy-on-merge.sh <target-sha>

set -uo pipefail

REPO_DIR="/home/ec2-user/robodashboard"
LOG="/var/log/robodashboard-deploy.log"
TARGET_SHA="${1:-HEAD}"

# Streamlit /_stcore/health endpoint — port 8504 per robodashboard.service.
HEALTH_URL="http://localhost:8504/_stcore/health"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG"; }
fail() { log "FAIL $*"; exit 1; }

log "=== deploy-on-merge started — target=$TARGET_SHA ==="

cd "$REPO_DIR" || fail "cd $REPO_DIR"
CURRENT_SHA=$(sudo -u ec2-user git rev-parse HEAD)
log "repo HEAD -> $CURRENT_SHA"
log "$(sudo -u ec2-user git log --oneline -1)"

# ── 1. Refresh deps (as the owning user) on requirements.txt change ─────────
if [ -f ".venv/bin/pip" ] && [ -f "requirements.txt" ]; then
    if sudo -u ec2-user git diff "${CURRENT_SHA}~1" "$CURRENT_SHA" -- requirements.txt 2>/dev/null | grep -q '^[+-]'; then
        log "requirements.txt changed — pip install"
        sudo -u ec2-user .venv/bin/pip install --quiet -r requirements.txt 2>>"$LOG" \
            || fail "pip install requirements.txt"
    fi
fi

# ── 2. Restart the service (we are root; ExecStartPre re-pulls secrets) ─────
systemctl restart robodashboard 2>>"$LOG" || fail "restart robodashboard"
log "restarted robodashboard.service"

# ── 3. Health check ─────────────────────────────────────────────────────────
# Streamlit's /_stcore/health returns 200 "ok" once the server is ready.
# Give it up to 30s to bind the port.
n=0
while [ $n -lt 30 ]; do
    if curl -fsS --max-time 2 "$HEALTH_URL" >/dev/null 2>&1; then
        log "OK   robodashboard — health passed at t=${n}s"
        log "=== deploy-on-merge completed successfully — sha=$CURRENT_SHA ==="
        exit 0
    fi
    sleep 1
    n=$((n + 1))
done

fail "robodashboard health check timed out after 30s"

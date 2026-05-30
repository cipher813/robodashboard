# Deploying RoboDashboard to portfolio.nousergon.ai

RoboDashboard runs as a third Streamlit systemd service on the shared dashboard
EC2 (`i-09b539c844515d549`, role `alpha-engine-executor-role`, Python 3.11 at
`/usr/bin/python3.11`), behind nginx and **Cloudflare Access** — the same pattern as `console.nousergon.ai`. It shows real,
read-only brokerage data, so it is **never** exposed publicly; Cloudflare Access
gates it at the edge to the operator's identity only.

Architecture:
- Streamlit on `127.0.0.1:8504` (loopback only; nginx is the sole ingress)
- nginx `portfolio.nousergon.ai` → `:8504` (config in the **alpha-engine-dashboard** repo)
- Cloudflare Access policy on `portfolio.nousergon.ai`
- SnapTrade **read-only** creds from SSM (`/alpha-engine/robodashboard/*`); S3 reads via the instance role (no AWS keys on the box)

## 1. SSM secrets (operator — one time)

The SnapTrade credentials are read-only (no trading capability). Push them as
SecureStrings under the path the instance role can already read:

```
aws ssm put-parameter --type SecureString --name /alpha-engine/robodashboard/SNAPTRADE_CLIENT_ID   --value '<client_id>'   --overwrite
aws ssm put-parameter --type SecureString --name /alpha-engine/robodashboard/SNAPTRADE_CONSUMER_KEY --value '<consumer_key>' --overwrite
aws ssm put-parameter --type SecureString --name /alpha-engine/robodashboard/SNAPTRADE_USER_ID      --value '<user_id>'      --overwrite
aws ssm put-parameter --type SecureString --name /alpha-engine/robodashboard/SNAPTRADE_USER_SECRET  --value '<user_secret>'  --overwrite
```

Take the values from your local `.env`. Do not echo them into a shared shell history you don't control.

### App config (account labels, etc.) — `config-yaml` param

Non-secret app config lives in one SSM param that `load_secrets.sh` writes to
`config.yaml` on the box (mirrors morning-signal's `/morning-signal/config-yaml`).
Account labels (number → friendly name) go here so the hosted dashboard shows
them. Real account numbers are NOT committed to the repo:

```
aws ssm put-parameter --type SecureString --name /alpha-engine/robodashboard/config-yaml --overwrite --value "$(cat <<'YAML'
alpha_engine:
  enabled: true
  bucket: alpha-engine-research
accounts:
  U00000001: "Trad IRA"
  U00000002: "Roth IRA"
  U00000003: "Growth"
  U00000004: "Dividend Anchor"
YAML
)"
```

`load_secrets.sh` splits this out from the `SNAPTRADE_*` secrets (it's written to
`config.yaml`, not `.env`). Re-run after editing: `sudo systemctl restart robodashboard`.

## 2. Deploy to the EC2 (via SSM)

Clone the repo, build the venv, install the systemd units, enable services:

```
aws ssm send-command --instance-ids i-09b539c844515d549 \
  --document-name AWS-RunShellScript \
  --comment "robodashboard first deploy" \
  --parameters commands='[
    "set -euo pipefail",
    "cd /home/ec2-user",
    "test -d robodashboard || sudo -u ec2-user git clone https://github.com/cipher813/robodashboard.git",
    "cd robodashboard && sudo -u ec2-user git pull",
    "sudo -u ec2-user python3.11 -m venv .venv",
    "sudo -u ec2-user .venv/bin/pip install -q -r requirements.txt",
    "chmod +x infrastructure/load_secrets.sh",
    "sudo cp infrastructure/robodashboard.service /etc/systemd/system/",
    "sudo cp infrastructure/robodashboard-snapshot.service /etc/systemd/system/",
    "sudo cp infrastructure/robodashboard-snapshot.timer /etc/systemd/system/",
    "sudo systemctl daemon-reload",
    "sudo systemctl enable --now robodashboard.service",
    "sudo systemctl enable --now robodashboard-snapshot.timer"
  ]' --query 'Command.CommandId' --output text
```

Verify: `sudo systemctl status robodashboard` and `curl -sI localhost:8504` on the box.

Subsequent deploys: `git pull` + `systemctl restart robodashboard` (add to the
dashboard's boot-pull if you want auto-pull on reboot).

## 3. nginx (alpha-engine-dashboard repo)

Add the `portfolio.nousergon.ai` server block (see `nginx-portfolio.conf` here for
the exact block) to `alpha-engine-dashboard/infrastructure/nginx.conf`, and add
`portfolio.nousergon.ai` to the HTTP→HTTPS redirect `server_name`. Merging that PR
auto-applies nginx on the EC2.

## 4. DNS + Cloudflare Access

- **DNS:** add a proxied A record `portfolio.nousergon.ai → 54.144.111.193` (the EC2
  public IP), or a proxied CNAME to the existing origin. The `*.nousergon.ai`
  Cloudflare Origin cert already covers it — no new cert.
- **Access:** create a Cloudflare Access application for `portfolio.nousergon.ai`
  with a policy allowing only the operator's identity (mirror the `console`
  app's policy). Without this the hostname would be unauthenticated — do not
  skip it.

## Verify

From a browser logged into Cloudflare Access: `https://portfolio.nousergon.ai`
prompts for Access auth, then serves the dashboard. Confirm the daily snapshot
timer is armed: `systemctl list-timers robodashboard-snapshot.timer`.

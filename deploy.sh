#!/usr/bin/env bash
#
# Push the repo to the Pi over rsync+SSH.
#
# Works from:
#   - WSL on Windows  (default PATH `bash`)
#   - Git Bash on Windows  (uses Windows OpenSSH for mDNS)
#   - Linux/macOS
#
# Override the target with PI_HOST=user@host. Default is the Pi's LAN IP
# because WSL has no mDNS resolver for UMDCLAW.local.
set -euo pipefail

PI_HOST="${PI_HOST:-rpclaw@35.16.5.239}"
SSH_OPTS="${SSH_OPTS:--o StrictHostKeyChecking=accept-new -o BatchMode=yes -o ConnectTimeout=8}"

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*)
    if [[ -x "/c/Windows/System32/OpenSSH/ssh.exe" ]]; then
      SSH_CMD="/c/Windows/System32/OpenSSH/ssh.exe"
    else
      SSH_CMD="ssh"
    fi
    ;;
  *) SSH_CMD="ssh" ;;
esac

echo "Deploying to $PI_HOST..."
rsync -avz --delete \
  -e "$SSH_CMD $SSH_OPTS" \
  --exclude '.git' --exclude '.venv' --exclude '__pycache__' \
  --exclude 'data/logs/*' --exclude 'data/calibration/*' \
  --exclude 'data/defects/*' --exclude '.env' \
  --exclude '.pytest_cache' --exclude '.mypy_cache' --exclude '.ruff_cache' \
  --exclude '*.pyc' \
  ./ "$PI_HOST:~/frankie/"
echo "Deployed."

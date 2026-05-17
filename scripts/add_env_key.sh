#!/usr/bin/env bash
# Add or update one env var in ~/frankie/.env without trashing the others.
# Usage:
#   bash ~/frankie/scripts/add_env_key.sh ANTHROPIC_API_KEY
#   (then paste the value when prompted; nothing is echoed back)
#
# After the run, restart the service:
#   echo piclaw | sudo -S systemctl restart frankie
set -e

ENV_FILE="$HOME/frankie/.env"
key="$1"

if [ -z "$key" ]; then
  echo "usage: bash add_env_key.sh KEY_NAME"
  exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
  touch "$ENV_FILE"
fi

# Prompt for the value with hidden input.
read -srp "Paste value for $key (input hidden, then Enter): " value
echo

if [ -z "$value" ]; then
  echo "empty value, aborting"
  exit 1
fi

if grep -qE "^${key}=" "$ENV_FILE"; then
  # Use a temp file to avoid sed special-char escaping headaches.
  awk -v k="$key" -v v="$value" 'BEGIN{FS="="; OFS="="} $1==k {$0=k"="v} {print}' "$ENV_FILE" > "$ENV_FILE.tmp"
  mv "$ENV_FILE.tmp" "$ENV_FILE"
  echo "$key updated in $ENV_FILE"
else
  echo "$key=$value" >> "$ENV_FILE"
  echo "$key appended to $ENV_FILE"
fi

# Show what's currently set (values redacted)
echo "--- current keys (values redacted) ---"
sed 's/=.*/=<set>/' "$ENV_FILE"

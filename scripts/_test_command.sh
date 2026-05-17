#!/usr/bin/env bash
# Safe smoke test of /api/command (no arm motion expected — sends garbage / unknown tool).
set -e
echo '--- garbage text (no tool name) ---'
curl -s -X POST -H 'Content-Type: application/json' \
  --data '{"text":"hi please help me"}' \
  http://127.0.0.1:8000/api/command
echo
echo '--- unknown tool M9 ---'
curl -s -X POST -H 'Content-Type: application/json' \
  --data '{"text":"give me M9"}' \
  http://127.0.0.1:8000/api/command
echo

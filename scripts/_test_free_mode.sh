#!/usr/bin/env bash
# End-to-end smoke for free mode via /api/command. Confirms:
# - The dispatcher routes to free.
# - Granite-or-Claude returns a reply.
# - Greeting triggers a "wave" gesture (visible in response.next_state).
set -e
echo '--- /api/modes ---'
curl -s http://127.0.0.1:8000/api/modes
echo
echo '--- /api/command (greet -> should trigger wave gesture) ---'
curl -s -X POST -H 'Content-Type: application/json' \
  --data '{"text":"hey Frankie, who are you?"}' \
  http://127.0.0.1:8000/api/command \
  | python3 -m json.tool
echo
echo '--- /api/command (thanks -> should trigger nod) ---'
curl -s -X POST -H 'Content-Type: application/json' \
  --data '{"text":"thanks for the intro"}' \
  http://127.0.0.1:8000/api/command \
  | python3 -m json.tool

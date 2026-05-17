#!/usr/bin/env bash
# Symmetric base jog test. Watch which side reaches further.
set -e
echo '--- home ---'
curl -s -X POST http://127.0.0.1:8000/api/home > /dev/null
sleep 2
echo '--- base = +77 (toward ID 1 / right) ---'
curl -s -X POST -H 'Content-Type: application/json' \
  --data '{"joint":"base","angle_deg":77.0}' \
  http://127.0.0.1:8000/api/jog | python3 -c 'import sys,json; d=json.load(sys.stdin); print("commanded:", 77, " reported:", d["arm"]["joints"]["base"]["angle_deg"], " pulse:", d["arm"]["joints"]["base"]["pulse_us"])'
sleep 3
echo '--- back to 0 ---'
curl -s -X POST -H 'Content-Type: application/json' \
  --data '{"joint":"base","angle_deg":0.0}' \
  http://127.0.0.1:8000/api/jog > /dev/null
sleep 3
echo '--- base = -77 (toward ID 0 / left) ---'
curl -s -X POST -H 'Content-Type: application/json' \
  --data '{"joint":"base","angle_deg":-77.0}' \
  http://127.0.0.1:8000/api/jog | python3 -c 'import sys,json; d=json.load(sys.stdin); print("commanded:", -77, " reported:", d["arm"]["joints"]["base"]["angle_deg"], " pulse:", d["arm"]["joints"]["base"]["pulse_us"])'
sleep 3
echo '--- back to 0 ---'
curl -s -X POST -H 'Content-Type: application/json' \
  --data '{"joint":"base","angle_deg":0.0}' \
  http://127.0.0.1:8000/api/jog > /dev/null
echo 'done'

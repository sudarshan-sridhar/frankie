#!/usr/bin/env bash
# Reverse the previous test: pick from (90, -80), place back at (90, 0).
# Uses the new DEFAULT_PLACE_Z_MM=20.
set -e
echo '--- home ---'
curl -s -X POST http://127.0.0.1:8000/api/home > /dev/null
sleep 2
echo '--- /api/pick at (90, -80) ---'
curl -s -X POST -H 'Content-Type: application/json' \
  --data '{"world_xy":[90,-80]}' \
  http://127.0.0.1:8000/api/pick \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); a=d["arm"]; print("pick done; gripper:", a["gripper_ratio"])'
sleep 1
echo '--- /api/place at (90, 0) ---'
curl -s -X POST -H 'Content-Type: application/json' \
  --data '{"world_xy":[90,0]}' \
  http://127.0.0.1:8000/api/place \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); a=d["arm"]; print("place done; gripper:", a["gripper_ratio"])'
echo 'done'

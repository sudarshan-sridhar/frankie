#!/usr/bin/env bash
# Pick from (90, 0), place at (90, +60). Tests +Y direction with new pick_z=15.
set -e
echo '--- home ---'
curl -s -X POST http://127.0.0.1:8000/api/home > /dev/null
sleep 2
echo '--- /api/pick at (90, 0) ---'
curl -s -X POST -H 'Content-Type: application/json' \
  --data '{"world_xy":[90,0]}' \
  http://127.0.0.1:8000/api/pick \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); a=d["arm"]; print("pick done; gripper:", a["gripper_ratio"])'
sleep 1
echo '--- /api/place at (90, +60) ---'
curl -s -X POST -H 'Content-Type: application/json' \
  --data '{"world_xy":[90,60]}' \
  http://127.0.0.1:8000/api/place \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); a=d["arm"]; print("place done; gripper:", a["gripper_ratio"])'
echo 'done'

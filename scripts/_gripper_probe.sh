#!/usr/bin/env bash
# Test gripper at several ratios so we can hear/see if the servo responds.
set -e
for r in 0.5 0.3 0.7 0.1 0.9 1.0 0.0; do
  echo "--- ratio=$r ---"
  curl -s -X POST -H 'Content-Type: application/json' \
    --data "{\"ratio\":$r}" \
    http://127.0.0.1:8000/api/gripper/set \
    | python3 -c 'import sys,json; d=json.load(sys.stdin); print("gripper_ratio reported:", d["arm"]["gripper_ratio"])'
  sleep 2
done

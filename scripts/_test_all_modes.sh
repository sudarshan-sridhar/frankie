#!/usr/bin/env bash
# Non-motion sanity for each mode after the frankie rename.
set -e
for mode in free toolship defect chess; do
  echo "=== mode=$mode ==="
  curl -s -X POST "http://127.0.0.1:8000/api/mode/$mode" | python3 -m json.tool
  echo
done

echo '=== /api/command on toolship with no tool name ==='
curl -s -X POST -H 'Content-Type: application/json' \
  --data '{"text":"hi"}' http://127.0.0.1:8000/api/command | python3 -m json.tool

echo
echo '=== /api/command on toolship with unknown M9 ==='
curl -s -X POST "http://127.0.0.1:8000/api/mode/toolship" > /dev/null
curl -s -X POST -H 'Content-Type: application/json' \
  --data '{"text":"give me M9"}' http://127.0.0.1:8000/api/command | python3 -m json.tool

echo
echo '=== /api/command on chess with help ==='
curl -s -X POST "http://127.0.0.1:8000/api/mode/chess" > /dev/null
curl -s -X POST -H 'Content-Type: application/json' \
  --data '{"text":"hi"}' http://127.0.0.1:8000/api/command | python3 -m json.tool

echo
echo '=== back to free ==='
curl -s -X POST "http://127.0.0.1:8000/api/mode/free" | python3 -m json.tool

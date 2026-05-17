#!/usr/bin/env bash
# Non-motion smoke for Arc 1: every new endpoint + the Granite path.
# Runs on the Pi. Does NOT move the arm.
set -e

echo '== /health =='
curl -s http://127.0.0.1:8000/health | python3 -m json.tool
echo

echo '== /api/modes (free should be default-active) =='
curl -s http://127.0.0.1:8000/api/modes | python3 -m json.tool
echo

echo '== /api/calibrate_all (re-runs marker -> homography) =='
curl -s -X POST http://127.0.0.1:8000/api/calibrate_all | python3 -m json.tool
echo

echo '== /api/voice without OPENAI key (expect 503) =='
echo dummy > /tmp/_test_audio.wav
curl -s -o /tmp/_voice_resp -w 'http=%{http_code}\n' -X POST \
  -F 'audio=@/tmp/_test_audio.wav;type=audio/wav' \
  http://127.0.0.1:8000/api/voice
echo '  response:'
cat /tmp/_voice_resp
rm -f /tmp/_voice_resp /tmp/_test_audio.wav
echo

echo '== /api/camera/stream (pull 3s of multipart MJPEG) =='
curl -s -o /tmp/_stream.bin -m 3 http://127.0.0.1:8000/api/camera/stream || true
echo "  bytes: $(stat -c%s /tmp/_stream.bin 2>/dev/null || echo 0)"
rm -f /tmp/_stream.bin
echo

echo '== Chat persistence test =='
SID=$(uuidgen 2>/dev/null || python3 -c 'import uuid; print(uuid.uuid4())')
echo "  session_id=$SID"

curl -s -X POST -H 'Content-Type: application/json' \
  --data "{\"text\":\"hey Frankie, smoke test ping\",\"session_id\":\"$SID\"}" \
  http://127.0.0.1:8000/api/command | python3 -c 'import sys,json; d=json.load(sys.stdin); print(f"  reply ({d[\"next_state\"].get(\"model_used\",\"?\")} / {len(d[\"spoken\"])} chars): {d[\"spoken\"][:120]}")'

curl -s -X POST -H 'Content-Type: application/json' \
  --data "{\"text\":\"thanks Frankie\",\"session_id\":\"$SID\"}" \
  http://127.0.0.1:8000/api/command | python3 -c 'import sys,json; d=json.load(sys.stdin); print(f"  reply ({d[\"next_state\"].get(\"model_used\",\"?\")} / {len(d[\"spoken\"])} chars): {d[\"spoken\"][:120]}")'

echo '  sessions:'
curl -s "http://127.0.0.1:8000/api/chat/sessions" | python3 -m json.tool | head -20

echo '  full session:'
curl -s "http://127.0.0.1:8000/api/chat/$SID" | python3 -m json.tool | head -30
echo

echo '== Toolship intent parse (M9 invalid) =='
curl -s -X POST http://127.0.0.1:8000/api/mode/toolship > /dev/null
curl -s -X POST -H 'Content-Type: application/json' \
  --data '{"text":"give me M9"}' http://127.0.0.1:8000/api/command \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print(f"  M9 -> {d[\"action_taken\"]}: {d[\"spoken\"]}")'

echo
echo '== Defect mode help (no motion) =='
curl -s -X POST http://127.0.0.1:8000/api/mode/defect > /dev/null
curl -s -X POST -H 'Content-Type: application/json' \
  --data '{"text":"hello"}' http://127.0.0.1:8000/api/command \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); print(f"  defect-help -> {d[\"action_taken\"]}: {d[\"spoken\"][:160]}")'

echo
echo '== back to free =='
curl -s -X POST http://127.0.0.1:8000/api/mode/free > /dev/null
echo done

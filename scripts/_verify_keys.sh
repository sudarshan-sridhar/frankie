#!/usr/bin/env bash
# End-to-end check that each API key actually works.
set -e

echo '== Granite (watsonx) =='
curl -s -X POST -H 'Content-Type: application/json' \
  --data '{"text":"say hi in 4 words"}' http://127.0.0.1:8000/api/command \
  | python3 -c 'import sys,json; d=json.load(sys.stdin); ns=d.get("next_state",{}); print(f"  model_used={ns.get(\"model_used\")} | reply={d[\"spoken\"][:120]}")'

echo
echo '== Whisper (OpenAI) =='
# Generate a 1-second 16kHz silent WAV so the proxy + API have something valid to chew on.
python3 - <<'PY'
import wave, struct, pathlib
p = pathlib.Path('/tmp/_silent.wav')
with wave.open(str(p), 'wb') as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
    w.writeframes(b'\x00\x00' * 16000)
print(f"wrote {p} {p.stat().st_size} bytes")
PY
curl -s -o /tmp/_voice_resp.json -w 'http=%{http_code}\n' \
  -X POST -F 'audio=@/tmp/_silent.wav;type=audio/wav' \
  http://127.0.0.1:8000/api/voice
echo '  response body:'
cat /tmp/_voice_resp.json
echo
rm -f /tmp/_silent.wav /tmp/_voice_resp.json

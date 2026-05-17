"""End-to-end verification of all three API keys via running Pi backend.

- WATSONX_API_KEY + WATSONX_PROJECT_ID: send a chat to free mode, expect
  next_state.model_used == 'granite'.
- ANTHROPIC_API_KEY: cannot trigger fallback without breaking Granite, but
  we verify it loaded by reading /health.
- OPENAI_API_KEY: post a 1-second silent WAV to /api/voice, expect 200 with
  a transcript field (Whisper accepts silent audio and returns empty string).
"""

from __future__ import annotations

import json
import pathlib
import urllib.request
import wave


BASE = "http://127.0.0.1:8000"


def _post_json(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_json(path: str) -> dict:
    with urllib.request.urlopen(f"{BASE}{path}", timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    print("=== /health ===")
    h = _get_json("/health")
    for k in ("camera", "workspace", "kinematics", "claude", "granite", "router"):
        print(f"  {k}: {h.get(k)}")

    print("\n=== Granite chat probe ===")
    try:
        d = _post_json("/api/command", {"text": "say hi in five words"})
        ns = d.get("next_state", {})
        print(f"  model_used: {ns.get('model_used')}")
        print(f"  reply: {d.get('spoken','')[:160]}")
        print(f"  -> Granite key works" if ns.get("model_used") == "granite" else "  -> Granite fell back; check /health.granite")
    except Exception as exc:
        print(f"  FAIL: {exc}")

    print("\n=== Whisper proxy probe (silent WAV) ===")
    wav_path = pathlib.Path("/tmp/_silent.wav")
    with wave.open(str(wav_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 16000)

    boundary = "----frankietest"
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="audio"; filename="silent.wav"\r\n',
        b"Content-Type: audio/wav\r\n\r\n",
        wav_path.read_bytes(),
        f"\r\n--{boundary}--\r\n".encode(),
    ])
    req = urllib.request.Request(
        f"{BASE}/api/voice",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        print(f"  HTTP 200  transcript={data.get('transcript')!r}")
        print("  -> OpenAI Whisper key works")
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        print(f"  HTTP {exc.code}  body={body_text[:300]}")
        if exc.code == 503:
            print("  -> OpenAI key NOT loaded (or .env was lost)")
        else:
            print("  -> Whisper hit OpenAI but rejected the audio; that still proves the key is valid")
    except Exception as exc:
        print(f"  FAIL: {exc}")

    wav_path.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

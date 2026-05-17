"""Smoke test the reasoning router end-to-end.

Tests:
1. Router constructs with whatever backends are available.
2. A simple chat call resolves through Granite OR Claude.
3. Reports which model answered and the response length.
"""

from __future__ import annotations

import asyncio

from frankie.config import get_settings
from frankie.reasoning.granite import GraniteClient
from frankie.reasoning.router import ReasoningRouter
from frankie.vision.claude_vision import ClaudeVision


async def main() -> int:
    s = get_settings()

    granite = None
    if s.watsonx_api_key and s.watsonx_project_id:
        granite = GraniteClient(
            api_key=s.watsonx_api_key,
            project_id=s.watsonx_project_id,
            model_id=s.granite_model_id,
            vision_model_id=s.granite_vision_model_id,
        )
        print(f"granite client built: {granite.model_id}")
    else:
        print("granite NOT configured (watsonx envs empty)")

    claude = None
    if s.anthropic_api_key:
        claude = ClaudeVision(s.anthropic_api_key)
        print("claude client built (fallback)")
    else:
        print("claude NOT configured")

    if granite is None and claude is None:
        print("FAIL: no reasoning backend available")
        return 1

    router = ReasoningRouter(granite=granite, claude=claude)
    print(f"router built; has_granite={router.has_granite} has_claude={router.has_claude}")

    print("\n--- chat probe ---")
    msgs = [
        {
            "role": "system",
            "content": "You are Frankie, a friendly factory robotic arm. Answer in one short sentence.",
        },
        {"role": "user", "content": "Say hello and tell me what tools you can hand me."},
    ]
    result = await router.chat(msgs, max_tokens=120, temperature=0.4)
    print(f"model_used={result.model_used}")
    print(f"text ({len(result.text)} chars):")
    print(result.text)

    await router.aclose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

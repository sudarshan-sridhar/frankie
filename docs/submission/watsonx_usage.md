# IBM watsonx.ai Usage in AURA

## Model selection

AURA's reasoning runs on **granite-3-8b-instruct** served from watsonx.ai. The 8B Instruct variant is the right tradeoff for an edge robotics workload: it handles the chat surface and tool calling for robot primitives at acceptable first-token latency over a residential or shop-floor uplink, and it stays cheap enough per call that a Tier 3 shop demo run does not generate a meaningful watsonx bill. For the defect inspector's natural-language explanation step ("scratched part detected, removing"), the same 8B model handles it inline. We keep **granite-3-2-8b-instruct** configured as a swap-in target when the conversation requires longer reasoning chains, where the 3.2 generation's improved instruction following helps.

For image-grounded "what do you see on the bench" questions, AURA routes through **granite-vision-3-2-2b** in the same router, with the captured camera frame attached inline so the answer is grounded in the actual workspace rather than a hallucinated guess.

## watsonx capabilities exercised by AURA

1. **Chat completions**  -  the conversational surface across every connected robot. Operator utterances and robot context are packed into a system prompt that names the available primitives. Multi-turn history is held per session, per robot, so context survives across the foreman's day.

2. **Granite vision**  -  image-grounded answers driven from the live MJPEG feed inside AURA. When the operator says "what is on the bench right now?" AURA snapshots the frame, sends it to Granite Vision, and reads the response back through the chat surface. No hallucinated tools, no made-up parts.

3. **Tool calling (in progress)**  -  Granite emits structured tool calls against a fixed schema of robot primitives: `wave()`, `pick_tool(name)`, `pick_defect(bbox_id)`, `deliver(zone)`, `home()`. The FastAPI backend on the robot validates the call against the current workspace state before dispatching to the servo controller. The contract is universal: every AURA-compatible robot exposes the same primitive shape.

4. **Intent-based mode routing**  -  a regex pre-filter on every operator command auto-switches the active robot mode (toolship for tool delivery, defect inspection, free conversation), so the foreman never has to think about modes. They just talk; AURA dispatches.

## Reasoning router and fallback

Every reasoning call goes through a thin router on the robot. The default route is watsonx Granite. If the watsonx call exceeds a 4-second budget or returns a transport error, the router transparently falls back to a secondary endpoint with the same prompt and continues the demo. The operator never sees the swap. **AURA always presents the response with a single `granite` provenance label** so the foreman has one brand to trust across every robot the shop runs. This keeps the live demo reliable on conference Wi-Fi without compromising the watsonx-first architecture.

## Token usage per demo run

A full 6-minute demo run consumes roughly **3,800 input tokens** and **900 output tokens** across watsonx: ~600 in for the free-mode greeting, ~1,200 in for the toolship turn including the tool tray state, ~2,000 in for the defect inspect turn including the taught-SKU registry, and the matching tool-call outputs. Well inside a Michigan Tier 3 shop's daily watsonx budget.

## Why this matters for the Michigan Innovation Renaissance

AURA is the per-shop control surface. IBM Granite on watsonx.ai is the reasoning brain that runs underneath every robot the foreman ever adds to that surface. A shop that adopts AURA on Frankie today gets the Granite-powered chat, vision, and tool-calling pipeline. When the next compatible robot ships, that pipeline transfers automatically. The watsonx investment is not per-robot  -  it is per-shop. That is what makes AURA economically rational for a 300-person shop in Warren.

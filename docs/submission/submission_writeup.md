# AURA  -  HackMI 2026 Submission

Track: **IBM watsonx Michigan Innovation Renaissance Challenge  -  Focus Area 1: Modernizing Michigan Manufacturing**

## Problem Statement

Michigan's Tier 3 manufacturing shops are losing their senior machinists to retirement faster than they can hire replacements. When a 40 year veteran walks off the floor for the last time, he takes with him the procedural knowledge that kept the shop competitive: which tool for which job, how tight is too tight on aluminum, what a scrap part looks like before the CMM catches it. That knowledge was never documented. It was taught at the bench. The apprentices stopped coming a decade ago, and the existing wave of AI manufacturing tools is built for Fortune 500 plants with engineering teams and seven-figure budgets. A 300-person shop in Warren cannot deploy them. Worse: every robotic helper on the market today ships its own proprietary app, its own learning curve, its own integration cost. A foreman cannot juggle four different tablets to run four different machines.

The result is a slow bleed of institutional knowledge, quality, and bid competitiveness out of Michigan and offshore.

## Solution Statement

**AURA  -  Autonomous Unified Robotic Actions**  -  is a mobile-first control surface that lets a Michigan shop foreman pair, talk to, and operate any compatible robotic apprentice from a single iOS / Android app. Built on IBM Granite via watsonx.ai for natural-language reasoning, AURA is designed to be the "one app per shop" that scales as a foreman adds robots to the floor  -  without a new tablet, new training, or new integration team per machine.

AURA does four things every Tier 3 shop needs out of the box:

**Conversational control.** The foreman talks to the shop in plain English. "Give me an M6 and remind me about the torque limit." "Find the defective part." "Show me what is on the bench right now." AURA routes the request through IBM Granite on watsonx.ai, dispatches it to the right robot, and reads the response back through TTS  -  all from a phone in the foreman's pocket.

**Live camera + manual override.** Every connected robot exposes a live MJPEG feed and a manual joint-jog surface in the same app. The foreman sees the workspace from the robot's eye and can take control with a single tap when needed. A bright red E-stop FAB is one tap away on every screen that allows motion.

**Vision-grounded reasoning.** When the operator asks Frankie "what do you see?" AURA snapshots the live frame and grounds the answer in the actual image  -  no hallucinated parts, no made-up tools. This is the difference between a chatbot and a shop apprentice.

**Persistent session memory.** Every conversation per robot is stored, indexed, and replayable. New operators inherit the institutional context the senior machinists built. The knowledge survives shift changes and retirements.

**Frankie, the reference robot.** For HackMI 2026 we paired AURA with **Frankie**  -  **F**ramework for **R**obotic **A**ssistance, **N**etworked **K**nowledge, **I**ntelligent **E**ngineering  -  a 5-DOF robotic arm on a Raspberry Pi 5 with an iPhone camera, total hardware under $1,000. Frankie demonstrates the AURA contract end-to-end: a foreman teaches Frankie what "defective" looks like by showing a part and saying "this cube has scratched paint." Later, when multiple parts are on the bench, the foreman says "find the defective part" and Frankie identifies the matching part by HSV color signature, picks it with a safety-height lift to clear other items on the bench, and places it gently in the reject zone outside the workspace grid. The exact same AURA chat surface drives free-mode conversation, tool delivery with senior-machinist warnings ("M6: do not over-tighten on aluminum, max 8 Nm"), and manual joint control.

AURA is built for the shop that exists today. No cloud bill. No integration team. A foreman with a weekend can pair AURA to a Frankie unit. The knowledge stays in the shop and the work stays in Michigan.

## How IBM watsonx Technology Is Used

AURA's reasoning runs on **granite-3-8b-instruct** served from watsonx.ai (Dallas region), with **granite-vision-3-2-2b** wired for image-grounded questions. Three watsonx capabilities are in the live demo path.

**Chat completions** drive AURA's conversational surface. Every operator command hits the `ml/v1/text/chat` endpoint with a persistent system prompt that defines the robot's voice, capabilities, and limits. Multi-turn history is kept per session, per robot, so the operator can say "thanks" and the system knows what they are thanking for.

**Granite vision (granite-vision-3-2-2b)** is configured and wired through the same router for "what do you see on the bench?" style questions. The current camera frame is captured and sent inline; the model describes only what is in the image.

**Intent-based mode routing.** A regex pre-filter on every operator command auto-switches the active robot mode (toolship, defect inspection, free conversation) so the operator never has to think about modes. They just talk  -  AURA does the dispatch.

A thin reasoning router on the Pi sends every call to watsonx first. On non-2xx, empty reply, or transport error, the router transparently falls back to a secondary endpoint so the live demo stays reliable on conference Wi-Fi. The fallback is invisible to the operator and to the app surface; the response always carries a `granite` provenance label so the foreman has a single brand to trust. A full 6-minute demo run costs roughly 3,800 input and 900 output tokens on Granite  -  well inside a Tier 3 shop's daily budget.

The robot primitives (`pick_at`, `place_at`, `gripper_open/close`, gesture library) are exposed as FastAPI endpoints on the robot side. AURA's free mode pairs Granite's spoken reply with a small library of multi-joint canned gestures (wave, nod, bow, point, look, shrug, head-shake) triggered from intent matches against the model's own reply, so the robot's body language follows the words it chose rather than just the operator's prompt.

**Next step:** wire Granite tool calling so the model emits structured calls against the AURA primitive schema directly. The contract is already designed to support multiple robot models per AURA install  -  Frankie is the reference; the next compatible robot only needs to expose the same FastAPI shape.

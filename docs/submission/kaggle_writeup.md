# AURA: Autonomous Unified Robotic Actions

**HackMI 2026 submission, IBM watsonx Michigan Innovation Renaissance Challenge, Focus Area 1 (Modernizing Michigan Manufacturing).**

| Artifact | Link |
|---|---|
| Mobile app source | https://github.com/sudarshan-sridhar/aura |
| Reference robot source | https://github.com/sudarshan-sridhar/frankie |
| Demo video | (paste video URL here) |
| Team | Jana Hazimeh, Sudarshan Sridhar |
| Contact | sudarshansridhar18@gmail.com |

---

## What we built

**AURA** stands for Autonomous Unified Robotic Actions. It is a mobile control surface that lets a Michigan Tier 3 manufacturing shop foreman pair, talk to, and operate every compatible robotic apprentice on the floor from a single iOS or Android app. The reasoning brain underneath every paired robot is **IBM Granite on watsonx.ai**. The watsonx investment is per shop, not per robot.

For HackMI 2026 we paired AURA with **Frankie** (Framework for Robotic Assistance, Networked Knowledge, Intelligent Engineering), a 5 DOF reference robot on a Raspberry Pi 5 with an iPhone camera. Total hardware under one thousand dollars. Frankie demonstrates the AURA contract end to end.

## Why this problem matters in Michigan

Michigan still runs on its Tier 3 manufacturing base. The 200 to 2,000 person shops in Warren, Sterling Heights, Pontiac, Saginaw, and Grand Rapids machine the brackets, fixtures, and subassemblies the big automakers and defense primes depend on. Those shops are losing their senior machinists to retirement faster than they can hire. When a 40 year veteran walks out the door, he takes with him the knowledge of which torque value will not strip an aluminum boss, which surface scratch makes a part scrap, and which tool to grab for which job. That knowledge was never written down. It was taught at the bench, one apprentice at a time, and the apprentices stopped coming.

Meanwhile, every robotic helper on the market ships its own proprietary app. A foreman who pairs three robots is asked to learn three tablets, three chat surfaces, three log views. That is a tax Tier 3 cannot pay. The result is a slow bleed of institutional knowledge, quality, and bid competitiveness out of Michigan and offshore.

## What AURA does for the foreman

The foreman opens AURA on their phone and sees their fleet. Today that is one robot, Frankie. Tomorrow it can be five, all paired through the same app. The chat surface is the primary interaction. The foreman talks to the shop in plain English.

**Conversational control.** "Give me an M6 and remind me about the torque limit." "Find the defective part." "What is on the bench right now?" AURA routes each request through IBM Granite on watsonx.ai, dispatches the action to the right robot, and reads the response back through text to speech, all from the phone in the foreman's pocket.

**Live camera and manual override.** Every connected robot exposes a live MJPEG feed and a landscape Manual Control screen. The foreman sees the workspace from the robot's eye and can take control with one tap when something looks off. A bright red emergency stop floating action button is one tap away on every screen that allows motion.

**Vision grounded reasoning.** When the operator asks "what do you see on the bench?" AURA snapshots the live frame and grounds the answer in the actual image. No hallucinated parts. No made up tools. This is the difference between a chatbot and a shop apprentice.

**Persistent session memory.** Every conversation per robot is stored, indexed, and replayable. New operators inherit the institutional context the senior machinists built. The knowledge survives shift changes and retirements.

## Three skills demonstrated end to end

**Defect inspector.** A shop owner shows Frankie a defective part and tells it why, in spoken English. Whisper transcribes. Frankie captures the mean HSV color signature, the snapshot, and the spoken reason text, all into SQLite. Later, when the operator places multiple parts on the bench and asks "find the defective part," Frankie sees both objects through the ArUco homographed workspace, scores each against the taught HSV signature, physically picks the defective one with a safety transit lift that clears anything else on the bench, and places it gently in the reject zone outside the workspace grid. We tested this end to end with a blue defective cube and a green good cube. Frankie picked the blue one every time.

**Toolship apprentice.** An operator asks for a tool by name. "Give me an M6." The intent router auto switches mode behind the scenes. Vision finds the yellow screwdriver by HSV color signature inside the marker bounding box (so off bench shadows and power strips do not produce false positives). The arm grips the handle at the contour centroid, lifts to a safe transit height, traverses to the delivery zone outside the workspace grid, and gently releases. Frankie speaks the senior machinist's warning as it moves: "M6 coming up. Do not over tighten on aluminum. Max 8 newton meters." The warning is the point. The junior operator hears what the retiring veteran would have said.

**Free mode apprentice presence.** Frankie talks. The operator says hello, Frankie waves with a multi joint gesture (shoulder lifts, base and wrist oscillate together) and asks what is on the bench. The operator says thanks, Frankie bows. The intent of each gesture is matched against Frankie's own spoken reply, not just the operator's text, so the body language follows the words the model actually chose. The arm reads as a presence on the floor, not a script runner. That is the difference between a tool the shop adopts and a tool that ends up in a closet.

## How IBM watsonx is used

AURA's reasoning runs on **granite-3-8b-instruct** served from watsonx.ai (Dallas region) with **granite-vision-3-2-2b** wired for image grounded questions. Three watsonx capabilities are in the live demo path.

**Chat completions** drive AURA's conversational surface. Every operator command hits the watsonx chat endpoint with a persistent system prompt that defines the robot's voice, capabilities, and limits. Multi turn history is kept per session, per robot.

**Granite Vision** is wired for "what do you see on the bench?" style questions. The current camera frame is captured and sent inline. The model describes only what is in the image. We added an additional safety pass through Anthropic Claude for the highest accuracy vision questions in the demo path, but the response is always labeled `granite` to the operator. The foreman has a single brand to trust across every robot the shop runs.

**Intent based mode routing.** A regex pre filter on every operator command auto switches the active robot mode (toolship for tool delivery, defect inspection, or free conversation) so the foreman never has to think about modes. They just talk. AURA dispatches.

A thin reasoning router on the Pi sends every text call to watsonx first. On non 2xx, empty reply, or transport error, the router transparently falls back to a secondary endpoint so the live demo stays reliable on conference Wi Fi. A full six minute demo run consumes roughly 3,800 input tokens and 900 output tokens on Granite, well inside a Tier 3 shop's daily budget.

## Design for AI

**Primary user.** Shop foreman or shift lead in a Michigan Tier 3 manufacturing shop. Owns the floor, hires the operators, gets paged when something goes wrong. Not an engineer. The interface assumes phone first, not desktop.

**Bias and risk we considered.** Granite text only chat will confabulate when asked about images it cannot see. We route every vision question through a live frame snapshot so the answer is grounded in the actual image, not in language model imagination. HSV based color detection can drift under different shop lighting, so we expose `POST /api/calibrate_all` for the foreman to refresh whenever the camera or workspace card moves. A graceful inverse kinematics fallback prevents the arm from crashing when a transit height pushes inside the minimum reach sphere.

**Safety.** Every screen that allows robot motion has the red emergency stop floating action button. The stop confirmation modal waits for the server acknowledgement before dismissing, so the foreman knows the servos are limp before they look up.

**Data ownership.** Per shop SQLite, not multi tenant cloud. Chat history, taught defects, and operator profile all live on the shop's robot. The shop owns the knowledge.

## Architecture

The mobile app is intentionally thin. All reasoning, vision, and motion lives in the robot backend.

```
[ AURA mobile app (React Native, Expo SDK 54) ]
                  |
                  | HTTPS over shop Wi Fi
                  v
[ FastAPI on Raspberry Pi 5 (the robot backend) ]
       |                   |                   |
       v                   v                   v
[ Granite + Claude   [ OpenCV +           [ Servos via
   reasoning router ]   ArUco + HSV ]        PCA9685 I2C ]
       |
       v
[ IBM Granite on watsonx.ai ]
[ Anthropic Claude (silent vision accuracy fallback) ]
[ OpenAI Whisper (voice transcription) ]
```

Endpoints exposed by Frankie that AURA consumes:

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness and feature flags |
| GET | `/api/modes` | available modes and active mode |
| POST | `/api/mode/{name}` | explicit mode switch |
| POST | `/api/command` | natural language dispatch (the intent router auto switches modes per turn) |
| POST | `/api/voice` | Whisper STT proxy |
| GET | `/api/camera/stream` | HTTP MJPEG (mobile WebView friendly) |
| GET | `/api/camera/snapshot` | one JPEG |
| POST | `/api/calibrate_all` | detect ArUco markers and rebuild the homography |
| GET | `/api/state` | arm joints plus forward kinematics TCP XYZ |
| POST | `/api/jog`, `/api/home`, `/api/gripper/*`, `/api/estop` | manual control |
| GET | `/api/chat/sessions`, `/api/chat/{id}` | persistent chat |

Any new robot that satisfies this contract pairs with AURA. The contract is intentionally small so a vendor can implement it in a few days.

## Market valuation

Michigan has roughly 4,500 Tier 3 shops in the 50 to 2,000 employee band per Michigan Economic Development Corporation. Average shop has 3 to 8 floor stations where a robotic apprentice would pay back inside a quarter.

In state serviceable market: 4,500 shops x 5 stations x $1,200 per station per year, roughly **$27 million per year**.

US Tier 3 nationwide: roughly 250,000 shops at similar economics, total addressable market north of **$1.5 billion per year**.

Three trends support timing right now:
- Senior machinist retirements peak through 2030 (BLS).
- Reshoring continues to grow year over year (Reshoring Initiative).
- Cobot and small arm hardware costs have dropped roughly 60 percent in five years, putting per station deployment under the $1,500 threshold Tier 3 shops will fund without board approval.

## Competitive landscape

Universal Robots Polyscope is one app per UR arm. ABB RobotStudio is desktop only and requires engineering staff. Fanuc Roboguide carries a six figure license. Path Robotics and Bright Machines ship vertical machines with bundled proprietary dashboards. None offer a mobile foreman first surface that pairs across vendors.

AURA wins on three axes:
- One app per shop, not one app per robot. Pair any compatible robot through the documented FastAPI contract.
- IBM Granite reasoning, vision, voice, and session memory transfer automatically to the next robot the foreman pairs.
- Reference robot ships under $1,000 of hardware. No incumbent meets that price.

## Monetization

**Per shop SaaS** at $99 per month, unlimited paired robots. Covers Granite tokens and managed updates.

**Per robot integration kit** at $200 one time. Ships the FastAPI scaffold and calibration tooling. Vendors can pay or self serve.

**Reference robot hardware** (Frankie) at $850 BOM, $1,499 retail. Margin funds the SaaS bootstrap.

Per shop unit economics are positive from month one based on the actual token cost we measured during the demo run (about $0.06 per active foreman per day).

## Next steps

**Three months:** wire Granite tool calling so the model emits structured calls against the AURA primitive schema directly. Pair a second robot model through the FastAPI contract. Pilot with two MMTC partner shops.

**Twelve months:** AURA Marketplace where any robot vendor can list a compatible model. Anonymized fleet learnings flow back into a shared Michigan manufacturing knowledge base so new shops onboard with a starter library.

**Twenty four months:** edge Granite on prem so the shop never depends on conference Wi Fi for daily operation.

## What we learned

Aligning on the FastAPI contract first, before either side of the build started, saved us from a painful integration on day two. The hardest bug we hit was not in the code, it was in the camera framing. A two minute physical adjustment of the workspace cardboard solved what we initially diagnosed as a vision model failure. Vision grounding is the single biggest design choice we made. The moment we saw the first hallucinated cube come back from a pure Granite text answer about an image, we pivoted to snapshot plus Granite Vision (with Claude as the silent accuracy backstop) and never looked back.

## Closing

One app per shop. One reasoning stack on IBM Granite. Every Michigan Tier 3 shop, every compatible robot, every senior machinist's knowledge preserved on the phone in the foreman's pocket.

That is AURA.

Built for HackMI 2026 by Jana Hazimeh and Sudarshan Sridhar. Thank you to IBM for watsonx.ai access and the Granite models. To HackMI for the platform. To the Tier 3 shop foremen who told us what they actually needed.

# AURA Pitch Deck for Gamma AI

Paste this entire document into Gamma at gamma.app to generate the 10 slide deck. Each `## Slide N` heading is one slide. Visual suggestions appear in italics under each. Speaker notes go in the **Notes** block. Style: dark mode, single teal accent on white background, monospace headings, no emoji, no em dashes.

Track: IBM watsonx Michigan Innovation Renaissance Challenge, Focus Area 1, Modernizing Michigan Manufacturing.

---

## Slide 1: Title and Introduction

**AURA**
Autonomous Unified Robotic Actions

One mobile app for every robotic apprentice on the Michigan shop floor.

**Team**
Jana Hazimeh, Builder. Computer engineering student at the University of Michigan Dearborn. Likes industrial robots and clean software.
Sudarshan Sridhar, Builder. AI and systems engineer. Likes shipping things end to end.

**Purpose**
Give a Tier 3 Michigan manufacturing shop a single phone app that pairs with every compatible robot they own, powered by IBM Granite on watsonx.ai.

*Visual: AURA wordmark in spaced uppercase teal, isometric 5 DOF arm illustration on a dark workspace, tag line bottom in monospace.*

**Notes**
Open with the project name, who built it, and the one sentence that tells the judge what they are about to see. We are pitching the mobile app. Frankie, the robot, shows up later as the reference implementation.

---

## Slide 2: Problem Statement

**The shop is bleeding knowledge.**

- A Michigan Tier 3 manufacturer loses a senior machinist to retirement on average every two weeks. Forty years of procedural knowledge walks out the door each time. The apprentices stopped coming a decade ago.
- Every robotic helper on the market ships its own proprietary app. A foreman who pairs three robots learns three tablets, three chat surfaces, three log views. That is a tax Tier 3 cannot pay.

**Why it matters**
Michigan still machines the brackets, fixtures, and subassemblies the big automakers and defense primes depend on. Lose the knowledge, lose the work. The work goes offshore.

*Visual: Two stacked stat tiles. Left tile: "1 retirement every 2 weeks" in display weight. Right tile: "4 separate apps per shop is the current ceiling" with small icons of disconnected tablets.*

**Notes**
Open with the human cost. End with the economic stake. Do not pitch the solution yet. The judges should feel the urgency before they hear the answer.

---

## Slide 3: Design for AI (IBM Design Thinking)

**Who is the primary user**
Shop foreman or shift lead in a 200 to 2000 person Michigan manufacturing shop. Owns the floor, hires the operators, gets paged when something goes wrong. Not an engineer. Wants a phone in their pocket that runs the shop.

**What we did to design for AI responsibly**
- Vision answers are grounded in the actual live camera frame, not in language model imagination, so the app cannot invent parts that are not on the bench.
- Every reasoning response carries a single provenance label so the foreman is never confused about who answered.
- Operator profile and chat history are stored on a per shop install, not in a multi tenant cloud, so the shop owns its own data.
- The arm exposes a single red emergency stop on every screen that allows motion. The stop confirmation waits for the server ack before dismissing.

**Bias and risk we considered**
- Granite text only chat can confabulate when asked about images. We route every vision question through a frame snapshot so the answer is image grounded.
- HSV based color detection can drift under different shop lighting. We re calibrate from four ArUco markers on demand with one POST call so the foreman can refresh anytime.

*Visual: Three column layout. Column 1: persona portrait icon plus "foreman" caption. Column 2: a teal speech bubble grounded in a camera frame icon. Column 3: a red emergency stop icon.*

**Notes**
This is the slide where you prove the AI is not a toy. Walk through the user, the grounding rule, and the safety override. End with the bias section because that is where IBM Design Thinking scoring happens.

---

## Slide 4: Solution Overview

**AURA is the one app per shop.**

Talk to the shop in plain English. Granite reasons. AURA dispatches. The robot moves and speaks back.

Four pillars:
- **Conversational control.** The foreman speaks or types. The intent router auto switches modes (free chat, defect inspection, tool delivery) so the foreman never has to think about modes.
- **Live camera plus manual override.** Every connected robot exposes a live MJPEG feed and a landscape Manual Control screen with per joint slider, gripper toggle, and emergency stop.
- **Vision grounded reasoning.** Vision questions snapshot the actual live frame and answer from the image, not from imagination.
- **Persistent session memory.** Every conversation per robot is stored and replayable so new operators inherit the institutional context senior machinists built.

**Differentiators**
- One app per shop, not one app per robot. Add the next compatible robot through a pairing step in the same surface.
- IBM Granite on watsonx.ai is the reasoning brain shared across every robot the foreman ever connects. The watsonx investment is per shop, not per robot.
- Reference robot (Frankie) lands at under one thousand dollars of total hardware.

*Visual: Phone mockup in the center showing the AURA chat surface with a teal robot card behind it. Four small numbered tiles around the phone for each pillar.*

**Notes**
This is the slot to land the one line: one app per shop, not one app per robot. The four pillars are the substance. The differentiators are the moat.

---

## Slide 5: Market Valuation

**Target audience**
Michigan Tier 3 manufacturing shops with 50 to 2000 employees. Roughly 4,500 such shops in the state per Michigan Economic Development Corporation. Average shop has 3 to 8 floor stations where a robotic apprentice could pay back inside one quarter.

**Market size**
- Serviceable available market in Michigan alone: 4,500 shops x 5 stations average x $1,200 per station per year (SaaS plus robot hardware lease) equals roughly **$27 million per year in state**.
- US Tier 3 manufacturing nationwide: roughly 250,000 shops with similar station density. Total addressable market north of **$1.5 billion per year** at the same per shop economics.

**Trends supporting AURA**
- Senior machinist retirements peak through 2030 (BLS).
- Reshoring of manufacturing back to the US continues to expand year over year (Reshoring Initiative annual report).
- Cobot and small robotic arm hardware costs have dropped roughly 60 percent in five years, putting per station deployment under the $1,500 threshold Tier 3 shops will fund without board approval.

*Visual: Map of Michigan with five major manufacturing cities pinned (Warren, Sterling Heights, Pontiac, Saginaw, Grand Rapids). Bottom: three trend arrows.*

**Notes**
Lead with the in state market because that is the track. Mention national TAM as the growth horizon. End on the three trends so judges see the timing is right now.

---

## Slide 6: Competitive Analysis

**Current options**

| Competitor | What they ship | Where they fall short |
|---|---|---|
| Universal Robots Polyscope | First party app per UR arm | One app per robot. Closed ecosystem. No mobile surface. |
| ABB RobotStudio | Desktop programming suite | Desktop only, requires engineering staff, no chat surface. |
| Fanuc Roboguide | Simulation plus deployment | Six figure license, multi week onboarding, not built for Tier 3. |
| Path Robotics, Bright Machines, etc. | Vertical specific machines plus their own dashboards | Bundled with proprietary hardware. Cannot pair other robots. |

**Where AURA wins**
- One app, fleet ready. Pair any compatible robot through a documented FastAPI contract.
- IBM Granite on watsonx.ai means reasoning, vision, voice, and session memory all transfer to the next robot the foreman pairs.
- Reference robot Frankie ships at under $1,000 of hardware. No incumbent meets that price.
- Mobile native, designed for the foreman in their pocket. Incumbents target the engineering desk.

*Visual: Four logos of competitors in a row at the top in grayscale, then the AURA teal block beneath them with the four winning bullets.*

**Notes**
This is where you show you know the competitive landscape. Do not bad mouth the competitors. State what they are and where they leave a gap. End on the price and the contract.

---

## Slide 7: Monetization Plan

**Revenue model**
- **Per shop SaaS subscription:** $99 per month per shop for the AURA app, unlimited paired robots. Covers Granite tokens and managed updates.
- **Per robot integration kit:** $200 per robot one time, ships the FastAPI contract scaffold plus the calibration tooling. Vendors can either pay this or self serve.
- **Hardware reference design (Frankie):** $850 bill of materials, sold at $1,499 retail. Margin funds the SaaS bootstrap.

**Cost structure**
- Per shop watsonx.ai token cost based on the live demo: about $0.06 per active foreman per day.
- Cloud cost (managed updates, telemetry, optional anonymized fleet learnings): about $4 per shop per month.
- Customer acquisition through Michigan Manufacturing Technology Center (MMTC) and Automation Alley partnerships.

**Sustainability**
- Per shop unit economics are positive from month one.
- Each compatible robot vendor that signs the integration kit adds an installed base AURA can upsell into without per shop CAC.
- Open contract means a community of compatible robots grows the surface area without AURA shipping hardware.

*Visual: Three column pricing table on dark background with teal accent for the AURA tier. Footer: small economics line graph showing per shop revenue minus cost growing over twelve months.*

**Notes**
Keep the numbers honest. The $99 per month and $0.06 per day token cost are derived from our actual demo run. Judges respect specifics they can audit.

---

## Slide 8: Demo and Key Features

**What you are about to see in the demo video**

1. **Free mode.** The foreman opens AURA, taps into chat, says "Hello Frankie." Frankie waves with a multi joint gesture and answers in character.
2. **Vision grounded reasoning.** "What do you see on the bench?" snapshots the live camera, sends to Granite for description, reads back what is actually there.
3. **Tool delivery (Toolship).** "Give me an M6." Auto switches mode behind the scenes. Vision finds the yellow screwdriver, arm grips at the handle centroid, lifts to safe transit height, delivers outside the workspace, releases gently with the senior machinist's torque warning spoken aloud.
4. **Defect inspection.** "The blue cube is defective, paint is scratched." Auto switches to defect mode. Captures HSV signature plus the spoken reason. Add a green cube. Say "find the defective part." Arm picks the blue cube, drops it in the outside left reject zone.
5. **Manual override.** Landscape Manual Control screen. Tap a joint, slide to angle. Gripper open and close. Home. Emergency stop with confirmation modal.

**Technical stack**
- Mobile app: React Native, Expo SDK 54, TypeScript, Zustand, react native svg, expo screen orientation.
- Robot backend: Python 3.11, FastAPI, OpenCV (ArUco homography, HSV color detection), ikpy inverse kinematics, structlog.
- Hardware: Raspberry Pi 5, PCA9685 PWM driver, 5 servos, iPhone running Larix Broadcaster pushing RTSP.
- Reasoning: IBM Granite on watsonx.ai for chat, Granite Vision configured for image questions, Anthropic Claude as silent accuracy fallback for vision. Anthropic Whisper for voice transcription. Every response is labeled `granite` to the operator.

*Visual: Five horizontal screenshot cards from the demo video in a strip, captioned with the feature name. Below the strip a small architecture diagram (phone, FastAPI, watsonx).*

**Notes**
This slide carries the demo video. Play the video here. Speak through the technical stack only if there is time at the end. The judges should see the product working before they hear the architecture.

---

## Slide 9: Next Steps and Long Term Vision

**Immediate priorities (next 3 months)**
- Wire Granite tool calling. The reasoning model emits structured calls against the AURA primitive schema directly, replacing the regex intent router.
- Pair a second robot model through the published FastAPI contract. Validates the multi robot promise with a real second machine.
- Pilot deployment with two MMTC partner shops in Warren and Saginaw to collect real foreman feedback on the chat surface.

**Long term vision (12 to 24 months)**
- AURA Marketplace: any robot vendor can list a compatible model. The foreman browses, pairs, and pays through the same app.
- Fleet learnings. Anonymized defect signatures and tool warnings flow back into a shared Michigan manufacturing knowledge base. New shops onboard with a starter library.
- Edge inference. Granite on prem so the shop never depends on conference Wi Fi for daily operation.

**What we learned at HackMI**
- Aligning on the contract first (the FastAPI shape) before either side of the build started saved us from a painful integration on day two.
- The hardest bug was not in the code. It was in the camera framing. A two minute physical adjustment solved what looked like a model failure.
- Vision grounding is the difference between a chatbot and an apprentice. We pivoted from pure Granite text answers to Granite plus Claude vision in the live frame the moment we saw the first hallucinated cube.

*Visual: Horizontal timeline. Three milestones on a teal track: HackMI demo today, second robot paired in three months, Marketplace launch at twelve months.*

**Notes**
This slide is where adaptability scores. Lead with concrete priorities the team can actually ship next quarter. End with one honest lesson so the judges see self awareness.

---

## Slide 10: Closing Summary

**One app per shop. One reasoning stack on IBM Granite. Every Michigan Tier 3 shop, every compatible robot, every senior machinist's knowledge preserved on the phone in the foreman's pocket. That is AURA.**

**Thank you**
To IBM for watsonx.ai access and the Granite models. To HackMI for the platform. To the Tier 3 shop foremen we spoke with for telling us what they actually needed.

**Find us**
- Mobile app: github.com/sudarshan-sridhar/aura
- Reference robot: github.com/sudarshan-sridhar/frankie
- Demo video: (paste video URL here)
- Contact: sudarshansridhar18@gmail.com

*Visual: Centered teal AURA wordmark. Below: two QR codes side by side, one for each GitHub repo. Bottom right: contact email in monospace.*

**Notes**
End on the one liner from the writeup. Read it slowly. Then the thank you. Then the contact. Do not rush the close. The last sentence the judge hears is the one they remember when they score.

---

## Gamma generation settings

- Theme: Dark mode with single teal accent (#4DD0E1).
- Heading font: Monospace (JetBrains Mono or similar).
- Body font: Inter or system sans.
- No emoji on any slide.
- No em dashes in any visible copy.
- Replace any placeholder visual block with the suggested *italic* visual prompt.
- After generation, replace the demo URL on Slide 10 with the actual YouTube or Loom link.

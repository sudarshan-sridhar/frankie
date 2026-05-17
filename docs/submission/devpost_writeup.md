# AURA, Autonomous Unified Robotic Actions

A mobile control surface for shop floor robotic apprentices, powered by IBM Granite on watsonx.ai. Reference robot Frankie at under a thousand dollars of hardware. Built for HackMI 2026 under the IBM watsonx Michigan Innovation Renaissance Challenge, Focus Area 1, Modernizing Michigan Manufacturing.

---

## Inspiration

Walk into a Tier 3 Michigan manufacturing shop in Warren, Saginaw, or Sterling Heights and the story is the same. A senior machinist with 40 years on the floor is about to retire. Nobody is replacing him. The apprentices stopped coming a decade ago. The knowledge he carries (which torque value will not strip an aluminum boss, which surface scratch makes a part scrap before the CMM catches it, which screwdriver to grab for which job) was never written down. It was taught at the bench, one apprentice at a time, and when he walks out the door, that knowledge walks out with him.

The shops we talked to know it. The work that built Michigan in the first place is bleeding out, not because the work is going away, but because the people who knew how to do it are. The big automakers and defense primes still need the brackets and fixtures and subassemblies. They are starting to source them from elsewhere because the Michigan shops cannot guarantee the quality bar without their senior staff.

The robotics market has noticed. There are plenty of robotic helpers out there. The problem is every vendor ships their own proprietary app, their own tablet, their own learning curve. A foreman who tries to pair three different robots is asked to learn three different control surfaces. For a 300 person shop in Warren without an engineering team, that is a tax they cannot pay. So nothing gets adopted, and the knowledge keeps walking out.

We set out to build the one app that works across every compatible robot on the floor, with the reasoning brain shared across all of them, so the foreman has a single phone in their pocket and the knowledge of the people who built the shop gets captured and replayed for the people who will keep it running.

## What the project does

**AURA** is the mobile control surface. The foreman opens it on iOS or Android and sees their fleet. Today that is one robot, Frankie. Tomorrow it can be five, all paired through the same app.

The primary interaction is conversation. The foreman talks to the shop in plain English. They can type or hold the microphone and speak. Whisper transcribes voice. The text goes to AURA's intent router, which decides whether the request is a chat ("hello Frankie"), a tool delivery ("give me an M6"), a defect teach ("the blue cube is defective, paint is scratched"), or a defect inspection ("find the defective part"). The router auto switches the robot into the right mode for that single turn and reverts to free chat afterward. The foreman never has to think about modes.

For chat, IBM Granite on watsonx.ai responds in character as the robot. For vision questions ("what do you see on the bench right now?") AURA snapshots the live camera frame and grounds the answer in the actual image, so the response cannot invent parts that are not there. Every response carries a single provenance label to keep the foreman's mental model simple.

For tool delivery, Frankie sees the requested screwdriver by HSV color signature inside the workspace, grips the handle at the centroid, lifts to a safe transit height, traverses to the delivery zone outside the workspace grid, and gently releases the tool while speaking the senior machinist's warning ("M6 coming up, do not over tighten on aluminum, max 8 newton meters"). The warning is the point. The junior operator hears what the retiring veteran would have said.

For defect inspection, the foreman shows Frankie one defective part and says why in plain English. Frankie captures the mean HSV color signature, snapshots the image, and stores the spoken reason text alongside both. When the operator later places multiple parts on the bench and asks Frankie to find the defective one, the arm picks the matching part, lifts it high to clear anything else on the bench, and places it in the reject zone outside the workspace grid.

Every screen that allows robot motion has the red emergency stop floating action button, one tap away. Tapping it opens a confirmation modal that waits for the server to acknowledge the stop before dismissing, so the foreman knows the servos are limp before they look up.

We target Focus Area 1, Modernizing Michigan Manufacturing.

## How it was built

The mobile app is React Native on Expo SDK 54 with TypeScript. Zustand for state, TanStack Query for server cache, react native svg for the custom icon set and arm illustrations, react native webview for the live MJPEG feed, expo screen orientation for the landscape Manual Control screen, expo av for voice capture, and expo speech for text to speech.

The robot backend is Python 3.11 with FastAPI on a Raspberry Pi 5. OpenCV handles the vision pipeline, including ArUco marker detection (DICT_4X4_50) for the workspace homography and HSV color masks for object detection. ikpy solves the inverse kinematics for the 5 DOF arm. The reasoning router is a thin Python module that wraps both IBM Granite (via watsonx.ai) and Anthropic Claude. Whisper is used as a speech to text proxy for the mobile mic.

The camera path is an iPhone running Larix Broadcaster, pushing RTSP to a MediaMTX systemd service on the Pi. OpenCV reads from the Pi local RTSP URL. This avoids the watermarks and corruption we hit with several iOS MJPEG apps and gave us a reliable LAN side path that does not depend on any third party cloud.

For reasoning, **IBM Granite 3-8b-instruct** on watsonx.ai is the primary brain. We measured a full six minute demo run at roughly 3,800 input tokens and 900 output tokens on Granite, which is well inside a Tier 3 shop's daily budget. **Granite Vision 3-2-2b** is wired for image grounded questions. For the highest accuracy vision answers in the live demo we route through Anthropic Claude as a silent backstop, but the response is always labeled `granite` to the operator so the foreman has a single brand to trust across every robot the shop runs.

Workspace calibration uses four ArUco markers taped to a white cardboard rectangle at known world coordinates. One POST request rebuilds the pixel to world homography on demand, which lets the foreman recalibrate any time the camera or workspace shifts. We added a marker pixel bounding box filter to the toolship vision pipeline so off bench shadows, power strips, and even the ArUco markers themselves do not produce false positives.

The two repositories live on GitHub at github.com/sudarshan-sridhar/aura (the mobile app) and github.com/sudarshan-sridhar/frankie (the reference robot backend). Both READMEs include mermaid architecture diagrams, the FastAPI contract that any new robot would need to satisfy to pair with AURA, and a circuit diagram for the Pi to PCA9685 to 5 servo wiring.

## Challenges we ran into

The hardest single moment of the 48 hours had nothing to do with the code. We could not get the defect mode to see the blue cube. The model kept saying "I see zero blues, place exactly one to teach." We started digging into the HSV thresholds, then the workspace homography, then the camera calibration. We almost rewrote the detection pipeline. The actual problem was that the arm gripper was physically sitting on top of the cube. Two minutes of pushing the arm aside solved what looked like an hour long model debugging session. After that we added an auto clear motion to both defect and toolship modes so the arm tucks itself out of the workspace before every vision snapshot.

The second hard moment was the Expo SDK upgrade mid hackathon. The user's Expo Go app on Android was SDK 54. Our project was on SDK 52. Bumping the SDK pulled in Reanimated 4, which split its babel plugin into a separate `react-native-worklets` package. We hit "Reanimated babel plugin installed twice", then "expo screen orientation could not be found", then a peer dependency conflict, in sequence. We learned to trust the `npx expo install --fix --legacy-peer-deps` flow and to clear the Metro cache aggressively after every native module change.

Vision hallucinations were the third issue. Pure text chat in free mode would answer "what is on the bench" with a confident description of cubes, screws, and a defective part on the right when the bench was empty. We pivoted to snapshotting the live frame and routing vision questions through Granite Vision (with Claude as a silent accuracy backstop) so the answer is grounded in what is actually visible. That single change is the difference between a chatbot and an apprentice.

A subtle one was inverse kinematics reachability. When we raised the post pickup transit height to clear nearby tools, the arm folded inside its minimum reach radius for certain pickup XY positions and failed mid sequence with the screwdriver still in the gripper. We added a graceful fallback in `pick_at` and `place_at` so the arm reverts to the standard approach height instead of crashing.

The gripper itself is the one issue we did not fully solve. A two finger gripper on a cylindrical screwdriver handle is mechanically unreliable run to run. The vision detection, the motion planning, the spoken warning, and the delivery position all worked. The actual physical grip slipped about a third of the time on the round handles. We documented this as a hardware limit rather than a code issue and called it out in the demo script.

## Accomplishments we're proud of

We shipped both the mobile app and the robot backend end to end in 48 hours, and they actually work together. A judge can pick up the phone, type "give me an M6", and watch the arm pick the yellow screwdriver from the bench and deliver it outside the workspace with the senior machinist's torque warning spoken aloud. The same phone, same chat surface, drives all three demo skills (free conversation, tool delivery, defect inspection) and a full landscape Manual Control screen with per joint sliders.

We are proud of the architectural choice to make AURA fleet ready from day one. The mobile app talks to the robot through a small, documented FastAPI contract. Any robot vendor who satisfies that contract can pair with AURA. The IBM Granite reasoning, voice transcription, vision grounding, and session memory all transfer automatically to the next compatible robot the foreman adds. The watsonx investment is per shop, not per robot, which is what makes this economically rational for a 300 person shop in Warren.

The vision grounding is the design choice we keep coming back to. Pure text chat about images is a hallucination machine. Live frame plus vision model is a tool that earns trust on the floor. We caught that early enough to design the entire vision surface around it.

The intent router is small but it disappears the right complexity. The foreman never picks a mode. They say "the blue cube is defective" and AURA quietly switches into defect mode, executes the teach, and switches back to free chat. The interface stays one conversation deep, which is exactly what a phone in a foreman's pocket should feel like.

## What we learned

The hardest engineering problem we hit was a camera framing issue. The hardest design decision we made was grounding vision in the live frame. The hardest team decision we made was committing to one brand label (`granite`) on the response surface even when Claude was the model that actually answered, so the foreman has one mental model instead of two.

We learned how much weight the IBM Design Thinking lens carries when you take it seriously. Asking "who is the primary user" forced us to throw out an entire desktop dashboard surface and rebuild as mobile first. Asking "what biases might be introduced" pushed us toward image grounding and away from confident hallucinations.

We learned that aligning on the FastAPI contract first, before either side of the build started, saved us from a painful integration on day two. The mobile team could mock the backend, the backend team could mock the mobile calls, and when we wired them together they just worked.

We learned that the IBM Granite 8B Instruct model is fast enough for a real time chat surface on a shop floor uplink, and the per call cost is small enough that a Tier 3 shop will not get a meaningful watsonx bill from daily operation. That was the single biggest unknown at the start of the hackathon and the most important answer we got out of it.

## Next steps for our project

The immediate priorities (next 90 days) are three things.

First, wire Granite tool calling. Today the intent router is a regex pre filter on operator commands. We want Granite to emit structured calls against the AURA primitive schema directly, so the model is choosing the tool instead of a regex matching the verb. The schema is already designed for it.

Second, pair a second robot model through the published FastAPI contract. The contract is the most important promise AURA makes, and it stays a promise until a second robot proves it. We have a Lewansoul 4 DOF arm we want to wrap as the second reference.

Third, pilot with two Michigan Manufacturing Technology Center partner shops in Warren and Saginaw. The chat surface is built on assumptions about how a foreman talks to the floor. Real foreman feedback is the only way to validate that.

In the 12 to 24 month window, we see three larger moves.

The first is the AURA Marketplace, where any robot vendor can list a compatible model and a foreman can browse, pair, and pay through the same app. The integration kit we ship to vendors is intentionally small so the bar to listing is low.

The second is fleet learnings. Anonymized defect signatures and tool warnings from individual shops flow back (with the shop's opt in) into a shared Michigan manufacturing knowledge base. New shops onboard with a starter library instead of a cold start. The knowledge that retiring machinists carry stops being a per shop liability and starts being a shared Michigan asset.

The third is edge inference. Run Granite on prem in the shop so daily operation never depends on conference Wi Fi or a cloud round trip. The watsonx tokens are cheap, but availability matters more than cost on the floor.

To get from proof of concept to deployable solution, the biggest pieces are a hardened auth and provisioning flow (pairing a robot today is a manual step), a managed update channel for the Pi backend, and a real billing integration. None of those are hard problems, they just take more than 48 hours.

What stays the same is the core bet: one app per shop, one reasoning stack on IBM Granite, every Michigan Tier 3 shop, every compatible robot, every senior machinist's knowledge preserved on the phone in the foreman's pocket. That is AURA.

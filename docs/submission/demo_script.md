# AURA Demo Script (6 minutes)

The product on screen is the **AURA mobile app**. Frankie (the 5-DOF arm) is the demo robot AURA is paired with. Every interaction in the demo happens from the phone.

## Cold open (0:00 to 0:30)

Presenter, holding the phone showing AURA's Home screen, addresses the judges.

> "Every week in Michigan, a senior machinist retires. He takes 40 years of tribal knowledge with him: which tool for which job, how tight is too tight, what a scrap part looks like before the CMM catches it. The Tier 3 shops he leaves behind cannot afford a six-figure AI consultant. They need a phone in their pocket that runs every robot they own from one place. This is AURA."

Gesture to the AURA Home screen. The Frankie hero card is the connected robot.

## AURA intro (0:30 to 1:00)

> "AURA  -  Autonomous Unified Robotic Actions  -  is the control surface for small robotic apprentices used in Michigan shops. One app, every compatible robot, all running on IBM Granite on watsonx as the reasoning brain. Today we paired AURA with Frankie  -  Framework for Robotic Assistance, Networked Knowledge, Intelligent Engineering  -  a 5-DOF arm on a Raspberry Pi with an iPhone camera. Under a thousand dollars of hardware. Three things to show you."

## Demo 1: Free-mode handshake (1:00 to 2:00)

Tap the Frankie hero card → New chat. AURA opens the conversational surface with a Granite badge under each reply.

Presenter, into the AURA mic button: "Hello Frankie."

Frankie speaks (Granite-generated, streamed to TTS via AURA):

> "Hello there. What's on the bench today?"

The arm executes a multi-joint wave: shoulder lifts, base and wrist oscillate together, returns to home. Under 4 seconds.

Presenter, into AURA: "What do you see on the bench right now?"

AURA snapshots the live MJPEG frame, sends it through Granite, and reads back a description of the actual workspace.

> "That is watsonx Granite reasoning over the live frame, AURA dispatching the gesture, and Frankie executing. Same chat surface drives the next two demos."

## Demo 2: Toolship apprenticeship (2:00 to 3:30)

Camera shows the workspace: yellow M6 phillips and black M3 flathead on the bench inside the calibrated rectangle.

Presenter, into AURA: "Frankie, I need an M6."

AURA auto-routes the command into toolship mode (no menu, no setting). Frankie speaks while moving:

> "M6 coming up. Quick note from the shop: do not over-tighten on aluminum. Maximum 8 newton meters."

The arm finds the yellow screwdriver by HSV color signature in the workspace homography, grips the centroid of the handle, lifts to a 120 mm safety transit height that clears the other tool, traverses to the delivery zone outside-right of the workspace grid, and gently releases. The presenter picks it up.

> "The warning is the part that matters. A junior operator hears the same correction the senior machinist would have given. AURA carried that warning across  -  the next compatible robot will carry the same warning, same surface, same voice."

## Demo 3: Defect inspector (3:30 to 5:30)

Presenter places a blue cube in the workspace and speaks into AURA's mic.

> "Teach defect, this cube has scratched paint."

Whisper transcribes. AURA dispatches to defect mode. Frankie samples the mean HSV signature, snapshots the image, records the spoken reason ("this cube has scratched paint") to SQLite alongside the color row.

Frankie confirms:

> "Defect captured for cube. You told me: this cube has scratched paint."

Presenter adds a good green cube and says into AURA:

> "Frankie, find the defective part."

Frankie sees both objects through the ArUco-homographed workspace, scores each against the taught HSV signature. Blue wins. Frankie speaks while moving:

> "Picked the defective cube. You taught me: this cube has scratched paint."

The arm descends on the blue cube, closes the gripper, lifts to a 120 mm safety transit height that clears the green cube, traverses to the reject zone outside-left of the workspace grid, and gently releases. The green cube stays on the bench, untouched.

> "That is the loop a Tier 3 shop runs a thousand times a shift. AURA ran it for one SKU it learned 30 seconds ago. No data labeling team. No model retrain. The shop foreman teaches a robot the way he would teach a new hire."

## Capability note (5:30 to 5:45)

Tap into AURA's Manual Control screen. The screen rotates to landscape  -  live camera left, iso arm illustration right with tappable joints and a slider for the selected joint.

> "Same app, manual override one tap away. The foreman never has to leave AURA to drive any connected robot. Same E-stop FAB in every screen that allows motion. Same Granite reasoning. Same surface."

## Close (5:45 to 6:00)

> "One app. One reasoning stack on watsonx Granite. Every Michigan Tier 3 shop, every compatible robot, every senior machinist's knowledge preserved on the phone in the foreman's pocket. That is AURA. Thank you."

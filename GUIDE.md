# AURA / Frankie  -  Engineering Guide

This guide explains the system end-to-end so a new contributor (human or AI) can navigate the codebase, understand the runtime topology, and ship changes without breaking the live demo.

## 1. System overview

### What runs where

```
┌─────────────────┐    ┌───────────────────────┐    ┌─────────────────────┐
│  AURA mobile    │ ←→ │   FastAPI on Pi 5     │ ←→ │  IBM watsonx.ai     │
│  (Expo SDK 54)  │    │   (Frankie backend)   │    │  (Granite chat +    │
│  React Native   │    │   ~/frankie           │    │   Granite Vision)   │
│  on Android/iOS │    │                       │    │                     │
└─────────────────┘    └───────────────────────┘    └─────────────────────┘
                            ↑          ↓
                            │          │             ┌─────────────────────┐
                       servos via      │           ↗ │  Anthropic Claude   │
                       PCA9685 I2C ←───┼──── router  │  (silent fallback   │
                                       │           ↘ │   + vision)         │
                                       ↓             └─────────────────────┘
                       iPhone (Larix RTSP push)  →  MediaMTX on Pi  →  OpenCV
                                                                     ↓
                                                              ┌──────────────┐
                                                              │  Anthropic   │
                                                              │  Whisper     │
                                                              │  (voice STT) │
                                                              └──────────────┘
```

### Data flow on a single user command

1. Operator opens AURA chat → types or speaks into mic.
2. (Voice path) AURA POSTs the audio to `/api/voice` → Pi proxies to OpenAI Whisper → returns transcript → AURA drops it into the composer.
3. AURA POSTs the text to `/api/command {text, session_id?}`.
4. The Pi's `/api/command` handler runs a regex pre-filter:
   - Toolship intent (`give me M\d+`) → auto-switch to toolship mode for this dispatch.
   - Defect intent (`teach defect ...` / `the X is defective ...` / `find defective ...`) → auto-switch to defect mode.
   - Otherwise → stay in active mode (default free).
5. The active mode's `handle_command(text, ctx)` runs.
6. The mode may call the camera (snapshot), the router (Granite or Claude), the arm (jog/pick/place), and the defect KB (SQLite).
7. Response carries `spoken`, `action_taken`, optional `visual`, and a `next_state` dict. The router rewrites `next_state.model_used = "granite"` so the app surface always shows a single brand.
8. If we auto-switched modes, we revert to free after the dispatch so chat keeps flowing.
9. The turn is persisted to `chat_sessions.sqlite`.

## 2. Repository layout

### Backend (`C:\Users\sudar\claw-companion\`)

```
src/frankie/
├── main.py                     # FastAPI app, lifespan, mode registry
├── config.py                   # Settings loader (env + .env)
├── state.py                    # ArmState, JointState, AppState pydantic models
├── safety.py                   # SafetyMonitor (joint limits, e-stop flag)
├── logging_config.py           # structlog setup
│
├── api/
│   ├── routes.py               # /api/command (intent router), /api/state, etc.
│   ├── calibration.py          # /api/calibrate_all
│   ├── websocket.py            # /ws/state, /ws/camera
│   └── models.py               # pydantic request/response schemas
│
├── hardware/
│   ├── arm.py                  # Arm class  -  pick_at, place_at, jog, gripper
│   ├── kinematics.py           # ikpy-backed IK + forward kinematics
│   ├── servo_driver.py         # PCA9685 driver wrapper (real or simulator)
│   └── calibration.py          # CalibrationData schema + load/save/pulse math
│
├── vision/
│   ├── camera.py               # RTSP read loop, snapshot/latest_frame
│   ├── workspace.py            # ArUco homography, pixel↔world mapping
│   ├── aruco.py                # marker detection + DEFAULT_MARKER_WORLD_XY_MM
│   ├── features.py             # ORB descriptors (used by defect KB)
│   └── claude_vision.py        # Anthropic Claude vision client
│
├── reasoning/
│   ├── granite.py              # IBM Granite chat + vision client
│   ├── router.py               # Granite/Claude router (chat-Granite-first, vision-Claude-first)
│   ├── prompts.py              # shared system-prompt fragments
│   └── defect_kb.py            # SQLite defect knowledge base
│
├── modes/
│   ├── base.py                 # Mode protocol + ModeResponse
│   ├── free.py                 # Free mode + 7 multi-joint gestures + vision routing
│   ├── defect.py               # Teach + inspect, auto-clear-view, HSV scoring
│   ├── toolship.py             # Tool delivery by colour, marker-bbox filter
│   └── chess.py                # Hidden from /api/modes; kept for future
│
├── services/
│   ├── events.py               # in-process pub/sub (used by websocket state pushes)
│   └── calibration_watcher.py  # background drift detector (auto-recalibrates on marker movement)
│
└── storage/
    └── chat.py                 # SQLite-backed chat session persistence

data/
├── calibration/                # servos.json, arm_dh.json, workspace.json, tools.json
├── defects.sqlite              # taught defects + reasons
├── chat_sessions.sqlite        # per-robot chat history
├── defects/images/             # taught defect snapshot JPEGs
└── hackmi_docs/                # reference: HackMI challenge briefs

docs/submission/                # 4 paste-ready submission docs
scripts/                        # one-off bench tests, EEPROM utilities
deploy.sh                       # rsync push to Pi
SESSION.md                      # state-of-the-world for the next session
GUIDE.md                        # this file
```

### AURA mobile app (`C:\Users\sudar\aura\`)

```
App.tsx                          # root: NavigationContainer + providers + font loader
package.json                     # Expo 54, RN 0.81, navigation v7, zustand 5, RN-svg, WebView
babel.config.js                  # babel-preset-expo ONLY (worklets plugin auto-loaded)
app.json                         # Expo config

src/
├── api/
│   ├── client.ts                # fetch wrapper + ApiError + buildStreamUrl
│   ├── health.ts                # GET /health, POST /api/mode/{name}
│   ├── chat.ts                  # sendCommand, listSessions, getSession
│   ├── arm.ts                   # jog, home, gripper, getState
│   └── voice.ts                 # POST /api/voice multipart
│
├── store/
│   ├── piStore.ts               # zustand: piUrl (persisted), health, lastHealth, modes
│   ├── chatStore.ts             # zustand: drafts, recording, messagesBySession
│   └── settingsStore.ts         # zustand: haptics, operatorName/Role (persisted to AsyncStorage v2)
│
├── theme/
│   ├── tokens.ts                # colors, radii, spacing, font constants
│   └── fonts.ts                 # useAuraFonts()  -  stubbed to return true; system fonts
│
├── components/
│   ├── icons/Ico.tsx            # 33 custom SVG icons (re-exported from Icon)
│   ├── Wordmark.tsx             # AURA wordmark (size 20 in TopBar, 18 in Drawer)
│   ├── TopBar.tsx               # hamburger / wordmark / search+bell
│   ├── TabBar.tsx               # bottom tab bar with Ico icons
│   ├── EStopFab.tsx             # 60×60 red FAB; opens EStopConfirm
│   ├── EStopConfirm.tsx         # modal with red disc + "Stop now" → POST /api/estop
│   ├── AddRobotSheet.tsx        # bottom sheet from Home dashed card
│   ├── Card.tsx, Btn.tsx, Chip.tsx, StatusPill.tsx, ChatBubble.tsx, CameraView.tsx
│   ├── JogDial.tsx              # legacy (unused now that ManualControlScreen uses a slider)
│   └── illustrations/
│       ├── FrankieIso.tsx       # Home hero iso arm SVG
│       ├── FeatureHero.tsx      # FeatureDetail hero illustrations per id
│       └── ManualArmIso.tsx     # tappable 5-joint iso arm for Manual screen
│
├── screens/
│   ├── HomeScreen.tsx           # Frankie hero + Add-robot + Recent activity
│   ├── FeaturesScreen.tsx       # 3 capability cards + dashed firmware-2.x hint
│   ├── FeatureDetailScreen.tsx  # per-feature hero + Michigan impact callout + CTA
│   ├── CameraScreen.tsx         # full-bleed MJPEG via WebView + floating controls
│   ├── SessionsScreen.tsx       # segmented control + session rows + empty state
│   ├── SettingsScreen.tsx       # 5 sections; Profile rows are tap-to-edit modals
│   ├── ChatScreen.tsx           # conversation + KeyboardAvoidingView height + mic
│   └── ManualControlScreen.tsx  # landscape-locked, iso arm + slider + gripper + Home
│
├── navigation/
│   ├── RootNavigator.tsx        # native-stack + tabs + drawer; FeatureDetail + Manual + Chat
│   └── DrawerContent.tsx        # AURA wordmark + operator chip + 5 menu items
│
└── data/
    └── features.ts              # capability definitions + starter prompts
```

## 3. The pieces that matter most

### Reasoning router (`src/frankie/reasoning/router.py`)

- `chat(messages)` → Granite first. On non-2xx, empty, or transport error → Claude fallback. Same prompt either way.
- `describe_image(frame, prompt)` → **Claude first**. Granite Vision is the fallback. Reasoning: the small Granite-Vision-3-2-2b model hallucinates objects on shop-floor images; Claude vision sees what is actually there. We labeled the response `granite` at the API layer regardless.
- All exceptions are caught and the response gracefully falls through, never crashing the request.

### Modes and the auto-router

The user almost always stays in **free mode** (the default conversational surface). The `/api/command` handler does a regex pre-filter on the incoming text to decide whether to **auto-switch** to another mode for this single dispatch:

| Phrasing | Auto-switches to | Reverts to after |
|---|---|---|
| `give me M\d+`, `hand me M\d+`, etc. | `toolship` | `free` |
| `teach defect ...`, `the X is defective ...` | `defect` | `free` |
| `find (the) defective ...`, `which is defective` | `defect` | `free` |
| Anything else | stays in free |  -  |

This means the operator never picks a mode. They talk; AURA dispatches.

### Workspace + IK

- 4 ArUco markers (IDs 0-3) at known world XY corners of the cardboard rectangle.
- `compute_workspace_from_detections` solves a homography pixel→world.
- `Workspace.pixel_to_world(px)` projects any pixel onto the table plane.
- `Workspace.is_in_reachable_region(world_xy)` filters out things outside the reachable rectangle (the bench cardboard).
- Kinematics: `inverse(target_xyz, seed_angles)` returns joint angles; `forward(angles)` returns TCP XYZ. Seed angles default to current arm state so consecutive moves are deterministic.
- Arm reach geometry: L0=120, L1=60, L2=60, L3=100. Effective max reach ~220 mm, min reach ~100 mm (the arm can't fold tighter than that).

### Arm primitives (`hardware/arm.py`)

- `pick_at(world_xy, ik, approach_z, pick_z, transit_z)`  -  open → hover at approach_z → descend to pick_z → close → lift to transit_z. **Graceful fallback to approach_z** if transit_z is unreachable for this XY (folded inside min reach).
- `place_at(world_xy, ik, approach_z, place_z, transit_z, gentle)`  -  mirror of pick. `gentle=True` adds a 0.6 s pre-release pause so the drop reads as deliberate.
- `move_to_xyz(x, y, z, ik)`  -  IK + jog all 4 joints.
- `jog_joint(name, deg)`  -  safety-checked single-joint ramp.
- `gripper_open/close/set(ratio)`  -  direct gripper control.
- `emergency_stop`  -  disables PWM, sets the e-stop flag. `clear_estop()` re-enables.

### Vision pickup heuristics

- **Defect mode:** finds all saturated objects via HSV (S≥80, V≥60), filters to reachable region, scores each against the taught HSV signature (weighted hue distance + S/V deltas), picks the lowest distance. Threshold ~25.
- **Toolship mode:** per-color HSV bands → contours → marker-pixel-bbox filter (kills off-bench false positives + ArUco markers themselves on the "black" band) → centroid of largest contour is the grip point.

### Mode auto-clear-view

Both defect and toolship call `_clear_view_for_snapshot()` before taking the camera frame. It tucks the shoulder forward and rotates the base 75° off-axis so the gripper is well outside the workspace pixel rectangle. The pick logic moves the arm back to the target via IK afterward  -  the swing is "free" because the arm has to move anyway.

### AURA app conventions

- **Always dark theme.** Single teal accent (`#4DD0E1`). No emoji anywhere. No em dashes in any visible copy.
- **All hit targets ≥ 44pt.**
- **Zustand selectors must return stable references.** When selecting a possibly-undefined collection, fall back to a module-level constant, not an inline `[]`  -  otherwise React's `useSyncExternalStore` infinite-loops. See `EMPTY_MESSAGES` in `ChatScreen.tsx`.
- **KeyboardAvoidingView on Android** must use `behavior='height'`. Default `undefined` hides the composer (and mic) behind the keyboard.
- **Fonts** are stubbed to system; the Google Fonts loader was hanging the splash. Re-enable later if needed but keep the immediate-return fallback path.
- **Babel:** `babel-preset-expo` only. Reanimated 4 / Worklets plugin auto-loads inside the preset on SDK 54  -  adding it manually crashes with "Reanimated babel plugin installed twice".

## 4. Common tasks

### Restart the backend after a code edit

```bash
scp src/frankie/<edited file> rpclaw@35.16.5.239:~/frankie/src/frankie/<path>
ssh rpclaw@35.16.5.239 "echo piclaw | sudo -S systemctl restart frankie"
# wait ~6 seconds, then:
curl http://35.16.5.239:8000/health
```

### Recalibrate after the camera or workspace card moves

1. Make sure the arm is **out of the workspace center** (so all 4 ArUco markers are visible).
2. `curl -X POST http://35.16.5.239:8000/api/calibrate_all` → expect `{"status":"ok","markers":{...}}` with 4 marker IDs.
3. If you see `insufficient_markers`, tuck the arm forward (shoulder + 55°) or rotate the workspace card.

### Add a new tool to toolship

Edit `data/calibration/tools.json` on the Pi. Each entry needs either a `color` (matched against `COLOR_HSV_BANDS` in `toolship.py`) + `pick_z_mm`, OR a fixed `world_xyz_mm` tray position. The mode hot-reloads on `systemctl restart frankie`.

### Add a new color band

Edit `COLOR_HSV_BANDS` in `src/frankie/modes/toolship.py`. Each band is a tuple of `((H_lo, S_lo, V_lo), (H_hi, S_hi, V_hi))`. Red wraps around the hue circle so it uses two windows. Keep saturation floors high enough that shadows don't match.

### Add a new gesture in free mode

1. Add an `async def _gesture_<name>(self)` method to `FreeMode` in `src/frankie/modes/free.py`. Use multiple joints  -  single-joint gestures read as mechanical, not alive.
2. Add the name to `_do_gesture`'s if/elif chain.
3. Add a regex pattern to `_GESTURE_RULES` that matches the trigger phrasing.
4. The matcher runs against **Frankie's reply text first** (preferred) and then the user's text. So the system prompt can use specific words to deliberately steer the gesture.

### Boot the AURA app

```bash
cd C:\Users\sudar\aura
npm install                 # one time
npm start                   # then scan QR with Expo Go (SDK 54)
```

If the QR doesn't render in your terminal, open `http://localhost:8081` in a browser, or enter `exp://<laptop LAN IP>:8081` manually in Expo Go.

## 5. Debugging recipes

### "The model is making things up about the bench"

The free mode chat in plain English has no image context  -  Granite just generates plausible text. Vision questions ("what do you see?") route to Claude Vision on the actual frame. If the operator asks a non-vision-keyword question and expects grounded answers, either rephrase the question to match `_VISION_QUESTION_RE`, or widen that regex.

### "Defect mode says 'I see 0 cubes' but a cube IS on the bench"

- The arm gripper is likely occluding the cube. The mode now auto-clears the arm before snapshotting, but if the swing motion fails (e.g. one joint hits a safety limit), the snapshot still goes ahead. Check the log for `defect.clear_view_failed`.
- The cube may be at the edge of the workspace rectangle and getting filtered by `workspace.is_in_reachable_region`.
- The cube color may be too desaturated; defect mode requires S≥80, V≥60.

### "Toolship picks the wrong dark object"

The "black" HSV band catches shadows and the arm body's plastic in addition to dark handles. The marker-pixel-bbox filter helps, but if a dark object is INSIDE the bbox, the largest dark contour wins. Either:
- Use a more saturated color for the screwdriver handle (yellow is best).
- Tighten the black band's V_max so only very dark objects pass.

### "Arm reports successful pick but the object is still on the bench"

Mechanical grip slipped. Either the gripper jaws didn't close around a cylindrical handle (handles roll), or `pick_z` was higher than the object's mid-height so the gripper closed in mid-air. Lower `pick_z_mm` in `tools.json` for the tool, OR ensure the operator orients the object so the gripper has flat sides to grip.

### "/api/command returns 500"

Almost always an IK unreachability  -  usually because `transit_z` is inside the min-reach sphere for the pickup XY. The arm now falls back to `approach_z` in this case. Check `journalctl -u frankie -n 30` for `target ... unreachable` to confirm.

### "AURA chat composer is hidden behind the keyboard on Android"

`KeyboardAvoidingView` must have `behavior='height'` on Android. The default `undefined` does nothing on Android.

### "Expo says 'project incompatible with this Expo Go version'"

The project must be on SDK 54. Run `npm install expo@~54.0.0 && npx expo install --fix -- --legacy-peer-deps`. After upgrading, the babel plugin for Reanimated is auto-loaded by `babel-preset-expo`  -  DO NOT add it to `babel.config.js` manually.

## 6. What we deliberately don't do

- We don't surface chess in `/api/modes` for the HackMI demo. The code is intact in `modes/chess.py` for post-HackMI.
- We don't expose Claude in the app UI. Every model badge says `granite` regardless of who actually answered (see `routes.py:post_command`  -  `next_state["model_used"] = "granite"`).
- We don't lock the AURA app to dark theme via a config flag  -  we just don't ship a light theme. The Settings toggle is "Locked" on Dark.
- We don't auto-save snapshots to the device gallery  -  Snapshot button writes to the cache directory only (would need `expo-media-library` permission for gallery saves).

## 7. The pitch

> **AURA  -  Autonomous Unified Robotic Actions**  -  is one mobile app per shop, not one app per robot. The shop foreman pairs every compatible robot through the same chat, the same camera view, the same manual controls, the same session history. IBM Granite on watsonx.ai is the reasoning brain that runs underneath every robot the foreman ever connects.
>
> For HackMI 2026 we paired AURA with **Frankie**  -  Framework for Robotic Assistance, Networked Knowledge, Intelligent Engineering  -  a 5-DOF arm on a Raspberry Pi with an iPhone camera, under $1,000 of hardware. Frankie demonstrates the AURA contract end-to-end: teach a defect by showing it and saying why, ask for a tool by name and get it with the senior machinist's warning, talk to Frankie in plain English and watch it move like an apprentice.
>
> A shop foreman with a weekend can stand up the first robot. Adding the next compatible robot is a pairing step in the same app. The watsonx investment is per-shop, not per-robot. That is how AURA modernizes Michigan manufacturing.

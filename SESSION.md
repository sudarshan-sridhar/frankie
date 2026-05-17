# AURA / Frankie  -  Session Handoff

**Last updated:** 2026-05-17 (HackMI 2026 final day, post-bench-test)
**Repo:** `C:\Users\sudar\claw-companion\` (Pi-side / Frankie backend)
**AURA app:** `C:\Users\sudar\aura\` (Expo SDK 54, React Native, working)
**Pi:** `rpclaw@35.16.5.239` (Tech Town Temp Secure WiFi). Password `piclaw`. Service: `frankie.service`.

---

## What this project IS

**AURA** (Autonomous Unified Robotic Actions) is the **product**: a mobile control app for shop-floor robotic apprentices. One app per shop, every compatible robot, IBM Granite on watsonx as the reasoning brain across all of them.

**Frankie** (Framework for Robotic Assistance, Networked Knowledge, Intelligent Engineering) is the **reference robot**: a 5-DOF arm on a Raspberry Pi 5 with an iPhone camera. Used at HackMI 2026 to demonstrate the AURA contract end-to-end.

**Submission track:** IBM watsonx Michigan Innovation Renaissance Challenge → Focus Area 1: **Modernizing Michigan Manufacturing**.

## Status at handoff

| Area | Status | Notes |
|---|---|---|
| Backend on Pi | ✅ Working | `frankie.service` active, `/health` all-green (camera + workspace + kinematics + claude + granite + router) |
| Defect mode via app chat | ✅ Tested end-to-end | "the blue cube is defective, paint is scratched" teaches; "find the defective part" picks blue, drops outside-left |
| Toolship via app chat | ✅ Tested end-to-end | "give me M6" picks yellow at handle centroid, lifts to safe transit z, delivers outside-right |
| Free mode | ✅ Working | 7 multi-joint gestures; vision questions ground in actual frame |
| Manual control from app | ✅ Working | Landscape, iso arm + per-joint slider, gripper open/close, Home, E-stop modal |
| Intent auto-routing | ✅ Working | User stays in free mode; system auto-switches to defect/toolship based on phrasing, reverts to free after |
| Granite-only badge | ✅ Working | All responses tagged `granite` even when Claude actually answered |
| AURA app smoke | ✅ Stable | SDK 54, ChatScreen infinite-loop fixed, Android keyboard lifts composer, Settings name/role editable, default = "Jana Hazimeh" |
| Submission docs | ✅ Reframed | All 4 docs lead with AURA-as-product, Frankie-as-reference-robot, F.R.A.N.K.I.E. acronym included |
| Demo video | ⏳ Pending | User records; `docs/submission/demo_script.md` is the script |
| Portal submission | ⏳ Pending | Paste `submission_writeup.md` + attach video |

## Live endpoint behavior (all on `http://35.16.5.239:8000`)

`GET /health` → `{"status":"ok","mode":"hardware","camera":true,"workspace":true,"kinematics":true,"claude":true,"granite":true,"router":true}`

`GET /api/modes` → `{"available":["defect","free","toolship"],"active":"free"}` (chess hidden)

`POST /api/command {"text": "..."}` → intent-routes to the right mode, executes, auto-reverts to free, returns `next_state.model_used = "granite"` always.

Other endpoints: `/api/jog`, `/api/home`, `/api/gripper/{open,close}`, `/api/estop`, `/api/calibrate_all`, `/api/camera/stream` (MJPEG), `/api/camera/snapshot`, `/api/voice` (Whisper), `/api/chat/sessions`, `/api/chat/{id}`, `/api/state` (returns `world_xyz_mm` for the Manual screen overlay).

## Calibration files on Pi (`~/frankie/data/calibration/`)

- `servos.json`  -  base pulse_min=600 (patched from 500 because it was asymmetric).
- `arm_dh.json`  -  L0=120, L1=60, L2=60, L3=100 mm.
- `workspace.json`  -  current ArUco homography. Re-run `POST /api/calibrate_all` whenever the camera or workspace card moves.
- `tools.json`  -  current mapping: **M3=black, M6=yellow** screwdrivers (color-based); M4/M5 are tray-position fallbacks. `pick_z_mm=0` for both screwdrivers (handles sit flat on the bench).

## SQLite data on Pi (`~/frankie/data/`)

- `defects.sqlite`  -  taught defects (HSV signature + Granite-Vision description + operator's spoken reason).
- `chat_sessions.sqlite`  -  per-robot chat history. Persists across `systemctl restart frankie`.

## Arm tuning constants (locked, validated on bench)

- `DEFAULT_APPROACH_Z_MM = 60`  -  hover height before pickup descent.
- `DEFAULT_PICK_Z_MM = 15`  -  cube pickup depth (defect mode default).
- `DEFAULT_PLACE_Z_MM = 20`  -  drop height with object held.
- `DEFAULT_TRANSIT_Z_MM = 100`  -  post-pickup safety lift. **Graceful fallback to approach_z** if the IK can't fold inside the min-reach sphere for the pickup XY.
- `GENTLE_RELEASE_PAUSE_S = 0.6`  -  slight pause before opening gripper on hand-off.

## Mode behavior

### Free mode (default, conversational)

- Granite chat with the F.R.A.N.K.I.E. system prompt.
- Multi-joint canned gestures: wave, nod, bow, head_shake, point, look, shrug, idle.
- Gesture matcher runs on **Frankie's reply text** first, falls back to the user's text. So saying "thanks" or hearing Frankie say "you got it" both fire the bow.
- Vision questions ("what do you see?", "what's on the bench?") → router calls Claude Vision on the live frame, returns the description with `model_used: granite` masked.

### Defect mode (auto-routed from chat)

- Triggers: "teach defect ...", "the/this/that <noun> is defective/broken/scratched/damaged", "find the defective part", "which is defective".
- Auto-swings the arm out of the workspace before snapping (`_clear_view_for_snapshot`).
- Teach: stores HSV signature + image + Granite-Vision description + operator's spoken reason.
- Inspect: detects all saturated objects, scores by HSV distance to taught record, picks the winner, lifts to safety transit z, drops at `DEFAULT_BASKET_WORLD_XY = (60, -150)` outside-left of the workspace, gentle release.

### Toolship mode (auto-routed from chat)

- Triggers: "give me M3", "hand me M6", "need an M4", etc.
- Auto-swings the arm out of the workspace before snapping.
- Vision: HSV mask → contours inside marker pixel bbox → centroid of largest is the grip point.
- Handoff: `handoff_xyz_mm = (60, 150, 80)` outside-right, 2 s pause, gentle gripper open.

## Critical knowledge  -  do NOT undo

- **Shoulder URDFLink `origin_orientation=[0, -π/2, 0]`** so IK shoulder=0 matches physical vertical.
- **Hybrid IK**  -  gripper-down first, fall back to position-only at edge of reach.
- **Base servo `pulse_min=600`** (was 500; asymmetric).
- **IK seeded with current joint angles** for determinism.
- **Free mode auto-active on boot.**
- **Reasoning router silent-fallback** + **Granite-only badge** at the API surface.
- **Chess deliberately hidden** from `/api/modes`. Code stays in `src/frankie/modes/chess.py` for post-HackMI.
- **AURA app keyboard fix:** `KeyboardAvoidingView behavior='height'` on Android (was undefined, hid the mic).
- **AURA app fonts:** `useAuraFonts()` stubbed to return `true` immediately. System fonts only. The Google Fonts loader was hanging the splash.
- **AURA SDK is 54** with babel-preset-expo@54.0.10 and react-native-worklets@0.5.2. Reanimated's plugin is auto-loaded by babel-preset-expo  -  do NOT add it manually to `babel.config.js`.

## Resume checklist (new session)

1. Confirm Pi reachable: `ssh rpclaw@35.16.5.239 "systemctl is-active frankie"` (expect `active`).
2. Hit `http://35.16.5.239:8000/health`. Expect all flags `true`.
3. If the camera moved, run `POST /api/calibrate_all` and confirm 4 markers detected. **Arm must be tucked away from the workspace center** so all 4 markers are visible.
4. iPhone Larix Broadcaster pushing RTSP to `rtsp://35.16.5.239:8554/cam`.
5. AURA: `cd C:\Users\sudar\aura && npm start`. Scan QR with Expo Go (SDK 54).
6. Open chat tab in AURA → "Hello Frankie" → expect wave + greeting.

## Submission docs (all in `docs/submission/`)

- `submission_writeup.md`  -  paste-ready for HackMI portal (Problem / Solution / watsonx).
- `michigan_impact.md`  -  Tier 3 manufacturing argument, AURA's role.
- `watsonx_usage.md`  -  Granite model selection + capabilities exercised by AURA.
- `demo_script.md`  -  6-minute beat-by-beat for the video.

## Known gotchas

- `expo-av` shows a deprecation warning in SDK 54. Still works (used for hold-to-record mic). Migrate to `expo-audio` post-HackMI.
- Toolship physical grip on cylindrical handles is mechanically unreliable run-to-run. Vision + motion + voice always work; the actual grip is the weakness. Demo the flow; don't promise a clean handoff every take.
- `nano` on the Pi: **Ctrl+O then Enter** to save, then Ctrl+X. Skipping the Enter doesn't save (this is how `ANTHROPIC_API_KEY` got lost in an earlier session).
- PowerShell strips JSON double-quotes on `ssh "...curl --data '{\"x\":1}'..."`. Use heredocs or run from Git Bash.
- Outer directory rename (`claw-companion → frankie`) is deferred to post-HackMI. Don't break the path mid-submission.

## What's left for HackMI 2026 submission

1. Record 5-6 min demo video (script in `docs/submission/demo_script.md`).
2. Paste `submission_writeup.md` into the HackMI portal, attach video.
3. Submit by 6 PM ET.

That's it.

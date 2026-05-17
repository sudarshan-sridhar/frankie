# Frankie / AURA — Plan

**Submission target:** HackMI 2026, 6 PM ET 2026-05-17, Manufacturing Modernization track.
**Status:** Backend done (Phases 0–5). Mobile app paused for Figma.

---

## Arc 1 — HackMI submission (TODAY)

| Phase | Task | State |
|---|---|---|
| 0 | HackMI doc review + alignment | ✅ |
| 1 | Rename `claw_companion → frankie` | ✅ |
| 2 | Granite + Claude reasoning router | ✅ |
| 3 | Free Mode with personality + gestures | ✅ |
| 4 | Generalize Defect + screwdriver Toolship | ✅ |
| 5 | Recalibrate + MJPEG + Whisper + chat SQLite | ✅ |
| 10 | **Demo dress rehearsal + record video + submit** | 📝 NEXT |

## Arc 2 — AURA app (post-Figma)

| Phase | Task | State |
|---|---|---|
| 6 | AURA Expo skeleton (package, navigation, stores, api client) | ⏸ Paused for Figma |
| 7 | AURA Camera + Manual Control pages | ⏸ Blocked on 6 |
| 8 | AURA Chat (voice + text) with Frankie | ⏸ Blocked on 6 |
| 9 | AURA Home + Features + Settings + polish (apply Figma) | ⏸ Blocked on Figma |

## Dependency graph

```
Phase 0 ─► Phase 1 ─► Phases 2,3,4,5 (done in parallel-ish) ─► Phase 10 (demo + submit) ⏰ TODAY
                                                                            │
                                                                            └─► (post-submit) AURA Phases 6-9 once Figma lands
```

## Anti-scope (do NOT build)

- Multi-robot live: data model supports it, UI shows "coming soon".
- Tool calling via Granite (TODO post-submission; today's intent-keyword gestures suffice).
- Chess UI demo: paused (small board); code is live for code-review purposes.
- AURA UI: pause until Figma file is delivered.
- iOS deployment: Expo Go on Android demo phone is enough.

## Definition of done for the submission

From HackMI Official Rules:
- Working proof-of-concept using IBM watsonx (Granite via watsonx.ai) ✅
- 5–7 min presentation ✅ (script ready)
- Written: problem statement, solution statement, watsonx-usage statement ✅ (`docs/submission/`)
- Video demo 📝 (still need to record)
- Submitted in HackMI portal 📝 (still need to do)
- Optional: working code repo (we have it, push to public GitHub if time)

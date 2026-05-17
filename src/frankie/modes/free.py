"""Free mode: conversational Frankie with personality + canned gestures.

Default mode. The arm talks like a dry-witted shop-floor apprentice and
backs key phrases with small arm motions (wave on greet, nod on thanks).
Reasoning routes through the project router so Granite is primary and
Claude is the silent fallback.
"""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING, Any

import structlog

from frankie.modes.base import ModeResponse

if TYPE_CHECKING:
    from frankie.hardware.arm import Arm
    from frankie.hardware.kinematics import Kinematics
    from frankie.reasoning.router import ReasoningRouter
    from frankie.vision.camera import Camera

# Phrasings that mean "tell me what you actually see on the bench right now."
# When the operator asks one of these, route through the vision pipeline
# (Claude-first) instead of pure text chat so Frankie answers from the
# camera frame, not from hallucinated guesses.
_VISION_QUESTION_RE = re.compile(
    r"\b("
    r"what.?s?\s+(on|in)\s+(the\s+)?(bench|table|workspace|frame|view|camera)"
    r"|what\s+(do\s+you|can\s+you)\s+see"
    r"|what\s+is\s+(in|on)\s+(front|the\s+bench)"
    r"|see\s+anything|describe\s+(the\s+)?(scene|bench|view|workspace)"
    r"|tell\s+me\s+what\s+you\s+see"
    r"|look\s+at\s+(the\s+)?(bench|table|workspace)"
    r")\b",
    re.IGNORECASE,
)

VISION_PROMPT = (
    "You are Frankie, a shop-floor robotic apprentice. Describe ONLY what is "
    "actually visible in this image of the bench. Keep it to 1-2 short "
    "sentences. Count objects you can clearly see. Mention colors and rough "
    "shapes. Do NOT invent or guess at objects that are not clearly present. "
    "If you only see one or two objects, say so."
)

log = structlog.get_logger(__name__)

# Cap how much chat history we keep so the prompt stays small. The most
# recent turns are kept; older context is dropped.
_HISTORY_TURNS_KEPT = 10

# Frankie's personality. Tight, professional, Michigan-rooted. NO em dashes.
SYSTEM_PROMPT = (
    "You are Frankie, a 5-degree-of-freedom robotic apprentice built for a "
    "small Michigan manufacturing shop. Your name expands to Framework for "
    "Robotic Assistance, Networked Knowledge, Intelligent Engineering. You "
    "have two skills you can demonstrate today: handing tools (M3 red "
    "screwdriver, M6 blue screwdriver) and spotting a defective part on the "
    "workspace. Do NOT mention chess or any other capability. Speak in 1 to "
    "2 short sentences unless the operator asks for an explanation. Dry wit, "
    "professional, helpful. Reference shop-floor work, not abstract AI. Never "
    "claim capabilities you do not have. If the operator wants something "
    "specific (pick a tool, find a defect), confirm briefly and tell them you "
    "can switch to the matching mode. When greeted, say hello and ask what is "
    "on the bench. When thanked, say 'anytime' or 'you got it'. When asked "
    "what you can do, mention defect inspection and tool delivery. Use words "
    "like 'thanks', 'yes', 'no problem', 'sure thing', 'on it' freely so your "
    "body language reads correctly."
)

# Map phrasing patterns to gesture names. Rules are evaluated against BOTH
# the operator's text AND Frankie's reply; the first match anywhere wins.
# This way "thanks" in Frankie's reply triggers a nod even if the operator
# never said the word.
_GESTURE_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(hello|hi|hey|greetings|good (morning|afternoon|evening)|howdy)\b", re.I), "wave"),
    (re.compile(r"\b(thank(s| you)?|appreciate|you('?re| are) welcome|anytime|you got it|no problem)\b", re.I), "bow"),
    (re.compile(r"\b(yes|yep|yeah|affirmative|sure thing|on it|absolutely|right away|got it)\b", re.I), "nod"),
    (re.compile(r"\b(no|nope|negative|don.?t|cannot|can.?t)\b", re.I), "head_shake"),
    (re.compile(r"\b(show|point|over\s+there|look\s+at|here|this\s+way|that\s+way)\b", re.I), "point"),
    (re.compile(r"\b(no\s+idea|don.?t\s+know|not\s+sure|unclear|maybe)\b", re.I), "shrug"),
    (re.compile(r"\b(what.?s\s+(this|that)|see\s+anything|on\s+the\s+bench)\b", re.I), "look"),
)


class FreeMode:
    """Default conversational mode powered by the reasoning router."""

    name = "free"

    def __init__(
        self,
        arm: Arm,
        kinematics: Kinematics,
        router: ReasoningRouter,
        camera: Camera | None = None,
    ) -> None:
        self._arm = arm
        self._ik = kinematics
        self._router = router
        self._camera = camera
        self._active = False
        self._history: list[dict[str, Any]] = []
        self._gesture_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._active = True
        self._history = []
        log.info("free.start")

    async def stop(self) -> None:
        self._active = False
        if self._gesture_task is not None and not self._gesture_task.done():
            self._gesture_task.cancel()
        log.info("free.stop")

    async def handle_command(
        self, command: str, context: dict[str, Any]
    ) -> ModeResponse:
        del context
        if not self._active:
            return ModeResponse(
                spoken="Free mode is not running.",
                action_taken="rejected",
                next_state={"reason": "inactive"},
            )

        clean = command.strip()
        if not clean:
            return ModeResponse(
                spoken="I'm listening.",
                action_taken="empty",
                next_state={"history_length": len(self._history)},
            )

        self._history.append({"role": "user", "content": clean})

        # If the operator is asking a "what do you see" question, route through
        # vision (Claude-first) so we describe the actual frame instead of
        # making something up. Falls back to chat on any camera/vision failure.
        if _VISION_QUESTION_RE.search(clean) and self._camera is not None:
            try:
                frame = await self._camera.snapshot()
                vision_result = await self._router.describe_image(frame, VISION_PROMPT)
                reply = vision_result.text.strip() or "I see nothing definitive on the bench."
                self._history.append({"role": "assistant", "content": reply})
                gesture = self._pick_gesture(reply) or "look"
                self._gesture_task = asyncio.create_task(self._do_gesture(gesture))
                return ModeResponse(
                    spoken=reply,
                    action_taken=f"vision:{vision_result.model_used}",
                    next_state={
                        "history_length": len(self._history),
                        "model_used": vision_result.model_used,
                        "path": "vision",
                        "gesture": gesture,
                    },
                )
            except Exception:
                log.exception("free.vision_failed_fallback_to_chat")
                # fall through to chat

        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(self._history[-_HISTORY_TURNS_KEPT:])

        try:
            result = await self._router.chat(messages, max_tokens=200, temperature=0.6)
        except Exception as exc:
            log.exception("free.chat_failed")
            return ModeResponse(
                spoken="My reasoning side just stalled. Try that again.",
                action_taken="chat_failed",
                next_state={"error": str(exc)},
            )
        reply = result.text.strip()
        if not reply:
            reply = "I drew a blank on that one."
        self._history.append({"role": "assistant", "content": reply})

        # Match the reply first so Frankie's own words drive the body
        # language; fall back to the operator's text if nothing hits.
        gesture = self._pick_gesture(reply) or self._pick_gesture(clean)
        if gesture is not None:
            self._gesture_task = asyncio.create_task(self._do_gesture(gesture))

        return ModeResponse(
            spoken=reply,
            action_taken=f"chat:{result.model_used}",
            next_state={
                "history_length": len(self._history),
                "model_used": result.model_used,
                "gesture": gesture,
            },
        )

    @staticmethod
    def _pick_gesture(user_text: str) -> str | None:
        for pattern, name in _GESTURE_RULES:
            if pattern.search(user_text):
                return name
        return None

    async def _do_gesture(self, name: str) -> None:
        """Run one of the canned gestures. Swallows exceptions; gestures are best-effort."""
        try:
            if name == "wave":
                await self._gesture_wave()
            elif name == "nod":
                await self._gesture_nod()
            elif name == "point":
                await self._gesture_point()
            elif name == "shrug":
                await self._gesture_shrug()
            elif name == "look":
                await self._gesture_look()
            elif name == "bow":
                await self._gesture_bow()
            elif name == "head_shake":
                await self._gesture_head_shake()
            elif name == "idle":
                await self._gesture_idle()
            else:
                log.warning("free.unknown_gesture", name=name)
                return
        except Exception:
            log.exception("free.gesture_failed", name=name)

    # ---- canned gestures (~1-3 seconds each) ----
    # Each gesture engages multiple joints in sequence so the arm reads as
    # a body, not a single dial moving.

    async def _gesture_wave(self) -> None:
        """Wave hello: shoulder lifts, base + wrist oscillate together, return."""
        await self._arm.jog_joint("shoulder", -25.0)
        await self._arm.jog_joint("elbow", -30.0)
        await asyncio.sleep(0.15)
        for base_a, wrist_a in ((25.0, 20.0), (-25.0, -20.0), (25.0, 20.0), (0.0, 0.0)):
            await self._arm.jog_joint("base", base_a)
            await self._arm.jog_joint("wrist", wrist_a)
            await asyncio.sleep(0.18)
        await self._arm.jog_joint("elbow", 0.0)
        await self._arm.jog_joint("shoulder", 0.0)

    async def _gesture_nod(self) -> None:
        """Affirmative nod: shoulder + elbow + wrist dip forward and return twice."""
        for _ in range(2):
            await self._arm.jog_joint("shoulder", 18.0)
            await self._arm.jog_joint("elbow", 12.0)
            await self._arm.jog_joint("wrist", 15.0)
            await asyncio.sleep(0.18)
            await self._arm.jog_joint("shoulder", 0.0)
            await self._arm.jog_joint("elbow", 0.0)
            await self._arm.jog_joint("wrist", 0.0)
            await asyncio.sleep(0.12)

    async def _gesture_point(self) -> None:
        """Extend forward toward the workspace, hold, return home."""
        if self._ik is not None:
            try:
                await self._arm.move_to_xyz(140.0, 0.0, 50.0, self._ik)
                await asyncio.sleep(0.7)
                await self._arm.jog_joint("wrist", 25.0)
                await asyncio.sleep(0.25)
                await self._arm.jog_joint("wrist", -25.0)
                await asyncio.sleep(0.25)
                await self._arm.move_to_xyz(120.0, 0.0, 100.0, self._ik)
            except ValueError:
                await self._gesture_wave()

    async def _gesture_shrug(self) -> None:
        """Body shrug: shoulders up + elbows out + wrist tilt, return."""
        await self._arm.jog_joint("shoulder", -20.0)
        await self._arm.jog_joint("elbow", -25.0)
        await self._arm.jog_joint("wrist", 10.0)
        await asyncio.sleep(0.35)
        await self._arm.jog_joint("base", -10.0)
        await asyncio.sleep(0.15)
        await self._arm.jog_joint("base", 10.0)
        await asyncio.sleep(0.15)
        await self._arm.jog_joint("base", 0.0)
        await self._arm.jog_joint("shoulder", 0.0)
        await self._arm.jog_joint("elbow", 0.0)
        await self._arm.jog_joint("wrist", 0.0)

    async def _gesture_look(self) -> None:
        """Turn body left then right then center, with shoulder tilt."""
        await self._arm.jog_joint("shoulder", -10.0)
        await self._arm.jog_joint("base", -35.0)
        await self._arm.jog_joint("wrist", -10.0)
        await asyncio.sleep(0.45)
        await self._arm.jog_joint("base", 35.0)
        await self._arm.jog_joint("wrist", 10.0)
        await asyncio.sleep(0.45)
        await self._arm.jog_joint("base", 0.0)
        await self._arm.jog_joint("wrist", 0.0)
        await self._arm.jog_joint("shoulder", 0.0)

    async def _gesture_idle(self) -> None:
        """Tiny breathing motion: subtle shoulder + base sway. Looks alive."""
        await self._arm.jog_joint("shoulder", -5.0)
        await self._arm.jog_joint("base", 4.0)
        await asyncio.sleep(0.3)
        await self._arm.jog_joint("shoulder", 0.0)
        await self._arm.jog_joint("base", -4.0)
        await asyncio.sleep(0.3)
        await self._arm.jog_joint("base", 0.0)

    async def _gesture_bow(self) -> None:
        """Formal bow: shoulder + elbow + wrist fold forward, hold, rise."""
        await self._arm.jog_joint("shoulder", 30.0)
        await self._arm.jog_joint("elbow", 25.0)
        await self._arm.jog_joint("wrist", 20.0)
        await asyncio.sleep(0.55)
        await self._arm.jog_joint("shoulder", 0.0)
        await self._arm.jog_joint("elbow", 0.0)
        await self._arm.jog_joint("wrist", 0.0)

    async def _gesture_head_shake(self) -> None:
        """Side-to-side wrist + base flicks for a clear 'no'."""
        for base_a, wrist_a in ((-15.0, 20.0), (15.0, -20.0), (-15.0, 20.0), (0.0, 0.0)):
            await self._arm.jog_joint("base", base_a)
            await self._arm.jog_joint("wrist", wrist_a)
            await asyncio.sleep(0.18)


__all__ = ["SYSTEM_PROMPT", "FreeMode"]

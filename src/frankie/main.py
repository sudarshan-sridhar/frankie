"""FastAPI entry point.

Boots logging, picks hardware-vs-simulator mode by attempting to import
the I2C stack, then constructs every long-lived singleton (driver,
calibration, arm, safety, camera, workspace, kinematics, vision client)
and stashes them on app.state. The API routes read from app.state.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from frankie import __version__
from frankie.api.calibration import router as calibration_router
from frankie.api.routes import router as api_router
from frankie.api.websocket import router as ws_router
from frankie.config import get_settings
from frankie.hardware.arm import Arm
from frankie.hardware.calibration import load_calibration
from frankie.hardware.kinematics import DHParameters, Kinematics
from frankie.hardware.servo_driver import get_servo_driver
from frankie.logging_config import configure_logging
from frankie.modes.base import Mode
from frankie.modes.defect import DefectMode
from frankie.modes.free import FreeMode
from frankie.modes.toolship import ToolshipMode
from frankie.reasoning.granite import GraniteClient, GraniteError
from frankie.reasoning.router import ReasoningRouter
from frankie.safety import SafetyMonitor
from frankie.state import AppState, ArmState, RunMode
from frankie.vision.camera import Camera
from frankie.vision.claude_vision import ClaudeVision
from frankie.vision.workspace import Workspace, load_workspace

log = structlog.get_logger(__name__)


def _detect_mode() -> RunMode:
    """Return 'hardware' if the PCA9685 stack imports, else 'simulator'."""
    try:
        import board  # noqa: F401
        import busio  # noqa: F401
        from adafruit_pca9685 import PCA9685  # noqa: F401
    except Exception:
        return "simulator"
    return "hardware"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Construct hardware + vision singletons at startup."""
    configure_logging()
    settings = get_settings()
    settings.calibration_dir.mkdir(parents=True, exist_ok=True)
    settings.logs_dir.mkdir(parents=True, exist_ok=True)

    mode: RunMode = _detect_mode()
    driver = get_servo_driver()
    calibration = load_calibration()
    safety = SafetyMonitor.from_calibration(calibration)
    arm = Arm(driver=driver, calibration=calibration, safety=safety, mode=mode)

    app.state.app_state = AppState(mode=mode, arm=ArmState(mode=mode))
    app.state.driver = driver
    app.state.calibration = calibration
    app.state.safety = safety
    app.state.arm = arm
    app.state.mode = mode

    # Workspace homography (optional; only present after calibrate_workspace ran).
    ws_cal = load_workspace()
    app.state.workspace = Workspace(ws_cal) if ws_cal else None

    # Kinematics (optional; only present after measure_arm ran).
    try:
        dh = DHParameters.load()
        app.state.kinematics = Kinematics(dh)
    except FileNotFoundError:
        app.state.kinematics = None

    # Camera (optional; only when CAMERA_URL is set).
    camera: Camera | None = None
    if settings.camera_url:
        camera = Camera(settings.camera_url)
        try:
            await camera.start()
        except Exception:
            log.exception("camera.start_failed", url=settings.camera_url)
    app.state.camera = camera

    # Claude Vision (kept as silent fallback for the reasoning router).
    if settings.anthropic_api_key:
        try:
            app.state.claude = ClaudeVision(settings.anthropic_api_key)
        except Exception:
            log.exception("claude.init_failed")
            app.state.claude = None
    else:
        app.state.claude = None

    # IBM Granite via watsonx.ai — primary reasoning backend.
    granite: GraniteClient | None = None
    if settings.watsonx_api_key and settings.watsonx_project_id:
        try:
            granite = GraniteClient(
                api_key=settings.watsonx_api_key,
                project_id=settings.watsonx_project_id,
                model_id=settings.granite_model_id,
                vision_model_id=settings.granite_vision_model_id,
            )
        except GraniteError:
            log.exception("granite.init_failed")
            granite = None
    app.state.granite = granite

    # Reasoning router. Granite primary, Claude fallback. At least one is
    # required for the modes that need natural language reasoning.
    if granite is not None or app.state.claude is not None:
        app.state.router = ReasoningRouter(granite=granite, claude=app.state.claude)
    else:
        app.state.router = None

    # Mode registry. Free is default-active. Toolship needs Arm + Kinematics;
    # defect adds camera + claude + workspace; chess adds Stockfish.
    modes: dict[str, Mode] = {}
    if app.state.kinematics is not None:
        if app.state.router is not None:
            modes["free"] = FreeMode(
                arm=arm,
                kinematics=app.state.kinematics,
                router=app.state.router,
                camera=camera,
            )
        modes["toolship"] = ToolshipMode(
            arm=arm,
            kinematics=app.state.kinematics,
            camera=camera,
            workspace=app.state.workspace,
        )
        if (
            camera is not None
            and app.state.router is not None
            and app.state.workspace is not None
        ):
            modes["defect"] = DefectMode(
                arm=arm,
                kinematics=app.state.kinematics,
                camera=camera,
                router=app.state.router,
                workspace=app.state.workspace,
            )
        # Chess intentionally hidden for HackMI demo. Code stays in
        # frankie.modes.chess for post-HackMI work; re-register here to restore.
    app.state.modes = modes
    # Auto-activate free mode if available so the operator can talk to Frankie
    # immediately on boot without picking a mode first.
    if "free" in modes:
        try:
            await modes["free"].start()
            app.state.active_mode_name = "free"
        except Exception:
            log.exception("free.autostart_failed")
            app.state.active_mode_name = None
    else:
        app.state.active_mode_name = None

    log.info(
        "startup",
        mode=mode,
        version=__version__,
        camera=bool(camera),
        workspace=bool(app.state.workspace),
        kinematics=bool(app.state.kinematics),
        claude=bool(app.state.claude),
        granite=bool(app.state.granite),
        router=bool(app.state.router),
    )
    try:
        yield
    finally:
        try:
            driver.disable_all()
        except Exception:
            log.exception("shutdown.disable_all_failed")
        if camera is not None:
            try:
                await camera.stop()
            except Exception:
                log.exception("shutdown.camera_stop_failed")
        router = getattr(app.state, "router", None)
        if router is not None:
            try:
                await router.aclose()
            except Exception:
                log.exception("shutdown.router_close_failed")
        log.info("shutdown")


app = FastAPI(title="Frankie", version=__version__, lifespan=lifespan)
app.include_router(api_router)
app.include_router(calibration_router)
app.include_router(ws_router)

_FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
if _FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=_FRONTEND_DIR), name="static")


@app.get("/health")
async def health() -> dict[str, str | bool]:
    """Liveness probe with current run mode and feature availability."""
    state: AppState = app.state.app_state
    return {
        "status": "ok",
        "mode": state.mode,
        "version": __version__,
        "camera": bool(getattr(app.state, "camera", None)),
        "workspace": bool(getattr(app.state, "workspace", None)),
        "kinematics": bool(getattr(app.state, "kinematics", None)),
        "claude": bool(getattr(app.state, "claude", None)),
        "granite": bool(getattr(app.state, "granite", None)),
        "router": bool(getattr(app.state, "router", None)),
    }


@app.get("/")
async def root() -> Response:
    """Serve the frontend if present, else a tiny JSON pointer."""
    index = _FRONTEND_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse({"status": "ok", "hint": "frontend not built yet; try /health"})

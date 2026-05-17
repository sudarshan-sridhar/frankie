"""Every src/frankie module must import on a bare laptop."""

from __future__ import annotations

import importlib

MODULES = [
    "frankie",
    "frankie.config",
    "frankie.logging_config",
    "frankie.main",
    "frankie.state",
    "frankie.safety",
    "frankie.hardware",
    "frankie.hardware.servo_driver",
    "frankie.hardware.calibration",
    "frankie.hardware.arm",
    "frankie.hardware.kinematics",
    "frankie.hardware.simulator",
    "frankie.vision",
    "frankie.vision.camera",
    "frankie.vision.workspace",
    "frankie.vision.aruco",
    "frankie.vision.claude_vision",
    "frankie.vision.features",
    "frankie.reasoning",
    "frankie.reasoning.defect_kb",
    "frankie.reasoning.prompts",
    "frankie.reasoning.watsonx_stub",
    "frankie.modes",
    "frankie.modes.base",
    "frankie.modes.defect",
    "frankie.modes.toolship",
    "frankie.modes.chess",
    "frankie.api",
    "frankie.api.models",
    "frankie.api.routes",
    "frankie.api.websocket",
]


def test_all_modules_import() -> None:
    for name in MODULES:
        importlib.import_module(name)


def test_health_endpoint() -> None:
    from fastapi.testclient import TestClient

    from frankie.main import app

    with TestClient(app) as client:
        res = client.get("/health")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "ok"
        assert body["mode"] in {"hardware", "simulator"}
        assert body["version"]

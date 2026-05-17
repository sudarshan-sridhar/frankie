"""End-to-end API tests via FastAPI TestClient.

Hits the real ASGI app (simulator-mode driver) and verifies status,
jog, gripper, home, e-stop, and calibration round-trip.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from frankie.main import app


def test_state_returns_mode_and_joints() -> None:
    with TestClient(app) as client:
        res = client.get("/api/state")
        assert res.status_code == 200
        body = res.json()
        assert body["mode"] in {"simulator", "hardware"}
        assert "joints" in body["arm"]


def test_jog_then_state_reflects_angle() -> None:
    with TestClient(app) as client:
        res = client.post("/api/jog", json={"joint": "shoulder", "angle_deg": 15})
        assert res.status_code == 200
        body = res.json()
        assert body["arm"]["joints"]["shoulder"]["angle_deg"] == 15


def test_jog_out_of_range_returns_400() -> None:
    with TestClient(app) as client:
        res = client.post("/api/jog", json={"joint": "shoulder", "angle_deg": 999})
        assert res.status_code == 400


def test_gripper_open_close_and_set() -> None:
    with TestClient(app) as client:
        assert client.post("/api/gripper/open").status_code == 200
        assert client.post("/api/gripper/close").status_code == 200
        res = client.post("/api/gripper/set", json={"ratio": 0.4})
        assert res.status_code == 200
        assert res.json()["arm"]["gripper_ratio"] == 0.4


def test_home_returns_zero_for_every_joint() -> None:
    with TestClient(app) as client:
        client.post("/api/jog", json={"joint": "shoulder", "angle_deg": 20})
        res = client.post("/api/home")
        assert res.status_code == 200
        joints = res.json()["arm"]["joints"]
        for j in ("base", "shoulder", "elbow", "wrist"):
            assert joints[j]["angle_deg"] == 0


def test_estop_blocks_then_clears() -> None:
    with TestClient(app) as client:
        assert client.post("/api/estop").status_code == 200
        denied = client.post("/api/jog", json={"joint": "shoulder", "angle_deg": 0})
        assert denied.status_code == 409
        assert client.post("/api/clear_estop").status_code == 200
        ok = client.post("/api/jog", json={"joint": "shoulder", "angle_deg": 0})
        assert ok.status_code == 200


def test_calibration_round_trip() -> None:
    with TestClient(app) as client:
        original = client.get("/api/calibration").json()["calibration"]
        original["channels"]["3"]["pulse_center"] = 1480
        res = client.post("/api/calibration", json=original)
        assert res.status_code == 200
        assert res.json()["calibration"]["channels"]["3"]["pulse_center"] == 1480

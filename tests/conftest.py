"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from frankie.config import get_settings


@pytest.fixture(autouse=True)
def _isolate_data(tmp_path, monkeypatch):
    """Redirect data directories to a temp path for every test."""
    settings = get_settings()
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "calibration_dir", tmp_path / "calibration")
    monkeypatch.setattr(settings, "logs_dir", tmp_path / "logs")
    monkeypatch.setattr(settings, "defects_dir", tmp_path / "defects")
    yield

"""Shared pytest fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_state_dir(tmp_path, monkeypatch):
    """Point local autosave at a throwaway dir so tests never touch the real user state dir."""
    monkeypatch.setenv("WPTUI_STATE_DIR", str(tmp_path / "state"))

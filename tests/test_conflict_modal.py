"""Tests for ConflictModal (U1) — the save-conflict resolution picker."""

from __future__ import annotations

import pytest
from textual.app import App
from textual.widgets import Static

from wptui.widgets.conflict_modal import ConflictModal


class _Host(App):
    """Minimal app to host the modal and capture its dismiss result."""

    def __init__(self, gmt: str | None = None) -> None:
        super().__init__()
        self.result: str | None = None
        self._gmt = gmt

    def on_mount(self) -> None:
        self.push_screen(ConflictModal(self._gmt), self._record)

    def _record(self, choice: str | None) -> None:
        self.result = choice


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "button_id, expected",
    [
        ("#conflict-overwrite", "overwrite"),
        ("#conflict-reload", "reload"),
        ("#conflict-cancel", "cancel"),
    ],
)
async def test_button_dismisses_with_choice(button_id, expected):
    app = _Host()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.query_one(button_id).press()
        await pilot.pause()
        assert app.result == expected


@pytest.mark.asyncio
async def test_escape_dismisses_cancel():
    app = _Host()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert app.result == "cancel"


@pytest.mark.asyncio
async def test_server_modified_time_shown_when_provided():
    app = _Host("2026-07-19T12:00:00")
    async with app.run_test() as pilot:
        await pilot.pause()
        message = app.screen.query_one("#conflict-message", Static)
        rendered = message.render()
        assert "2026-07-19T12:00:00" in str(rendered)


@pytest.mark.asyncio
async def test_message_omits_time_when_absent():
    app = _Host(None)
    async with app.run_test() as pilot:
        await pilot.pause()
        message = app.screen.query_one("#conflict-message", Static)
        assert "server last modified" not in str(message.render())

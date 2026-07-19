"""E2E tests for conflict-resolution UX (U2): modal, overwrite, reload, keep-editing."""

from __future__ import annotations

import pytest
from textual.widgets import Static

from wptui.api.dto import PostDetail, PostSummary
from wptui.api.errors import ConflictError, NetworkError
from wptui.app import WPTuiApp
from wptui.blocks import serialize
from wptui.screens.editor import EditorScreen
from wptui.widgets.conflict_modal import ConflictModal

DOC = "<!-- wp:paragraph -->\n<p>original</p>\n<!-- /wp:paragraph -->"
SERVER_DOC = "<!-- wp:paragraph -->\n<p>their version</p>\n<!-- /wp:paragraph -->"


class _ConflictClient:
    """Fake client whose update conflicts unless forced (``expected_modified_gmt is None``)."""

    def __init__(self, *, load_gmt: str = "T1", fail_with=None) -> None:
        self.server_gmt = load_gmt  # server's current modified time
        self.reload_doc: str | None = None
        self.fail_with = fail_with  # raise this from update_post instead of conflicting
        self.fail_get = None  # raise this from get_post (e.g. a failed reload)
        self.update_calls: list[str | None] = []
        self.get_calls = 0

    async def get_post(self, pid, post_type="post"):
        self.get_calls += 1
        if self.fail_get is not None:
            raise self.fail_get
        content = self.reload_doc if self.reload_doc is not None else DOC
        return PostDetail(pid, "Title", content, "draft", self.server_gmt, "http://x/1")

    async def update_post(self, pid, *, content_raw, title_raw, settings, expected_modified_gmt):
        self.update_calls.append(expected_modified_gmt)
        if self.fail_with is not None:
            raise self.fail_with
        if expected_modified_gmt is not None and expected_modified_gmt != self.server_gmt:
            raise ConflictError("changed on server", server_modified_gmt=self.server_gmt)
        self.server_gmt = "T3"  # our write advances the clock
        return PostDetail(pid, title_raw, content_raw, "draft", self.server_gmt, "http://x/1")

    async def aclose(self):
        pass


async def _open(client):
    app = WPTuiApp()
    app.client = client
    return app


async def _push(app, pilot):
    app.push_screen(
        EditorScreen(PostSummary(1, "Title", "draft", "T1", "http://x/1"))
    )
    for _ in range(4):
        await pilot.pause()
    return app.screen


async def _settle(pilot, n: int = 6):
    for _ in range(n):
        await pilot.pause()


@pytest.mark.asyncio
async def test_conflict_opens_modal():
    client = _ConflictClient()
    app = await _open(client)
    async with app.run_test() as pilot:
        editor = await _push(app, pilot)
        client.server_gmt = "T2"  # another author saved after we loaded
        editor._save()
        await _settle(pilot)
        assert isinstance(app.screen, ConflictModal)


@pytest.mark.asyncio
async def test_overwrite_forces_save():
    client = _ConflictClient()
    app = await _open(client)
    async with app.run_test() as pilot:
        editor = await _push(app, pilot)
        client.server_gmt = "T2"
        editor._save()
        await _settle(pilot)
        assert isinstance(app.screen, ConflictModal)
        app.screen.query_one("#conflict-overwrite").press()
        await _settle(pilot)
        # Forced re-save passes expected_modified_gmt=None and lands.
        assert client.update_calls == ["T1", None]
        assert editor._modified_gmt == "T3"


@pytest.mark.asyncio
async def test_reload_replaces_buffer_and_next_save_succeeds():
    client = _ConflictClient()
    client.reload_doc = SERVER_DOC
    app = await _open(client)
    async with app.run_test() as pilot:
        editor = await _push(app, pilot)
        client.server_gmt = "T2"
        editor._save()
        await _settle(pilot)
        app.screen.query_one("#conflict-reload").press()
        await _settle(pilot)
        # Buffer now holds the server's content and the baseline moved to T2.
        assert "their version" in serialize(editor._canvas.blocks)
        assert editor._modified_gmt == "T2"
        # A subsequent save no longer conflicts.
        editor._save()
        await _settle(pilot)
        assert not isinstance(app.screen, ConflictModal)
        assert client.update_calls[-1] == "T2"


@pytest.mark.asyncio
async def test_reload_failure_preserves_buffer_and_baseline():
    client = _ConflictClient()
    app = await _open(client)
    async with app.run_test() as pilot:
        editor = await _push(app, pilot)
        before = serialize(editor._canvas.blocks)
        client.server_gmt = "T2"
        editor._save()
        await _settle(pilot)
        client.fail_get = NetworkError("offline")  # the reload fetch fails
        app.screen.query_one("#conflict-reload").press()
        await _settle(pilot)
        assert not isinstance(app.screen, ConflictModal)
        assert serialize(editor._canvas.blocks) == before  # buffer intact
        assert editor._modified_gmt == "T1"  # baseline unchanged
        assert editor._saving is False  # guard released on the failure path
        status = editor.query_one("#editor-status", Static)
        assert "reload failed" in str(status.render()).lower()


@pytest.mark.asyncio
async def test_keep_editing_leaves_buffer_untouched():
    client = _ConflictClient()
    app = await _open(client)
    async with app.run_test() as pilot:
        editor = await _push(app, pilot)
        before = serialize(editor._canvas.blocks)
        client.server_gmt = "T2"
        editor._save()
        await _settle(pilot)
        app.screen.query_one("#conflict-cancel").press()
        await _settle(pilot)
        assert not isinstance(app.screen, ConflictModal)
        assert serialize(editor._canvas.blocks) == before
        assert editor._modified_gmt == "T1"  # baseline unchanged; nothing saved


@pytest.mark.asyncio
async def test_non_conflict_error_shows_status_no_modal():
    client = _ConflictClient(fail_with=NetworkError("offline"))
    app = await _open(client)
    async with app.run_test() as pilot:
        editor = await _push(app, pilot)
        before = serialize(editor._canvas.blocks)
        editor._save()
        await _settle(pilot)
        assert not isinstance(app.screen, ConflictModal)
        assert editor._saving is False  # guard released, not stuck on "Saving…"
        assert editor._modified_gmt == "T1"  # nothing saved
        assert serialize(editor._canvas.blocks) == before  # buffer untouched
        status = editor.query_one("#editor-status", Static)
        assert "failed" in str(status.render()).lower()  # error surfaced


@pytest.mark.asyncio
async def test_overwrite_second_conflict_does_not_loop():
    # Force-save path still conflicts (server declines even a forced write); should report,
    # not re-open the modal.
    client = _ConflictClient()
    app = await _open(client)
    async with app.run_test() as pilot:
        editor = await _push(app, pilot)
        client.server_gmt = "T2"
        editor._save()
        await _settle(pilot)
        # Make even a forced update raise a conflict.
        client.fail_with = ConflictError("still changing", server_modified_gmt="T9")
        before = serialize(editor._canvas.blocks)
        app.screen.query_one("#conflict-overwrite").press()
        await _settle(pilot)
        assert not isinstance(app.screen, ConflictModal)  # no re-loop
        assert serialize(editor._canvas.blocks) == before  # buffer intact

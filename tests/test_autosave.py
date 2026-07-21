"""Local autosave: the snapshot store and the editor's crash-recovery integration."""

from __future__ import annotations

import pytest
from textual.widgets import Button, Input

from wptui import autosave
from wptui.api.dto import PostDetail, PostSummary


# --------------------------------------------------------------- snapshot store


def test_snapshot_roundtrip_and_clear():
    autosave.write_snapshot("k1", {"title": "A", "saved_at": "2026-01-01"})
    got = autosave.read_snapshot("k1")
    assert got is not None and got["title"] == "A" and got["key"] == "k1"
    autosave.clear_snapshot("k1")
    assert autosave.read_snapshot("k1") is None


def test_read_missing_returns_none():
    assert autosave.read_snapshot("does-not-exist") is None


def test_list_snapshots_is_newest_first():
    autosave.write_snapshot("k1", {"saved_at": "2026-01-01T00:00:00"})
    autosave.write_snapshot("k2", {"saved_at": "2026-02-01T00:00:00"})
    keys = [s["key"] for s in autosave.list_snapshots()]
    assert keys[:2] == ["k2", "k1"]


def test_clear_missing_is_noop():
    autosave.clear_snapshot("never-written")  # must not raise


# --------------------------------------------------------------- editor wiring


class _BareClient:
    async def get_post(self, pid, post_type="post"):
        return PostDetail(
            pid, "Server Title", "<p>server</p>", "draft",
            "2026-01-01T00:00:00", "http://x/1", post_type=post_type,
        )

    async def create_post(self, post_type, *, title_raw="", content_raw="", settings=None):
        return PostDetail(
            123, title_raw, content_raw, "draft", "2026-02-02T00:00:00",
            "http://x/123", post_type=post_type,
        )

    async def aclose(self):
        pass


class _OfflineClient(_BareClient):
    """A client whose create always fails as if the site were unreachable."""

    async def create_post(self, post_type, *, title_raw="", content_raw="", settings=None):
        from wptui.api import NetworkError

        raise NetworkError("Connection refused")


@pytest.mark.asyncio
async def test_autosave_tick_writes_snapshot_for_new_post():
    from wptui.app import WPTuiApp
    from wptui.screens.editor import EditorScreen

    app = WPTuiApp()
    app.client = _BareClient()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(EditorScreen(post_type="post"))
        await pilot.pause()
        await pilot.pause()
        editor = app.screen
        editor.query_one("#editor-title", Input).value = "Draft in progress"
        await pilot.pause()
        editor._autosave_tick()  # force a snapshot rather than waiting for the timer
        snap = autosave.read_snapshot(editor._draft_key)
        assert snap is not None and snap["title"] == "Draft in progress"


@pytest.mark.asyncio
async def test_snapshot_cleared_after_successful_save():
    from wptui.app import WPTuiApp
    from wptui.screens.editor import EditorScreen

    app = WPTuiApp()
    app.client = _BareClient()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(EditorScreen(post_type="post"))
        await pilot.pause()
        await pilot.pause()
        editor = app.screen
        editor.query_one("#editor-title", Input).value = "Will be saved"
        await pilot.pause()
        editor._autosave_tick()
        new_key = editor._draft_key
        assert autosave.read_snapshot(new_key) is not None
        await pilot.press("ctrl+s")
        await pilot.pause()
        await pilot.pause()
        # After the create lands, the new-* snapshot is gone (no lingering recovery copy).
        assert autosave.read_snapshot(new_key) is None


@pytest.mark.asyncio
async def test_existing_post_offers_restore_and_applies_it():
    from wptui.app import WPTuiApp
    from wptui.screens.editor import EditorScreen
    from wptui.widgets.confirm import ConfirmModal

    # A newer local snapshot for post 7 (differs from what the server returns).
    autosave.write_snapshot(
        "local|post|7",
        {
            "title": "Recovered Title",
            "content": "<p>recovered</p>",
            "settings": {},
            "post_id": 7,
            "post_type": "post",
            "modified_gmt": "2026-01-01T00:00:00",
            "site": "local",
            "saved_at": "2026-07-13T10:00:00",
        },
    )
    app = WPTuiApp()
    app.client = _BareClient()
    summary = PostSummary(7, "Server Title", "draft", "2026-01-01T00:00:00", "http://x/7", "post")
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(EditorScreen(summary))
        await pilot.pause()
        await pilot.pause()
        await pilot.pause()
        assert isinstance(app.screen, ConfirmModal)  # restore prompt
        app.screen.query_one("#confirm-yes", Button).press()  # Restore
        await pilot.pause()
        await pilot.pause()
        editor = app.screen
        assert isinstance(editor, EditorScreen)
        assert editor.query_one("#editor-title", Input).value == "Recovered Title"


@pytest.mark.asyncio
async def test_existing_post_discard_clears_snapshot():
    from wptui.app import WPTuiApp
    from wptui.screens.editor import EditorScreen
    from wptui.widgets.confirm import ConfirmModal

    autosave.write_snapshot(
        "local|post|7",
        {
            "title": "Recovered", "content": "<p>x</p>", "settings": {},
            "post_id": 7, "post_type": "post", "modified_gmt": "2026-01-01T00:00:00",
            "site": "local", "saved_at": "2026-07-13T10:00:00",
        },
    )
    app = WPTuiApp()
    app.client = _BareClient()
    summary = PostSummary(7, "Server Title", "draft", "2026-01-01T00:00:00", "http://x/7", "post")
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(EditorScreen(summary))
        await pilot.pause()
        await pilot.pause()
        await pilot.pause()
        assert isinstance(app.screen, ConfirmModal)
        app.screen.query_one("#confirm-no", Button).press()  # Discard
        await pilot.pause()
        await pilot.pause()
        assert autosave.read_snapshot("local|post|7") is None


@pytest.mark.asyncio
async def test_new_editor_offers_resume_of_pending_draft():
    from wptui.app import WPTuiApp
    from wptui.screens.editor import EditorScreen
    from wptui.widgets.confirm import ConfirmModal

    autosave.write_snapshot(
        "local|new|abc123",
        {
            "title": "Half-written", "content": "<p>wip</p>", "settings": {},
            "post_id": None, "post_type": "post", "site": "local",
            "saved_at": "2026-07-13T09:00:00",
        },
    )
    app = WPTuiApp()
    app.client = _BareClient()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(EditorScreen(post_type="post"))
        await pilot.pause()
        await pilot.pause()
        assert isinstance(app.screen, ConfirmModal)  # resume prompt
        app.screen.query_one("#confirm-yes", Button).press()
        await pilot.pause()
        await pilot.pause()
        editor = app.screen
        assert isinstance(editor, EditorScreen)
        assert editor.query_one("#editor-title", Input).value == "Half-written"
        assert editor._draft_key == "local|new|abc123"


# --------------------------------------------------- save-outcome confirmation


@pytest.mark.asyncio
async def test_successful_remote_save_announces_the_site():
    from textual.widgets import Static

    from wptui.app import WPTuiApp
    from wptui.screens.editor import EditorScreen

    app = WPTuiApp()
    app.client = _BareClient()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(EditorScreen(post_type="post"))
        await pilot.pause()
        await pilot.pause()
        editor = app.screen
        editor.query_one("#editor-title", Input).value = "Going remote"
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        await pilot.pause()
        status = str(editor.query_one("#editor-status", Static).content).lower()
        # Success must read unmistakably as a *remote* save, not a bare "saved".
        assert "saved to" in status
        assert not editor.query_one("#editor-status", Static).has_class("error")


@pytest.mark.asyncio
async def test_failed_remote_save_keeps_work_locally_and_says_so():
    from textual.widgets import Static

    from wptui.app import WPTuiApp
    from wptui.screens.editor import EditorScreen

    app = WPTuiApp()
    app.client = _OfflineClient()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(EditorScreen(post_type="post"))
        await pilot.pause()
        await pilot.pause()
        editor = app.screen
        editor.query_one("#editor-title", Input).value = "Only local"
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        await pilot.pause()
        # The remote save failed, so the buffer must be flushed to the recovery store
        # immediately (not left waiting for the next autosave tick) …
        snap = autosave.read_snapshot(editor._draft_key)
        assert snap is not None and snap["title"] == "Only local"
        # … and the status must distinguish "kept locally" from a plain failure.
        status_widget = editor.query_one("#editor-status", Static)
        status = str(status_widget.content).lower()
        assert "local" in status
        assert status_widget.has_class("error")


@pytest.mark.asyncio
async def test_site_key_strips_trailing_slash():
    from wptui.app import WPTuiApp
    from wptui.config import SiteProfile
    from wptui.screens.editor import EditorScreen

    app = WPTuiApp()
    app.client = _BareClient()
    app.profile = SiteProfile(name="x", base_url="https://ex.com/", username="u")
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(EditorScreen(post_type="post"))
        await pilot.pause()
        await pilot.pause()
        editor = app.screen
        # A trailing slash on the profile URL must not fork the recovery key, or a
        # reconnect that drops/adds the slash would hide an existing local draft.
        assert editor._site() == "https://ex.com"

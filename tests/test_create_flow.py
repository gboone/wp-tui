"""End-to-end tests for creating a new post/page and saving with settings (U4)."""

from __future__ import annotations

import pytest
from textual.widgets import Input

from wptui.api import PostSettings
from wptui.api.dto import PostDetail, PostSummary
from wptui.api.errors import NetworkError


class RecordingClient:
    def __init__(self) -> None:
        self.created: list[tuple] = []
        self.updated: list[tuple] = []

    async def get_post(self, pid, post_type="post"):
        return PostDetail(pid, "T", "<p>x</p>", "draft", "2026-01-01T00:00:00", "http://x/1", post_type=post_type)

    async def create_post(self, post_type, *, title_raw="", content_raw="", settings=None):
        self.created.append((post_type, title_raw, content_raw, settings))
        return PostDetail(123, title_raw, content_raw, "draft", "2026-02-02T00:00:00", "http://x/123", post_type=post_type)

    async def update_post(self, post_id, *, content_raw=None, title_raw=None, settings=None, expected_modified_gmt=None):
        self.updated.append((post_id, content_raw, title_raw, settings, expected_modified_gmt))
        return PostDetail(post_id, title_raw or "", content_raw or "", "draft", "2026-03-03T00:00:00", "http://x/1")

    async def aclose(self):
        pass


async def _new_editor(pilot, app, post_type="post"):
    from wptui.screens.editor import EditorScreen

    app.push_screen(EditorScreen(post_type=post_type))
    await pilot.pause()
    await pilot.pause()
    return app.screen


@pytest.mark.asyncio
async def test_new_post_creates_then_updates():
    from wptui.app import WPTuiApp

    client = RecordingClient()
    app = WPTuiApp()
    app.client = client
    async with app.run_test() as pilot:
        await pilot.pause()
        editor = await _new_editor(pilot, app)
        editor.query_one("#editor-title", Input).value = "My New Post"
        await pilot.pause()

        await pilot.press("ctrl+s")
        await pilot.pause()
        await pilot.pause()
        # First save creates (no update, no conflict pre-check).
        assert len(client.created) == 1 and len(client.updated) == 0
        post_type, title, _content, settings = client.created[0]
        assert post_type == "post" and title == "My New Post"
        assert isinstance(settings, PostSettings) and settings.post_type == "post"

        # Second save updates the now-existing post using the adopted id.
        await pilot.press("ctrl+s")
        await pilot.pause()
        await pilot.pause()
        assert len(client.updated) == 1
        assert client.updated[0][0] == 123


@pytest.mark.asyncio
async def test_new_page_targets_page_type():
    from wptui.app import WPTuiApp

    client = RecordingClient()
    app = WPTuiApp()
    app.client = client
    async with app.run_test() as pilot:
        await pilot.pause()
        editor = await _new_editor(pilot, app, post_type="page")
        editor.query_one("#editor-title", Input).value = "About"
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        await pilot.pause()
        assert client.created[0][0] == "page"


@pytest.mark.asyncio
async def test_backing_out_of_new_editor_creates_nothing():
    from wptui.app import WPTuiApp

    client = RecordingClient()
    app = WPTuiApp()
    app.client = client
    async with app.run_test() as pilot:
        await pilot.pause()
        await _new_editor(pilot, app)
        await pilot.press("escape")
        await pilot.pause()
        assert client.created == []  # no orphan draft


@pytest.mark.asyncio
async def test_create_failure_is_surfaced_not_crashed():
    from wptui.app import WPTuiApp
    from wptui.screens.editor import EditorScreen

    class FailClient(RecordingClient):
        async def create_post(self, *a, **k):
            raise NetworkError("boom")

    app = WPTuiApp()
    app.client = FailClient()
    async with app.run_test() as pilot:
        await pilot.pause()
        await _new_editor(pilot, app)
        await pilot.press("ctrl+s")
        await pilot.pause()
        await pilot.pause()
        # Still alive on the editor screen; the failure did not crash the worker/app.
        assert isinstance(app.screen, EditorScreen)


# --- #4: a lost create response must not duplicate the post on retry ----------


class _LostCreateClient(RecordingClient):
    """create_post raises NetworkError the first time (response lost after a possible
    commit); ``posts`` is what list_posts reports the server actually holds."""

    def __init__(self, posts) -> None:
        super().__init__()
        self.create_calls = 0
        self._posts = posts

    async def create_post(self, post_type, *, title_raw="", content_raw="", settings=None):
        self.create_calls += 1
        if self.create_calls == 1:
            raise NetworkError("response lost after commit")
        return await super().create_post(
            post_type, title_raw=title_raw, content_raw=content_raw, settings=settings
        )

    async def list_posts(self, *, status="any", search=None, page=1, per_page=50):
        return list(self._posts)


@pytest.mark.asyncio
async def test_lost_create_recovers_via_update_not_duplicate():
    from wptui.app import WPTuiApp

    # The lost create actually committed as post 555; retry should adopt + update it.
    committed = PostSummary(555, "My New Post", "draft", "2026-02-02T00:00:00", "http://x/555", "post")
    client = _LostCreateClient([committed])
    app = WPTuiApp()
    app.client = client
    async with app.run_test() as pilot:
        await pilot.pause()
        editor = await _new_editor(pilot, app)
        editor.query_one("#editor-title", Input).value = "My New Post"
        await pilot.pause()
        await pilot.press("ctrl+s")  # create fails (network) -> flagged unverified
        await pilot.pause()
        await pilot.pause()
        assert client.create_calls == 1 and editor._unverified_create is True
        await pilot.press("ctrl+s")  # retry finds the committed post -> updates it
        await pilot.pause()
        await pilot.pause()
        assert client.create_calls == 1  # NOT re-created
        assert len(client.updated) == 1 and client.updated[0][0] == 555
        assert editor._post_id == 555 and editor._unverified_create is False


@pytest.mark.asyncio
async def test_lost_create_with_no_committed_post_creates_on_retry():
    from wptui.app import WPTuiApp

    client = _LostCreateClient([])  # server confirms nothing landed
    app = WPTuiApp()
    app.client = client
    async with app.run_test() as pilot:
        await pilot.pause()
        editor = await _new_editor(pilot, app)
        editor.query_one("#editor-title", Input).value = "Unique Title"
        await pilot.pause()
        await pilot.press("ctrl+s")  # first create fails
        await pilot.pause()
        await pilot.pause()
        await pilot.press("ctrl+s")  # "absent" -> a real create happens, no prompt
        await pilot.pause()
        await pilot.pause()
        assert client.create_calls == 2
        assert editor._post_id == 123 and editor._unverified_create is False


@pytest.mark.asyncio
async def test_lost_create_untitled_prompts_before_creating():
    from wptui.app import WPTuiApp
    from wptui.widgets.confirm import ConfirmModal
    from textual.widgets import Button

    client = _LostCreateClient([])
    app = WPTuiApp()
    app.client = client
    async with app.run_test() as pilot:
        await pilot.pause()
        editor = await _new_editor(pilot, app)
        # No title -> reconciliation can't match -> the retry must ask before creating.
        await pilot.press("ctrl+s")
        await pilot.pause()
        await pilot.pause()
        assert editor._unverified_create is True
        await pilot.press("ctrl+s")
        await pilot.pause()
        await pilot.pause()
        assert isinstance(app.screen, ConfirmModal)
        app.screen.query_one("#confirm-yes", Button).press()  # "Create anyway"
        await pilot.pause()
        await pilot.pause()
        assert client.create_calls == 2  # created after confirmation

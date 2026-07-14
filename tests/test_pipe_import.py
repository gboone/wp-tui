"""Tests for EditorScreen's pre-fill ("pipe import") mode (U3).

These exercise the ``import_blocks``/``import_title`` constructor path added to
``EditorScreen`` so it can open with already-built content instead of starting blank or
fetching from the server. The actual markdown -> block conversion (U2) and the app-level
stdin wiring (U4) are covered elsewhere; here we only need pre-built ``Block`` objects.
"""

from __future__ import annotations

import pytest
from textual.widgets import Input

from wptui.autosave import read_snapshot, write_snapshot
from wptui.blocks import parse
from wptui.widgets.canvas import BlockCanvas
from wptui.widgets.text_block import TextBlockEditor

SAMPLE_CONTENT = "<!-- wp:paragraph -->\n<p>Hello from import.</p>\n<!-- /wp:paragraph -->"


class RecordingClient:
    """Minimal fake client that records create_post calls (mirrors test_create_flow.py)."""

    def __init__(self) -> None:
        self.created: list[tuple] = []
        self.updated: list[tuple] = []

    async def get_post(self, pid, post_type="post"):
        raise AssertionError("get_post should never be called for a pre-filled new post")

    async def create_post(self, post_type, *, title_raw="", content_raw="", settings=None):
        self.created.append((post_type, title_raw, content_raw, settings))
        return _detail(123, title_raw, content_raw, post_type)

    async def update_post(
        self, post_id, *, content_raw=None, title_raw=None, settings=None, expected_modified_gmt=None
    ):
        self.updated.append((post_id, content_raw, title_raw, settings, expected_modified_gmt))
        return _detail(post_id, title_raw or "", content_raw or "", "post")

    async def aclose(self):
        pass


def _detail(post_id, title, content, post_type):
    from wptui.api.dto import PostDetail

    return PostDetail(
        id=post_id,
        title_raw=title,
        content_raw=content,
        status="draft",
        modified_gmt="2026-01-02T00:00:00",
        link=f"http://x/{post_id}",
        post_type=post_type,
    )


async def _push_import_editor(pilot, app, *, title=None, content=SAMPLE_CONTENT):
    from wptui.screens.editor import EditorScreen

    blocks = parse(content) if content is not None else []
    app.push_screen(EditorScreen(import_blocks=blocks, import_title=title))
    await pilot.pause()
    await pilot.pause()
    return app.screen


@pytest.mark.asyncio
async def test_prefilled_content_renders_on_mount():
    from wptui.app import WPTuiApp

    app = WPTuiApp()
    app.client = RecordingClient()
    async with app.run_test() as pilot:
        await pilot.pause()
        editor = await _push_import_editor(pilot, app, title="My Title")

        assert editor.query_one("#editor-title", Input).value == "My Title"
        text_editors = list(editor.query(TextBlockEditor))
        assert len(text_editors) == 1
        assert text_editors[0].query_one("#body").text == "Hello from import."

        status = editor.query_one("#editor-status")._Static__content
        assert str(status) == "Imported 1 block(s) · Ctrl+E settings · Ctrl+S to save"


@pytest.mark.asyncio
async def test_ctrl_s_creates_via_normal_new_post_path():
    from wptui.app import WPTuiApp

    client = RecordingClient()
    app = WPTuiApp()
    app.client = client
    async with app.run_test() as pilot:
        await pilot.pause()
        editor = await _push_import_editor(pilot, app, title="My Title")

        await pilot.press("ctrl+s")
        await pilot.pause()
        await pilot.pause()

        # Only the first Ctrl+S creates the post -- no write happened before it (R11).
        assert len(client.created) == 1 and len(client.updated) == 0
        post_type, title, content, settings = client.created[0]
        assert post_type == "post"
        assert title == "My Title"
        assert "Hello from import." in content


@pytest.mark.asyncio
async def test_empty_import_shows_distinct_status_line():
    from wptui.app import WPTuiApp

    app = WPTuiApp()
    app.client = RecordingClient()
    async with app.run_test() as pilot:
        await pilot.pause()
        editor = await _push_import_editor(pilot, app, title=None, content="")

        assert isinstance(editor._canvas, BlockCanvas)
        assert editor._canvas.blocks == []
        status = editor.query_one("#editor-status")._Static__content
        assert str(status) == "Imported 0 block(s) · Ctrl+E settings · Ctrl+S to save"


@pytest.mark.asyncio
async def test_resume_prompt_never_appears_even_with_stale_snapshot():
    from wptui.app import WPTuiApp
    from wptui.screens.editor import EditorScreen

    # An unrelated stale new-post draft for the same ("local") site.
    write_snapshot(
        "local|new|some-earlier-session",
        {
            "title": "Stale draft",
            "content": "<!-- wp:paragraph -->\n<p>Stale.</p>\n<!-- /wp:paragraph -->",
            "settings": {},
            "post_id": None,
            "post_type": "post",
            "modified_gmt": None,
            "site": "local",
            "saved_at": "2020-01-01T00:00:00",
        },
    )

    app = WPTuiApp()
    app.client = RecordingClient()
    async with app.run_test() as pilot:
        await pilot.pause()
        editor = await _push_import_editor(pilot, app, title="My Title")
        await pilot.pause()

        # No ConfirmModal ("resume unsaved draft?") got pushed on top.
        assert isinstance(app.screen, EditorScreen)
        assert app.screen is editor

        # Escape pops straight back off the editor (no modal to dismiss first).
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, EditorScreen)


@pytest.mark.asyncio
async def test_autosave_snapshot_exists_immediately_after_mount():
    from wptui.app import WPTuiApp

    app = WPTuiApp()
    app.client = RecordingClient()
    async with app.run_test() as pilot:
        await pilot.pause()
        editor = await _push_import_editor(pilot, app, title="My Title")

        # No timer tick has fired yet (autosave interval is 2s); the snapshot must already
        # be on disk from the synchronous write in _start_import.
        assert editor._draft_key is not None
        snap = read_snapshot(editor._draft_key)
        assert snap is not None
        assert snap["title"] == "My Title"
        assert "Hello from import." in snap["content"]


@pytest.mark.asyncio
async def test_focus_lands_on_title_when_no_title_provided():
    from wptui.app import WPTuiApp

    app = WPTuiApp()
    app.client = RecordingClient()
    async with app.run_test() as pilot:
        await pilot.pause()
        editor = await _push_import_editor(pilot, app, title=None)
        await pilot.pause()

        assert editor.focused is editor.query_one("#editor-title", Input)


@pytest.mark.asyncio
async def test_focus_lands_on_first_block_when_title_provided():
    from wptui.app import WPTuiApp

    app = WPTuiApp()
    app.client = RecordingClient()
    async with app.run_test() as pilot:
        await pilot.pause()
        editor = await _push_import_editor(pilot, app, title="My Title")
        await pilot.pause()

        first_body = editor.query_one(TextBlockEditor).query_one("#body")
        assert editor.focused is first_body

"""Tests for the F3 heading-level picker (U3)."""

from __future__ import annotations

import pytest

from wptui.api.dto import PostDetail, PostSummary
from wptui.app import WPTuiApp
from wptui.blocks import serialize
from wptui.screens.editor import EditorScreen
from wptui.widgets.canvas import BlockCanvas
from wptui.widgets.heading_level import HeadingLevelModal

H2_DOC = '<!-- wp:heading -->\n<h2 class="wp-block-heading">Title</h2>\n<!-- /wp:heading -->'
PARA_DOC = "<!-- wp:paragraph -->\n<p>hello</p>\n<!-- /wp:paragraph -->"
DOC_3 = "\n\n".join(
    [
        "<!-- wp:paragraph -->\n<p>First.</p>\n<!-- /wp:paragraph -->",
        H2_DOC,
        "<!-- wp:paragraph -->\n<p>Third.</p>\n<!-- /wp:paragraph -->",
    ]
)


class _Client:
    def __init__(self, doc: str) -> None:
        self._doc = doc

    async def get_post(self, pid, post_type="post"):
        return PostDetail(pid, "T", self._doc, "draft", "2026-01-01T00:00:00", "http://x/1")

    async def aclose(self):
        pass


async def _editor(doc: str):
    app = WPTuiApp()
    app.client = _Client(doc)
    return app


async def _push(app, pilot):
    app.push_screen(EditorScreen(PostSummary(1, "T", "draft", "2026-01-01T00:00:00", "http://x/1")))
    for _ in range(3):
        await pilot.pause()
    return app.screen._canvas


async def _settle(pilot):
    for _ in range(4):
        await pilot.pause()


@pytest.mark.asyncio
async def test_f3_on_heading_opens_picker_and_changes_level():
    app = await _editor(H2_DOC)
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = await _push(app, pilot)
        canvas._editors[0].query_one("#body").focus()
        await pilot.pause()
        await pilot.press("f3")
        await pilot.pause()
        assert isinstance(app.screen, HeadingLevelModal)
        options = app.screen.query_one("#heading-level-list")
        options.highlighted = 3  # Heading 4
        await pilot.press("enter")
        await _settle(pilot)
        out = serialize(canvas.blocks)
        assert '<h4 class="wp-block-heading">Title</h4>' in out and '{"level":4}' in out


@pytest.mark.asyncio
async def test_f3_on_non_heading_opens_no_picker():
    app = await _editor(PARA_DOC)
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = await _push(app, pilot)
        canvas._editors[0].query_one("#body").focus()
        await pilot.pause()
        await pilot.press("f3")
        await pilot.pause()
        assert isinstance(app.screen, EditorScreen)  # no modal


@pytest.mark.asyncio
async def test_escape_leaves_heading_unchanged():
    app = await _editor(H2_DOC)
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = await _push(app, pilot)
        before = serialize(canvas.blocks)
        canvas._editors[0].query_one("#body").focus()
        await pilot.pause()
        await pilot.press("f3")
        await pilot.pause()
        await pilot.press("escape")
        await _settle(pilot)
        assert serialize(canvas.blocks) == before


@pytest.mark.asyncio
async def test_level_change_leaves_other_blocks_byte_identical():
    p1 = "<!-- wp:paragraph -->\n<p>First.</p>\n<!-- /wp:paragraph -->"
    p3 = "<!-- wp:paragraph -->\n<p>Third.</p>\n<!-- /wp:paragraph -->"
    app = await _editor(DOC_3)
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = await _push(app, pilot)
        canvas._editors[1].query_one("#body").focus()  # the heading
        await pilot.pause()
        await pilot.press("f3")
        await pilot.pause()
        app.screen.query_one("#heading-level-list").highlighted = 2  # Heading 3
        await pilot.press("enter")
        await _settle(pilot)
        out = serialize(canvas.blocks)
        assert out.startswith(p1) and out.endswith(p3) and "<h3 " in out

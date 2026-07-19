"""End-to-end tests for document undo/redo through the editor (U2)."""

from __future__ import annotations

import pytest

from wptui.api.dto import PostDetail, PostSummary
from wptui.app import WPTuiApp
from wptui.blocks import serialize
from wptui.screens.editor import EditorScreen
from wptui.widgets.canvas import BlockCanvas

P1 = "<!-- wp:paragraph -->\n<p>One</p>\n<!-- /wp:paragraph -->"
P2 = "<!-- wp:paragraph -->\n<p>Two</p>\n<!-- /wp:paragraph -->"
DOC = "\n\n".join([P1, P2])


class _Client:
    def __init__(self, doc):
        self._doc = doc

    async def get_post(self, pid, post_type="post"):
        return PostDetail(pid, "T", self._doc, "draft", "2026-01-01T00:00:00", "http://x/1")

    async def aclose(self):
        pass


async def _open(doc, pilot):
    app = WPTuiApp()
    app.client = _Client(doc)
    return app


async def _push(app, pilot):
    app.push_screen(EditorScreen(PostSummary(1, "T", "draft", "2026-01-01T00:00:00", "http://x/1")))
    for _ in range(3):
        await pilot.pause()
    return app.screen


async def _settle(pilot):
    for _ in range(5):
        await pilot.pause()


def _para_count(canvas):
    return serialize(canvas.blocks).count("<!-- wp:paragraph -->")


@pytest.mark.asyncio
async def test_undo_restores_a_deleted_block_and_redo_deletes_it_again():
    app = WPTuiApp()
    app.client = _Client(DOC)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _push(app, pilot)
        canvas = screen._canvas
        canvas._editors[0].query_one("#body").focus()  # the first paragraph
        await pilot.pause()
        await pilot.press("ctrl+delete")
        await _settle(pilot)
        assert _para_count(canvas) == 1  # one deleted
        await pilot.press("ctrl+z")
        await _settle(pilot)
        assert _para_count(canvas) == 2  # restored
        await pilot.press("ctrl+y")
        await _settle(pilot)
        assert _para_count(canvas) == 1  # deleted again


@pytest.mark.asyncio
async def test_undo_reverses_an_inserted_paragraph():
    app = WPTuiApp()
    app.client = _Client(P1)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _push(app, pilot)
        canvas = screen._canvas
        canvas._editors[0].query_one("#body").focus()
        await pilot.pause()
        await pilot.press("ctrl+n")  # insert a paragraph
        await _settle(pilot)
        assert _para_count(canvas) == 2
        await pilot.press("ctrl+z")
        await _settle(pilot)
        assert _para_count(canvas) == 1


@pytest.mark.asyncio
async def test_undo_with_no_history_is_a_noop():
    app = WPTuiApp()
    app.client = _Client(DOC)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _push(app, pilot)
        canvas = screen._canvas
        before = serialize(canvas.blocks)
        canvas._editors[0].query_one("#body").focus()
        await pilot.pause()
        await pilot.press("ctrl+z")  # nothing changed yet
        await _settle(pilot)
        assert serialize(canvas.blocks) == before


@pytest.mark.asyncio
async def test_redo_with_nothing_to_redo_is_a_noop():
    app = WPTuiApp()
    app.client = _Client(DOC)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _push(app, pilot)
        canvas = screen._canvas
        canvas._editors[0].query_one("#body").focus()
        await pilot.pause()
        before = serialize(canvas.blocks)
        await pilot.press("ctrl+y")
        await _settle(pilot)
        assert serialize(canvas.blocks) == before


@pytest.mark.asyncio
async def test_new_edit_after_undo_clears_redo():
    app = WPTuiApp()
    app.client = _Client(DOC)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = await _push(app, pilot)
        canvas = screen._canvas
        canvas._editors[0].query_one("#body").focus()
        await pilot.pause()
        await pilot.press("ctrl+delete")  # 2 -> 1
        await _settle(pilot)
        await pilot.press("ctrl+z")  # -> 2
        await _settle(pilot)
        assert _para_count(canvas) == 2
        # a fresh structural edit clears the redo future
        canvas._editors[0].query_one("#body").focus()
        await pilot.pause()
        await pilot.press("ctrl+n")  # 2 -> 3
        await _settle(pilot)
        await pilot.press("ctrl+y")  # nothing to redo
        await _settle(pilot)
        assert _para_count(canvas) == 3

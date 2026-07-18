"""End-to-end tests for Enter/Backspace structural editing of nested children (U3)."""

from __future__ import annotations

import pytest

from wptui.api.dto import PostDetail, PostSummary
from wptui.app import WPTuiApp
from wptui.blocks import serialize
from wptui.blocks.containers import set_container_children
from wptui.blocks.factory import new_list_block, new_list_item, new_paragraph_block, new_quote_block
from wptui.blocks.text import set_editable_body
from wptui.keys import Mode
from wptui.screens.editor import EditorScreen
from wptui.widgets.canvas import BlockCanvas
from wptui.widgets.inline_area import InlineMarkdownArea


def _list_doc(*texts):
    lst = new_list_block()
    items = []
    for t in texts:
        item = new_list_item()
        set_editable_body(item, t)
        items.append(item)
    set_container_children(lst, items)
    return serialize([lst])


def _quote_doc(*texts):
    quote = new_quote_block()
    paras = []
    for t in texts:
        para = new_paragraph_block()
        set_editable_body(para, t)
        paras.append(para)
    set_container_children(quote, paras)
    return serialize([quote])


PARA_DOC = "<!-- wp:paragraph -->\n<p>hello</p>\n<!-- /wp:paragraph -->"


class _Client:
    def __init__(self, doc: str) -> None:
        self._doc = doc

    async def get_post(self, pid, post_type="post"):
        return PostDetail(pid, "T", self._doc, "draft", "2026-01-01T00:00:00", "http://x/1")

    async def aclose(self):
        pass


async def _push_editor(app, pilot):
    app.push_screen(EditorScreen(PostSummary(1, "T", "draft", "2026-01-01T00:00:00", "http://x/1")))
    for _ in range(3):
        await pilot.pause()
    return app.screen._canvas


async def _settle(pilot):
    for _ in range(5):
        await pilot.pause()


def _list_item_count(canvas: BlockCanvas) -> int:
    return serialize(canvas.blocks).count("<!-- wp:list-item -->")


@pytest.mark.asyncio
async def test_enter_at_end_adds_second_bullet():
    app = WPTuiApp()
    app.client = _Client(_list_doc("first"))
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = await _push_editor(app, pilot)
        body = canvas._editors[0].query_one("#body", InlineMarkdownArea)
        body.focus()
        body.move_cursor(body.document.end)
        await pilot.pause()
        await pilot.press("enter")
        await _settle(pilot)
        assert _list_item_count(canvas) == 2  # the headline: a second bullet exists


@pytest.mark.asyncio
async def test_enter_mid_text_splits_item():
    app = WPTuiApp()
    app.client = _Client(_list_doc("onetwo"))
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = await _push_editor(app, pilot)
        body = canvas._editors[0].query_one("#body", InlineMarkdownArea)
        body.focus()
        body.move_cursor((0, 3))  # between "one" and "two"
        await pilot.pause()
        await pilot.press("enter")
        await _settle(pilot)
        out = serialize(canvas.blocks)
        assert "<li>one</li>" in out and "<li>two</li>" in out


@pytest.mark.asyncio
async def test_enter_on_empty_item_exits_to_paragraph():
    app = WPTuiApp()
    app.client = _Client(_list_doc(""))
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = await _push_editor(app, pilot)
        canvas._editors[0].query_one("#body").focus()
        await pilot.pause()
        await pilot.press("enter")
        await _settle(pilot)
        out = serialize(canvas.blocks)
        assert "<!-- wp:list -->" not in out and "<!-- wp:paragraph -->" in out


@pytest.mark.asyncio
async def test_backspace_start_of_empty_item_removes_it():
    app = WPTuiApp()
    app.client = _Client(_list_doc("keep", ""))
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = await _push_editor(app, pilot)
        canvas._editors[1].query_one("#body").focus()  # empty second item, caret at (0,0)
        await pilot.pause()
        await pilot.press("backspace")
        await _settle(pilot)
        assert _list_item_count(canvas) == 1


@pytest.mark.asyncio
async def test_backspace_start_of_nonempty_item_merges_into_previous():
    app = WPTuiApp()
    app.client = _Client(_list_doc("one", "two"))
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = await _push_editor(app, pilot)
        body = canvas._editors[1].query_one("#body", InlineMarkdownArea)
        body.focus()
        body.move_cursor((0, 0))
        await pilot.pause()
        await pilot.press("backspace")
        await _settle(pilot)
        out = serialize(canvas.blocks)
        assert _list_item_count(canvas) == 1 and "<li>onetwo</li>" in out


@pytest.mark.asyncio
async def test_backspace_start_of_first_item_is_noop():
    app = WPTuiApp()
    app.client = _Client(_list_doc("one"))
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = await _push_editor(app, pilot)
        body = canvas._editors[0].query_one("#body", InlineMarkdownArea)
        body.focus()
        body.move_cursor((0, 0))
        await pilot.pause()
        await pilot.press("backspace")
        await _settle(pilot)
        assert _list_item_count(canvas) == 1 and "<li>one</li>" in serialize(canvas.blocks)


@pytest.mark.asyncio
async def test_enter_in_top_level_paragraph_is_not_restructured():
    app = WPTuiApp()
    app.client = _Client(PARA_DOC)
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = await _push_editor(app, pilot)
        body = canvas._editors[0].query_one("#body", InlineMarkdownArea)
        body.focus()
        body.move_cursor(body.document.end)
        await pilot.pause()
        await pilot.press("enter")
        await _settle(pilot)
        # Still one paragraph block; Enter inserted a newline instead of restructuring.
        assert serialize(canvas.blocks).count("<!-- wp:paragraph -->") == 1
        assert "\n" in canvas._editors[0].query_one("#body", InlineMarkdownArea).text


@pytest.mark.asyncio
async def test_quote_paragraph_enter_adds_paragraph():
    app = WPTuiApp()
    app.client = _Client(_quote_doc("hello"))
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = await _push_editor(app, pilot)
        body = canvas._editors[0].query_one("#body", InlineMarkdownArea)
        body.focus()
        body.move_cursor(body.document.end)
        await pilot.pause()
        await pilot.press("enter")
        await _settle(pilot)
        assert serialize(canvas.blocks).count("<!-- wp:paragraph -->") == 2


@pytest.mark.asyncio
async def test_vim_normal_enter_does_not_restructure_but_insert_does():
    app = WPTuiApp()
    app.client = _Client(_list_doc("first"))
    async with app.run_test() as pilot:
        await pilot.pause()
        app.vim_mode = True
        canvas = await _push_editor(app, pilot)
        body = canvas._editors[0].query_one("#body", InlineMarkdownArea)
        body.focus()
        body._vim.mode = Mode.NORMAL
        await pilot.pause()
        await pilot.press("enter")
        await _settle(pilot)
        assert _list_item_count(canvas) == 1  # NORMAL Enter is a motion, not a split

        body = canvas._editors[0].query_one("#body", InlineMarkdownArea)
        body.focus()
        body._vim.mode = Mode.INSERT
        body.move_cursor(body.document.end)
        await pilot.pause()
        await pilot.press("enter")
        await _settle(pilot)
        assert _list_item_count(canvas) == 2  # INSERT Enter splits

"""Headless tests for list indent/outdent transforms (U3)."""

from __future__ import annotations

from wptui.blocks import parse, serialize
from wptui.blocks.containers import (
    MAX_LIST_NEST_DEPTH,
    _sublist_of,
    indent_item,
    list_depth,
    outdent_item,
    set_container_children,
)
from wptui.blocks.factory import new_list_block, new_list_item
from wptui.blocks.text import get_editable_body, set_editable_body


def _item(text):
    item = new_list_item()
    set_editable_body(item, text)
    return item


def _list(*texts, ordered=False):
    lst = new_list_block(ordered=ordered)
    items = [_item(t) for t in texts]
    set_container_children(lst, items)
    return lst, items


def _bodies(items):
    return [get_editable_body(i) for i in items]


def _roundtrips(block):
    once = serialize([block])
    return serialize(parse(once)) == once


def test_indent_moves_item_into_previous_siblings_new_sublist():
    lst, items = _list("a", "b", "c")
    assert indent_item(lst, items[1])  # indent b under a
    assert _bodies(lst.inner_blocks) == ["a", "c"]
    sub = _sublist_of(lst.inner_blocks[0])
    assert sub is not None and _bodies(sub.inner_blocks) == ["b"]
    out = serialize([lst])
    assert out.count("<!-- wp:list -->") == 2 and "<li>b</li>" in out
    assert _roundtrips(lst)


def test_indent_appends_to_existing_sublist():
    lst, items = _list("a", "b", "c")
    indent_item(lst, items[1])  # a(sub:[b]), c
    indent_item(lst, items[2])  # c's prev is a, which has a sublist -> append
    assert _bodies(lst.inner_blocks) == ["a"]
    sub = _sublist_of(lst.inner_blocks[0])
    assert _bodies(sub.inner_blocks) == ["b", "c"]
    assert _roundtrips(lst)


def test_indent_first_item_is_noop():
    lst, items = _list("a", "b")
    assert indent_item(lst, items[0]) is False
    assert _bodies(lst.inner_blocks) == ["a", "b"]


def test_outdent_moves_item_up_and_drops_empty_sublist():
    lst, items = _list("a", "b")
    indent_item(lst, items[1])  # a(sub:[b])
    a = lst.inner_blocks[0]
    sub = _sublist_of(a)
    chain = [lst, a, sub]
    assert outdent_item(chain, items[1])
    assert _bodies(lst.inner_blocks) == ["a", "b"]  # b back to top level
    assert _sublist_of(lst.inner_blocks[0]) is None  # emptied sublist removed
    assert _roundtrips(lst)


def test_outdent_keeps_following_siblings_in_sublist():
    lst, items = _list("a", "b", "c")
    indent_item(lst, items[1])  # a(sub:[b]), c
    indent_item(lst, items[2])  # a(sub:[b, c])
    a = lst.inner_blocks[0]
    sub = _sublist_of(a)
    chain = [lst, a, sub]
    assert outdent_item(chain, items[1])  # outdent b
    assert _bodies(lst.inner_blocks) == ["a", "b"]  # b after a
    sub_after = _sublist_of(lst.inner_blocks[0])
    assert sub_after is not None and _bodies(sub_after.inner_blocks) == ["c"]  # c stays nested


def test_outdent_at_top_level_is_noop():
    lst, items = _list("a", "b")
    assert outdent_item([lst], items[1]) is False


def test_list_depth_and_cap():
    lst, items = _list("a", "b")
    indent_item(lst, items[1])  # b at depth 2
    a = lst.inner_blocks[0]
    sub = _sublist_of(a)
    assert list_depth([lst]) == 1  # top-level item's chain
    assert list_depth([lst, a, sub]) == 2  # depth-2 item's chain
    assert MAX_LIST_NEST_DEPTH == 4


# ------------------------------------------------------------------ E2E (EditorScreen)

import pytest  # noqa: E402

from wptui.api.dto import PostDetail, PostSummary  # noqa: E402
from wptui.app import WPTuiApp  # noqa: E402
from wptui.keys import Mode  # noqa: E402
from wptui.screens.editor import EditorScreen  # noqa: E402
from wptui.widgets.canvas import BlockCanvas  # noqa: E402
from wptui.widgets.inline_area import InlineMarkdownArea  # noqa: E402


def _list_doc(*texts):
    lst, _ = _list(*texts)
    return serialize([lst])


class _Client:
    def __init__(self, doc):
        self._doc = doc

    async def get_post(self, pid, post_type="post"):
        return PostDetail(pid, "T", self._doc, "draft", "2026-01-01T00:00:00", "http://x/1")

    async def aclose(self):
        pass


async def _push(app, pilot):
    app.push_screen(EditorScreen(PostSummary(1, "T", "draft", "2026-01-01T00:00:00", "http://x/1")))
    for _ in range(3):
        await pilot.pause()
    return app.screen._canvas


async def _settle(pilot):
    for _ in range(5):
        await pilot.pause()


def _list_count(canvas):
    return serialize(canvas.blocks).count("<!-- wp:list -->")


@pytest.mark.asyncio
async def test_tab_indents_and_shift_tab_outdents():
    app = WPTuiApp()
    app.client = _Client(_list_doc("a", "b", "c"))
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = await _push(app, pilot)
        canvas._editors[1].query_one("#body").focus()  # item b
        await pilot.pause()
        await pilot.press("tab")
        await _settle(pilot)
        assert _list_count(canvas) == 2  # b nested under a
        # focus followed the moved item and did not traverse away
        assert isinstance(app.focused, InlineMarkdownArea)
        await pilot.press("shift+tab")
        await _settle(pilot)
        assert _list_count(canvas) == 1  # b back to top level


@pytest.mark.asyncio
async def test_tab_on_first_item_is_noop():
    app = WPTuiApp()
    app.client = _Client(_list_doc("a", "b"))
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = await _push(app, pilot)
        canvas._editors[0].query_one("#body").focus()  # first item
        await pilot.pause()
        await pilot.press("tab")
        await _settle(pilot)
        assert _list_count(canvas) == 1  # unchanged


@pytest.mark.asyncio
async def test_tab_respects_the_depth_cap():
    app = WPTuiApp()
    app.client = _Client(_list_doc("a", "b", "c", "d", "e"))
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = await _push(app, pilot)
        # Indent the 2nd editor repeatedly; each Tab nests the current item one deeper.
        for _ in range(6):  # more than the cap
            editors = [e for e in canvas._editors]
            editors[1].query_one("#body").focus()
            await pilot.pause()
            await pilot.press("tab")
            await _settle(pilot)
        # 5 items, capped at depth 4 -> at most 4 list levels.
        assert _list_count(canvas) <= 4


@pytest.mark.asyncio
async def test_vim_normal_tab_does_not_indent():
    app = WPTuiApp()
    app.client = _Client(_list_doc("a", "b"))
    async with app.run_test() as pilot:
        await pilot.pause()
        app.vim_mode = True
        canvas = await _push(app, pilot)
        body = canvas._editors[1].query_one("#body", InlineMarkdownArea)
        body.focus()
        body._vim.mode = Mode.NORMAL
        await pilot.pause()
        await pilot.press("tab")
        await _settle(pilot)
        assert _list_count(canvas) == 1  # NORMAL Tab is not an indent


@pytest.mark.asyncio
async def test_indent_leaves_other_blocks_byte_identical():
    p1 = "<!-- wp:paragraph -->\n<p>First.</p>\n<!-- /wp:paragraph -->"
    p3 = "<!-- wp:paragraph -->\n<p>Third.</p>\n<!-- /wp:paragraph -->"
    doc = "\n\n".join([p1, _list_doc("a", "b"), p3])
    app = WPTuiApp()
    app.client = _Client(doc)
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = await _push(app, pilot)
        # editors: [First., a, b, Third.] -> focus b
        canvas._editors[2].query_one("#body").focus()
        await pilot.pause()
        await pilot.press("tab")
        await _settle(pilot)
        out = serialize(canvas.blocks)
        assert out.startswith(p1) and out.endswith(p3) and out.count("<!-- wp:list -->") == 2

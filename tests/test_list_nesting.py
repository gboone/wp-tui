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


def test_outdent_reparents_following_siblings_under_the_item():
    # Outdenting b (first of a's sublist [b, c]) pulls c out under b, preserving visual order.
    lst, items = _list("a", "b", "c")
    indent_item(lst, items[1])  # a(sub:[b]), c
    indent_item(lst, items[2])  # a(sub:[b, c])
    a = lst.inner_blocks[0]
    chain = [lst, a, _sublist_of(a)]
    assert outdent_item(chain, items[1])  # outdent b
    assert _bodies(lst.inner_blocks) == ["a", "b"]
    assert _sublist_of(lst.inner_blocks[0]) is None  # a emptied (b was first)
    assert _bodies(_sublist_of(lst.inner_blocks[1]).inner_blocks) == ["c"]  # c now under b


def test_indent_moves_item_with_its_own_sublist_as_a_unit():
    # a, b(sub:[x]), c  ->  indent b under a keeps b's own sublist [x] intact.
    lst, items = _list("a", "b", "c")
    indent_item(lst, items[2])  # a, b(sub:[c])  -- give b a sublist by nesting c under it
    # now a, b(sub:[c]); indent b under a
    assert indent_item(lst, items[1])
    assert _bodies(lst.inner_blocks) == ["a"]
    b = _sublist_of(lst.inner_blocks[0]).inner_blocks[0]
    assert get_editable_body(b) == "b"
    assert _bodies(_sublist_of(b).inner_blocks) == ["c"]  # b kept its sublist
    assert _roundtrips(lst)


def test_indent_preserves_ordered_list_kind():
    lst, items = _list("a", "b", ordered=True)
    indent_item(lst, items[1])
    sub = _sublist_of(lst.inner_blocks[0])
    assert sub.attributes.get("ordered") is True
    assert "<ol" in serialize([lst])


def test_nest_then_unnest_is_byte_identical():
    lst, items = _list("a", "b")
    original = serialize([lst])
    indent_item(lst, items[1])
    a = lst.inner_blocks[0]
    outdent_item([lst, a, _sublist_of(a)], items[1])
    assert serialize([lst]) == original


def test_outdent_at_top_level_is_noop():
    lst, items = _list("a", "b")
    assert outdent_item([lst], items[1]) is False


def test_outdent_through_a_quote_is_a_safe_noop():
    # list > item A > quote > list > item b. Outdenting b must NOT corrupt the quote — the
    # chain is interrupted by a non-list container, so it's a no-op.
    from wptui.blocks.factory import new_quote_block

    inner_list, inner_items = _list("b")
    quote = new_quote_block()
    set_container_children(quote, [inner_list])
    outer_item = _item_with_sublist_block("A", quote)
    top = _wrap_list_block([outer_item])
    before = serialize([top])
    chain = [top, outer_item, quote, inner_list]  # …, enclosing?, parent?, sublist
    assert outdent_item(chain, inner_items[0]) is False
    assert serialize([top]) == before  # quote intact


def _item_with_sublist_block(text, container):
    from wptui.blocks.model import Block

    return Block(
        block_name="core/list-item",
        inner_blocks=[container],
        inner_content=[f"\n<li>{text}", None, "</li>\n"],
        inner_html=f"\n<li>{text}</li>\n",
        dirty=True,
    )


def _wrap_list_block(items):
    lst = new_list_block()
    set_container_children(lst, items)
    return lst


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


def _item_with_sublist(text, sublist):
    from wptui.blocks.model import Block

    return Block(
        block_name="core/list-item",
        inner_blocks=[sublist],
        inner_content=[f"\n<li>{text}", None, "</li>\n"],
        inner_html=f"\n<li>{text}</li>\n",
        dirty=True,
    )


def _wrap_list(items):
    lst = new_list_block()
    set_container_children(lst, items)
    return lst


def _depth_four_list():
    # L1[a(L2[b(L3[c(L4[x, y])])])] — x and y sit at nesting depth 4.
    l4 = _wrap_list([_item("x"), _item("y")])
    l3 = _wrap_list([_item_with_sublist("c", l4)])
    l2 = _wrap_list([_item_with_sublist("b", l3)])
    return _wrap_list([_item_with_sublist("a", l2)])


@pytest.mark.asyncio
async def test_tab_at_the_depth_cap_is_a_noop():
    app = WPTuiApp()
    app.client = _Client(serialize([_depth_four_list()]))
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = await _push(app, pilot)
        before = serialize(canvas.blocks)
        # editors render a, b, c, x, y -> focus y (depth 4, has previous sibling x)
        canvas._editors[4].query_one("#body").focus()
        await pilot.pause()
        await pilot.press("tab")
        await _settle(pilot)
        assert _list_count(canvas) == 4  # capped — no deeper nesting
        assert serialize(canvas.blocks) == before


@pytest.mark.asyncio
async def test_tab_in_a_quote_paragraph_does_not_indent():
    from wptui.blocks.factory import new_paragraph_block, new_quote_block
    from wptui.blocks.text import set_editable_body

    quote = new_quote_block()
    paras = []
    for t in ("one", "two"):
        p = new_paragraph_block()
        set_editable_body(p, t)
        paras.append(p)
    set_container_children(quote, paras)
    app = WPTuiApp()
    app.client = _Client(serialize([quote]))
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = await _push(app, pilot)
        before = serialize(canvas.blocks)
        canvas._editors[1].query_one("#body").focus()  # a quote paragraph
        await pilot.pause()
        await pilot.press("tab")
        await _settle(pilot)
        assert "<!-- wp:list -->" not in serialize(canvas.blocks)  # no list created
        assert serialize(canvas.blocks) == before


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

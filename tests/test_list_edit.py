"""Canvas-level tests for nested-child structural editing (U2)."""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult

from wptui.blocks import parse, serialize
from wptui.blocks.containers import set_container_children
from wptui.blocks.factory import new_list_block, new_list_item, new_paragraph_block, new_quote_block
from wptui.blocks.text import set_editable_body
from wptui.widgets.canvas import BlockCanvas


class Harness(App):
    def __init__(self, blocks) -> None:
        super().__init__()
        self._blocks = blocks

    def compose(self) -> ComposeResult:
        yield BlockCanvas(self._blocks)


def _list(*texts, ordered=False):
    lst = new_list_block(ordered=ordered)
    items = []
    for t in texts:
        item = new_list_item()
        set_editable_body(item, t)
        items.append(item)
    set_container_children(lst, items)
    return lst


def _quote(*texts):
    quote = new_quote_block()
    paras = []
    for t in texts:
        para = new_paragraph_block()
        set_editable_body(para, t)
        paras.append(para)
    set_container_children(quote, paras)
    return quote


async def _focus_child(pilot, canvas, index):
    canvas._editors[index].query_one("#body").focus()
    await pilot.pause()


async def _settle(pilot):
    for _ in range(4):
        await pilot.pause()


def _item_texts(canvas):
    from wptui.blocks.text import get_editable_body
    from wptui.inline import document_to_markdown, html_to_document

    container = next(b for b in canvas.blocks if b.block_name in ("core/list", "core/quote"))
    return [document_to_markdown(html_to_document(get_editable_body(c) or "")) for c in container.inner_blocks]


@pytest.mark.asyncio
async def test_split_at_end_adds_empty_item_and_focuses_it():
    app = Harness([_list("first")])
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = app.query_one(BlockCanvas)
        await _focus_child(pilot, canvas, 0)
        assert await canvas.split_child("first", "")  # Enter at end
        await _settle(pilot)
        assert _item_texts(canvas) == ["first", ""]
        assert app.focused.text == "" and app.focused.cursor_location == (0, 0)


@pytest.mark.asyncio
async def test_split_mid_text_partitions_at_caret():
    app = Harness([_list("onetwo")])
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = app.query_one(BlockCanvas)
        await _focus_child(pilot, canvas, 0)
        assert await canvas.split_child("one", "two")  # Enter after "one"
        await _settle(pilot)
        assert _item_texts(canvas) == ["one", "two"]
        assert app.focused.text == "two" and app.focused.cursor_location == (0, 0)


@pytest.mark.asyncio
async def test_exit_from_empty_item_inserts_paragraph_after_list():
    app = Harness([_list("keep", "")])
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = app.query_one(BlockCanvas)
        await _focus_child(pilot, canvas, 1)  # the empty second item
        assert await canvas.exit_container()
        await _settle(pilot)
        assert _item_texts(canvas) == ["keep"]  # empty item gone, list survives
        out = serialize(canvas.blocks)
        assert out.index("<!-- /wp:list -->") < out.index("<!-- wp:paragraph -->")
        assert app.focused.text == ""  # focus in the new paragraph


@pytest.mark.asyncio
async def test_exit_from_only_item_removes_the_list():
    app = Harness([_list("")])
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = app.query_one(BlockCanvas)
        await _focus_child(pilot, canvas, 0)
        assert await canvas.exit_container()
        await _settle(pilot)
        out = serialize(canvas.blocks)
        assert "<!-- wp:list -->" not in out and "<!-- wp:paragraph -->" in out


@pytest.mark.asyncio
async def test_merge_joins_into_previous_with_caret_at_join():
    app = Harness([_list("one", "two")])
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = app.query_one(BlockCanvas)
        await _focus_child(pilot, canvas, 1)
        assert await canvas.merge_child_into_previous()
        await _settle(pilot)
        assert _item_texts(canvas) == ["onetwo"]
        assert app.focused.text == "onetwo" and app.focused.cursor_location == (0, 3)


@pytest.mark.asyncio
async def test_remove_empty_item_focuses_previous_end():
    app = Harness([_list("one", "")])
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = app.query_one(BlockCanvas)
        await _focus_child(pilot, canvas, 1)
        assert await canvas.remove_child()
        await _settle(pilot)
        assert _item_texts(canvas) == ["one"]
        assert app.focused.text == "one" and app.focused.cursor_location == (0, 3)


@pytest.mark.asyncio
async def test_remove_only_item_removes_list_and_focuses_neighbour():
    doc = "<!-- wp:paragraph -->\n<p>before</p>\n<!-- /wp:paragraph -->\n\n" + serialize([_list("")])
    app = Harness(parse(doc))
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = app.query_one(BlockCanvas)
        # the list-item editor is the second editor (after the "before" paragraph)
        await _focus_child(pilot, canvas, 1)
        assert await canvas.remove_child()
        await _settle(pilot)
        assert "<!-- wp:list -->" not in serialize(canvas.blocks)


@pytest.mark.asyncio
async def test_quote_paragraph_split_and_merge():
    app = Harness([_quote("hello")])
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = app.query_one(BlockCanvas)
        await _focus_child(pilot, canvas, 0)
        assert await canvas.split_child("hello", "")  # Enter at end -> second paragraph
        await _settle(pilot)
        assert serialize(canvas.blocks).count("<!-- wp:paragraph -->") == 2
        await _focus_child(pilot, canvas, 1)
        assert await canvas.merge_child_into_previous()
        await _settle(pilot)
        assert serialize(canvas.blocks).count("<!-- wp:paragraph -->") == 1


@pytest.mark.asyncio
async def test_editing_a_list_leaves_other_blocks_byte_identical():
    p1 = "<!-- wp:paragraph -->\n<p>First.</p>\n<!-- /wp:paragraph -->"
    p3 = "<!-- wp:paragraph -->\n<p>Third.</p>\n<!-- /wp:paragraph -->"
    doc = "\n\n".join([p1, serialize([_list("only")]), p3])
    app = Harness(parse(doc))
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = app.query_one(BlockCanvas)
        await _focus_child(pilot, canvas, 1)  # the list item
        assert await canvas.split_child("only", "")
        await _settle(pilot)
        out = serialize(canvas.blocks)
        assert out.startswith(p1) and out.endswith(p3)

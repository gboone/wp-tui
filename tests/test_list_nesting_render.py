"""Tests for rendering and editing list-items that contain a nested sublist (U1)."""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult

from wptui.blocks import parse, serialize
from wptui.blocks.containers import set_container_children
from wptui.blocks.factory import new_list_block, new_list_item
from wptui.blocks.model import Block
from wptui.blocks.text import get_editable_body, set_editable_body, set_list_item_body
from wptui.widgets.canvas import BlockCanvas
from wptui.widgets.text_block import TextBlockEditor


def _sublist(*texts):
    lst = new_list_block()
    items = []
    for t in texts:
        item = new_list_item()
        set_editable_body(item, t)
        items.append(item)
    set_container_children(lst, items)
    return lst


def _parent_with_sublist(text, *child_texts):
    """A core/list-item holding `text` plus a nested list of `child_texts`."""
    return Block(
        block_name="core/list-item",
        inner_blocks=[_sublist(*child_texts)],
        inner_content=[f"\n<li>{text}", None, "</li>\n"],
        inner_html=f"\n<li>{text}</li>\n",
        dirty=True,
    )


def _top_list(parent):
    lst = new_list_block()
    set_container_children(lst, [parent])
    return lst


class Harness(App):
    def __init__(self, blocks) -> None:
        super().__init__()
        self._blocks = blocks

    def compose(self) -> ComposeResult:
        yield BlockCanvas(self._blocks)


# ----------------------------------------------------------------- headless


def test_parent_with_sublist_serializes_and_roundtrips():
    top = _top_list(_parent_with_sublist("parent", "child1", "child2"))
    out = serialize([top])
    assert "<li>parent" in out and "<li>child1</li>" in out and "<li>child2</li>" in out
    assert out.count("<!-- wp:list -->") == 2  # outer + nested
    assert serialize(parse(out)) == out


def test_set_list_item_body_preserves_the_sublist():
    parent = _parent_with_sublist("parent", "child1", "child2")
    assert set_list_item_body(parent, "renamed")
    assert len(parent.inner_blocks) == 1  # sublist intact
    top = _top_list(parent)
    out = serialize([top])
    assert "<li>renamed" in out and "<li>child1</li>" in out and "<li>child2</li>" in out


def test_set_list_item_body_on_leaf_behaves_like_set_editable_body():
    leaf = new_list_item()
    set_editable_body(leaf, "old")
    assert set_list_item_body(leaf, "new")
    assert get_editable_body(leaf) == "new" and not leaf.inner_blocks


# ----------------------------------------------------------------- rendering


@pytest.mark.asyncio
async def test_nested_list_renders_parent_and_child_editors():
    top = _top_list(_parent_with_sublist("parent", "child1", "child2"))
    app = Harness([top])
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = app.query_one(BlockCanvas)
        editors = [e for e in canvas._editors if isinstance(e, TextBlockEditor)]
        bodies = [get_editable_body(e.block) for e in editors]
        assert bodies == ["parent", "child1", "child2"]


@pytest.mark.asyncio
async def test_editing_parent_text_via_commit_keeps_the_sublist():
    top = _top_list(_parent_with_sublist("parent", "child1", "child2"))
    app = Harness([top])
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = app.query_one(BlockCanvas)
        parent_editor = canvas._editors[0]
        parent_editor.query_one("#body").focus()
        await pilot.pause()
        parent_editor.query_one("#body").text = "renamed"
        canvas.sync()  # flush editors into blocks
        out = serialize(canvas.blocks)
        assert "<li>renamed" in out and "child1" in out and "child2" in out


@pytest.mark.asyncio
async def test_leaf_list_still_renders_and_edits():
    app = Harness([_sublist("a", "b")])
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = app.query_one(BlockCanvas)
        bodies = [get_editable_body(e.block) for e in canvas._editors]
        assert bodies == ["a", "b"]

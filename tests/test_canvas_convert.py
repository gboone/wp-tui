"""Tests for BlockCanvas.replace_focused — in-place block-type conversion (U3)."""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult

from wptui.blocks import parse, serialize
from wptui.blocks.factory import new_heading_block, new_list_block, new_quote_block, new_separator_block
from wptui.widgets.canvas import BlockCanvas
from wptui.widgets.inline_area import InlineMarkdownArea
from wptui.widgets.separator_card import SeparatorCard
from wptui.widgets.text_block import TextBlockEditor

P1 = "<!-- wp:paragraph -->\n<p>First.</p>\n<!-- /wp:paragraph -->"
EMPTY = "<!-- wp:paragraph -->\n<p></p>\n<!-- /wp:paragraph -->"
P3 = "<!-- wp:paragraph -->\n<p>Third.</p>\n<!-- /wp:paragraph -->"
DOC = "\n\n".join([P1, EMPTY, P3])


class Harness(App):
    def __init__(self, blocks) -> None:
        super().__init__()
        self._blocks = blocks

    def compose(self) -> ComposeResult:
        yield BlockCanvas(self._blocks)


async def _focus_editor(pilot, canvas, index):
    canvas._editors[index].query_one("#body").focus()
    await pilot.pause()


@pytest.mark.asyncio
async def test_convert_empty_paragraph_to_list_in_place():
    app = Harness(parse(DOC))
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = app.query_one(BlockCanvas)
        before = len(canvas.blocks)
        await _focus_editor(pilot, canvas, 1)  # the empty middle paragraph
        assert await canvas.replace_focused(new_list_block(ordered=False))
        await pilot.pause()

    assert len(canvas.blocks) == before  # positional swap, no block added/removed
    out = serialize(canvas.blocks)
    assert "<!-- wp:list -->" in out
    assert out.startswith(P1)  # first block byte-identical
    assert out.endswith(P3)  # last block byte-identical


@pytest.mark.asyncio
async def test_replace_with_no_focus_returns_false_and_mutates_nothing():
    app = Harness(parse(DOC))
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = app.query_one(BlockCanvas)
        canvas.screen.set_focus(None)
        await pilot.pause()
        before = serialize(canvas.blocks)
        assert await canvas.replace_focused(new_list_block()) is False
        assert serialize(canvas.blocks) == before


@pytest.mark.asyncio
async def test_convert_to_list_focuses_first_list_item_editor():
    app = Harness(parse(DOC))
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = app.query_one(BlockCanvas)
        await _focus_editor(pilot, canvas, 1)
        await canvas.replace_focused(new_list_block(ordered=False))
        await pilot.pause()
        focused = app.focused
        assert isinstance(focused, InlineMarkdownArea)
        editor = focused.ancestors_with_self[1]
        assert isinstance(editor, TextBlockEditor)
        assert editor.block.block_name == "core/list-item"


@pytest.mark.asyncio
async def test_converts_the_focused_block_when_a_structural_twin_exists():
    # Regression: two identical empty paragraphs are dataclass-equal, so a value-based
    # index would convert the FIRST one. The focused (second) block must convert.
    app = Harness(parse("\n\n".join([EMPTY, EMPTY])))
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = app.query_one(BlockCanvas)
        await _focus_editor(pilot, canvas, 1)  # focus the SECOND empty paragraph
        assert await canvas.replace_focused(new_heading_block(2))
        await pilot.pause()
    names = [b.block_name for b in canvas.blocks if b.block_name]
    assert names == ["core/paragraph", "core/heading"]  # first untouched, second converted


@pytest.mark.asyncio
async def test_replace_block_returns_false_when_target_is_gone():
    # The target captured before the picker opened may be removed before selection.
    app = Harness(parse(DOC))
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = app.query_one(BlockCanvas)
        await _focus_editor(pilot, canvas, 1)
        target = canvas.focused_block()
        canvas.blocks.remove(target)  # simulate a delete during the modal
        before = serialize(canvas.blocks)
        assert await canvas.replace_block(target, new_heading_block(2)) is False
        assert serialize(canvas.blocks) == before  # nothing mutated


@pytest.mark.asyncio
async def test_convert_to_quote_focuses_its_paragraph_child():
    app = Harness(parse(DOC))
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = app.query_one(BlockCanvas)
        await _focus_editor(pilot, canvas, 1)
        await canvas.replace_focused(new_quote_block())
        await pilot.pause()
        editor = app.focused.ancestors_with_self[1]
        assert isinstance(editor, TextBlockEditor)
        assert editor.block.block_name == "core/paragraph"  # the quote's child, focused


@pytest.mark.asyncio
async def test_convert_to_separator_focuses_card_without_crashing():
    app = Harness(parse(DOC))
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = app.query_one(BlockCanvas)
        await _focus_editor(pilot, canvas, 1)
        assert await canvas.replace_focused(new_separator_block())
        await pilot.pause()
        assert "<!-- wp:separator -->" in serialize(canvas.blocks)
        assert isinstance(app.focused, SeparatorCard)  # non-editor focus target, no crash


@pytest.mark.asyncio
async def test_convert_to_heading_focuses_heading_editor():
    app = Harness(parse(DOC))
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = app.query_one(BlockCanvas)
        await _focus_editor(pilot, canvas, 1)
        await canvas.replace_focused(new_heading_block(2))
        await pilot.pause()
        focused = app.focused
        assert isinstance(focused, InlineMarkdownArea)
        editor = focused.ancestors_with_self[1]
        assert editor.block.block_name == "core/heading"

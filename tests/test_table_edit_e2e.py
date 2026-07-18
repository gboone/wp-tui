"""End-to-end tests for table cell editing through the canvas (U3)."""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult

from wptui.blocks import parse, serialize
from wptui.widgets.canvas import BlockCanvas
from wptui.widgets.inline_area import InlineMarkdownArea
from wptui.widgets.opaque_card import OpaqueCard
from wptui.widgets.table_editor import TableEditor

TABLE = (
    "<!-- wp:table -->\n"
    '<figure class="wp-block-table"><table><tbody>'
    "<tr><td>A</td><td>B</td></tr></tbody></table></figure>\n"
    "<!-- /wp:table -->"
)
P1 = "<!-- wp:paragraph -->\n<p>First.</p>\n<!-- /wp:paragraph -->"
P3 = "<!-- wp:paragraph -->\n<p>Third.</p>\n<!-- /wp:paragraph -->"
COLUMNS = (
    "<!-- wp:columns -->\n"
    '<div class="wp-block-columns"><!-- wp:column -->\n'
    '<div class="wp-block-column"></div>\n<!-- /wp:column --></div>\n'
    "<!-- /wp:columns -->"
)


class Harness(App):
    def __init__(self, blocks) -> None:
        super().__init__()
        self._blocks = blocks

    def compose(self) -> ComposeResult:
        yield BlockCanvas(self._blocks)


@pytest.mark.asyncio
async def test_table_renders_as_editor_not_opaque():
    app = Harness(parse(TABLE))
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.query(TableEditor)
        assert not app.query(OpaqueCard)


@pytest.mark.asyncio
async def test_edit_cell_updates_table_and_leaves_neighbours_byte_identical():
    doc = "\n\n".join([P1, TABLE, P3])
    app = Harness(parse(doc))
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = app.query_one(BlockCanvas)
        app.query_one("#cell-0-0", InlineMarkdownArea).text = "edited"
        canvas.sync()
        out = serialize(canvas.blocks)
        assert "<td>edited</td>" in out and "<td>B</td>" in out
        assert out.startswith(P1) and out.endswith(P3)


@pytest.mark.asyncio
async def test_untouched_table_serializes_byte_identical():
    doc = "\n\n".join([P1, TABLE, P3])
    app = Harness(parse(doc))
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = app.query_one(BlockCanvas)
        canvas.sync()  # no edits
        assert serialize(canvas.blocks) == doc


@pytest.mark.asyncio
async def test_columns_block_still_renders_opaque():
    app = Harness(parse(COLUMNS))
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.query(OpaqueCard) and not app.query(TableEditor)

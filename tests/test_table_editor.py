"""Tests for the TableEditor widget (U2)."""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult

from wptui.blocks import parse, serialize
from wptui.widgets.inline_area import InlineMarkdownArea
from wptui.widgets.table_editor import TableEditor

TABLE_DOC = (
    "<!-- wp:table -->\n"
    '<figure class="wp-block-table"><table><tbody>'
    "<tr><td>A</td><td>B</td></tr>"
    "<tr><td>C</td><td>D</td></tr>"
    "</tbody></table></figure>\n"
    "<!-- /wp:table -->"
)

WITH_FORMAT_AND_HEADER = (
    "<!-- wp:table -->\n"
    '<figure class="wp-block-table"><table>'
    "<thead><tr><th>Name</th></tr></thead>"
    "<tbody><tr><td>a <strong>bold</strong> cell</td></tr></tbody>"
    "</table></figure>\n"
    "<!-- /wp:table -->"
)


def _table_block(doc):
    return parse(doc)[0]


class Harness(App):
    def __init__(self, block) -> None:
        super().__init__()
        self._block = block

    def compose(self) -> ComposeResult:
        yield TableEditor(self._block)


@pytest.mark.asyncio
async def test_renders_a_cell_editor_per_cell():
    block = _table_block(TABLE_DOC)
    app = Harness(block)
    async with app.run_test() as pilot:
        await pilot.pause()
        cells = app.query(InlineMarkdownArea)
        assert len(cells) == 4
        assert [c.text for c in cells] == ["A", "B", "C", "D"]


@pytest.mark.asyncio
async def test_editing_a_cell_updates_only_that_cell_and_dirties_block():
    block = _table_block(TABLE_DOC)
    app = Harness(block)
    async with app.run_test() as pilot:
        await pilot.pause()
        editor = app.query_one(TableEditor)
        app.query_one("#cell-0-1", InlineMarkdownArea).text = "changed"
        editor.commit()
        assert block.dirty
        out = serialize([block])
        assert "<td>changed</td>" in out
        assert "<td>A</td>" in out and "<td>C</td>" in out and "<td>D</td>" in out


@pytest.mark.asyncio
async def test_commit_with_no_edits_leaves_block_clean():
    block = _table_block(TABLE_DOC)
    original = serialize([block])
    app = Harness(block)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.query_one(TableEditor).commit()
        assert not block.dirty
        assert serialize([block]) == original


@pytest.mark.asyncio
async def test_header_cell_and_formatting_seed_as_markdown_and_commit_back():
    block = _table_block(WITH_FORMAT_AND_HEADER)
    app = Harness(block)
    async with app.run_test() as pilot:
        await pilot.pause()
        # header th seeds plain; body cell seeds bold as **bold**
        assert app.query_one("#cell-0-0", InlineMarkdownArea).text == "Name"
        assert app.query_one("#cell-1-0", InlineMarkdownArea).text == "a **bold** cell"
        app.query_one("#cell-0-0", InlineMarkdownArea).text = "Renamed"
        app.query_one(TableEditor).commit()
        out = serialize([block])
        assert "<th>Renamed</th>" in out  # still a th, edited
        assert "<strong>bold</strong>" in out  # untouched body cell preserved

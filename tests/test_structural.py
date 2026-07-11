"""Widget-level tests for Phase 4: rendering the full block set + move/delete/insert."""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult

from wptui.blocks import parse, serialize
from wptui.widgets.canvas import BlockCanvas
from wptui.widgets.opaque_card import OpaqueCard
from wptui.widgets.separator_card import SeparatorCard
from wptui.widgets.text_block import TextBlockEditor

PARA = "<!-- wp:paragraph -->\n<p>First para.</p>\n<!-- /wp:paragraph -->"
SEP = '<!-- wp:separator -->\n<hr class="wp-block-separator"/>\n<!-- /wp:separator -->'
LIST = (
    "<!-- wp:list -->\n<ul>"
    "<!-- wp:list-item --><li>one</li><!-- /wp:list-item -->\n"
    "<!-- wp:list-item --><li>two</li><!-- /wp:list-item -->"
    "</ul>\n<!-- /wp:list -->"
)
TABLE = (
    "<!-- wp:table -->\n<figure><table><tbody><tr><td>keep</td></tr>"
    "</tbody></table></figure>\n<!-- /wp:table -->"
)
DOC = "\n\n".join([PARA, SEP, LIST, TABLE])


class Harness(App):
    def __init__(self, blocks) -> None:
        super().__init__()
        self._blocks = blocks

    def compose(self) -> ComposeResult:
        yield BlockCanvas(self._blocks)


async def _focus_body(pilot, editor: TextBlockEditor) -> None:
    editor.query_one("#body").focus()
    await pilot.pause()


@pytest.mark.asyncio
async def test_renders_full_block_set():
    app = Harness(parse(DOC))
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = app.query_one(BlockCanvas)
        # paragraph + two list-items = 3 inline editors
        assert len(list(canvas.query(TextBlockEditor))) == 3
        assert len(list(canvas.query(SeparatorCard))) == 1
        assert len(list(canvas.query(OpaqueCard))) == 1  # the table
        # Clean round-trip when nothing was touched.
        assert serialize(canvas.blocks) == DOC


@pytest.mark.asyncio
async def test_move_block_down_reorders_top_level():
    app = Harness(parse(DOC))
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = app.query_one(BlockCanvas)
        para_editor = next(
            e for e in canvas.query(TextBlockEditor) if e.block.block_name == "core/paragraph"
        )
        await _focus_body(pilot, para_editor)

        assert await canvas.move_focused(+1) is True
        # The paragraph and the separator swapped; separator now leads.
        assert canvas.blocks[0].block_name == "core/separator"
        assert canvas.blocks[2].block_name == "core/paragraph"
        out = serialize(canvas.blocks)
        assert out.startswith(SEP)
        assert PARA in out and LIST in out and TABLE in out


@pytest.mark.asyncio
async def test_delete_focused_block_removes_it():
    app = Harness(parse(DOC))
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = app.query_one(BlockCanvas)
        table_card = app.query_one(OpaqueCard)
        table_card.focus()
        await pilot.pause()

        assert await canvas.delete_focused() is True
        names = [b.block_name for b in canvas.blocks]
        assert "core/table" not in names
        assert "core/list" in names  # siblings survive
        assert serialize(canvas.blocks).count("wp:table") == 0


@pytest.mark.asyncio
async def test_insert_paragraph_after_focused():
    app = Harness(parse(DOC))
    async with app.run_test() as pilot:
        await pilot.pause()
        canvas = app.query_one(BlockCanvas)
        para_editor = next(
            e for e in canvas.query(TextBlockEditor) if e.block.block_name == "core/paragraph"
        )
        await _focus_body(pilot, para_editor)

        before = sum(1 for b in canvas.blocks if b.block_name == "core/paragraph")
        assert await canvas.insert_paragraph() is True
        after = sum(1 for b in canvas.blocks if b.block_name == "core/paragraph")
        assert after == before + 1
        # The fresh paragraph serializes as valid, empty block grammar.
        assert "<!-- wp:paragraph -->\n<p></p>\n<!-- /wp:paragraph -->" in serialize(canvas.blocks)


@pytest.mark.asyncio
async def test_insert_paragraph_via_keybinding():
    """The Ctrl+N binding on the editor screen delegates to the canvas."""
    from wptui.api.dto import PostDetail, PostSummary
    from wptui.app import WPTuiApp
    from wptui.screens.editor import EditorScreen

    class Client:
        async def get_post(self, post_id):
            return PostDetail(post_id, "T", PARA, "draft", "2026-01-01T00:00:00", "http://x/1")

        async def aclose(self):
            pass

    app = WPTuiApp()
    app.client = Client()
    summary = PostSummary(1, "T", "draft", "2026-01-01T00:00:00", "http://x/1")
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(EditorScreen(summary))
        await pilot.pause()
        await pilot.pause()
        canvas = app.screen.query_one(BlockCanvas)
        editor = next(iter(canvas.query(TextBlockEditor)))
        editor.query_one("#body").focus()
        await pilot.pause()
        await pilot.press("ctrl+n")
        await pilot.pause()
        assert sum(1 for b in canvas.blocks if b.block_name == "core/paragraph") == 2

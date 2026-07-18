"""End-to-end tests for the slash-command block-type switcher trigger (U5)."""

from __future__ import annotations

import types

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Input

from wptui.api.dto import PostDetail, PostSummary
from wptui.app import WPTuiApp
from wptui.blocks import serialize
from wptui.keys import Mode
from wptui.screens.editor import EditorScreen
from wptui.widgets.block_switcher import BlockSwitcherModal
from wptui.widgets.canvas import BlockCanvas
from wptui.widgets.inline_area import InlineMarkdownArea

EMPTY_DOC = "<!-- wp:paragraph -->\n<p></p>\n<!-- /wp:paragraph -->"
FILLED_DOC = "<!-- wp:paragraph -->\n<p>hello</p>\n<!-- /wp:paragraph -->"


class _Client:
    def __init__(self, doc: str) -> None:
        self._doc = doc

    async def get_post(self, pid, post_type="post"):
        return PostDetail(pid, "T", self._doc, "draft", "2026-01-01T00:00:00", "http://x/1")

    async def aclose(self):
        pass


async def _open_editor(doc: str):
    app = WPTuiApp()
    app.client = _Client(doc)
    return app


async def _focus_first_body(app, pilot):
    canvas = app.screen._canvas
    canvas._editors[0].query_one("#body").focus()
    await pilot.pause()
    return canvas


@pytest.mark.asyncio
async def test_slash_on_empty_block_opens_modal_and_does_not_insert():
    app = await _open_editor(EMPTY_DOC)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(EditorScreen(PostSummary(1, "T", "draft", "2026-01-01T00:00:00", "http://x/1")))
        await pilot.pause()
        await pilot.pause()
        canvas = await _focus_first_body(app, pilot)
        body = canvas._editors[0].query_one("#body", InlineMarkdownArea)
        await pilot.press("/")
        await pilot.pause()
        assert isinstance(app.screen, BlockSwitcherModal)
        assert body.text == ""  # the "/" was not inserted


@pytest.mark.asyncio
async def test_full_path_converts_empty_paragraph_to_list():
    app = await _open_editor(EMPTY_DOC)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(EditorScreen(PostSummary(1, "T", "draft", "2026-01-01T00:00:00", "http://x/1")))
        await pilot.pause()
        await pilot.pause()
        canvas = await _focus_first_body(app, pilot)
        await pilot.press("/")
        await pilot.pause()
        app.screen.query_one("#switch-search", Input).value = "bulleted"
        await pilot.pause()
        await pilot.press("enter")
        for _ in range(4):
            await pilot.pause()
        out = serialize(canvas.blocks)
        assert "<!-- wp:list -->" in out and "<!-- wp:list-item -->" in out
        # Focus landed in the new list-item editor.
        focused = app.focused
        assert isinstance(focused, InlineMarkdownArea)
        assert focused.ancestors_with_self[1].block.block_name == "core/list-item"


@pytest.mark.asyncio
async def test_slash_in_non_empty_block_is_literal():
    app = await _open_editor(FILLED_DOC)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(EditorScreen(PostSummary(1, "T", "draft", "2026-01-01T00:00:00", "http://x/1")))
        await pilot.pause()
        await pilot.pause()
        canvas = await _focus_first_body(app, pilot)
        body = canvas._editors[0].query_one("#body", InlineMarkdownArea)
        body.move_cursor(body.document.end)
        await pilot.press("/")
        await pilot.pause()
        assert isinstance(app.screen, EditorScreen)  # no modal
        assert "/" in body.text


@pytest.mark.asyncio
async def test_escape_leaves_block_unchanged():
    app = await _open_editor(EMPTY_DOC)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(EditorScreen(PostSummary(1, "T", "draft", "2026-01-01T00:00:00", "http://x/1")))
        await pilot.pause()
        await pilot.pause()
        canvas = await _focus_first_body(app, pilot)
        before = serialize(canvas.blocks)
        await pilot.press("/")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, EditorScreen)
        assert serialize(canvas.blocks) == before  # still one empty paragraph, no "/"


EMPTY_LIST_DOC = (
    '<!-- wp:list -->\n<ul class="wp-block-list">'
    "<!-- wp:list-item -->\n<li></li>\n<!-- /wp:list-item -->"
    "</ul>\n<!-- /wp:list -->"
)
EMPTY_QUOTE_DOC = (
    '<!-- wp:quote -->\n<blockquote class="wp-block-quote">'
    "<!-- wp:paragraph -->\n<p></p>\n<!-- /wp:paragraph -->"
    "</blockquote>\n<!-- /wp:quote -->"
)


@pytest.mark.asyncio
async def test_slash_in_nested_quote_paragraph_is_literal():
    # A quote's child is a core/paragraph — same block_name as a top-level paragraph — so
    # this is the case most likely to slip past a guard keyed on type instead of ancestry.
    app = await _open_editor(EMPTY_QUOTE_DOC)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(EditorScreen(PostSummary(1, "T", "draft", "2026-01-01T00:00:00", "http://x/1")))
        await pilot.pause()
        await pilot.pause()
        canvas = await _focus_first_body(app, pilot)  # the quote's paragraph editor
        body = canvas._editors[0].query_one("#body", InlineMarkdownArea)
        await pilot.press("/")
        await pilot.pause()
        assert isinstance(app.screen, EditorScreen)  # no modal
        assert "/" in body.text  # typed literally
        assert "<!-- wp:quote -->" in serialize(canvas.blocks)  # quote intact


@pytest.mark.asyncio
async def test_slash_in_nested_list_item_is_literal_not_a_container_swap():
    # Regression guard: "/" in an empty list-item must NOT replace the whole list.
    app = await _open_editor(EMPTY_LIST_DOC)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(EditorScreen(PostSummary(1, "T", "draft", "2026-01-01T00:00:00", "http://x/1")))
        await pilot.pause()
        await pilot.pause()
        canvas = await _focus_first_body(app, pilot)  # the list-item editor
        body = canvas._editors[0].query_one("#body", InlineMarkdownArea)
        await pilot.press("/")
        await pilot.pause()
        assert isinstance(app.screen, EditorScreen)  # no modal opened
        assert "/" in body.text  # typed literally
        assert "<!-- wp:list -->" in serialize(canvas.blocks)  # list intact


# ------------------------------------------------------------------ vim gating (unit)


class _VimHarness(App):
    def compose(self) -> ComposeResult:
        yield InlineMarkdownArea("", id="body")


@pytest.mark.asyncio
async def test_slash_gating_respects_vim_mode():
    app = _VimHarness()
    async with app.run_test() as pilot:
        await pilot.pause()
        area = app.query_one("#body", InlineMarkdownArea)
        slash = types.SimpleNamespace(character="/", key="slash")

        app.vim_mode = False
        assert area._slash_triggers(slash) is True  # non-vim, empty block

        app.vim_mode = True
        area._vim.mode = Mode.NORMAL
        assert area._slash_triggers(slash) is False  # NORMAL "/" is a vim movement

        area._vim.mode = Mode.VISUAL
        assert area._slash_triggers(slash) is False  # VISUAL "/" is a vim movement too

        area._vim.mode = Mode.INSERT
        assert area._slash_triggers(slash) is True  # INSERT on empty block triggers

        area.insert("x")  # non-empty
        assert area._slash_triggers(slash) is False

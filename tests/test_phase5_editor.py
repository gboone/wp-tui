"""Widget-level tests for Phase 5: image editing, URL-paste link, and Vim mode."""

from __future__ import annotations

import pytest
from textual import events
from textual.app import App, ComposeResult
from textual.widgets.text_area import Selection

from wptui.api.dto import PostDetail, PostSummary
from wptui.widgets.inline_area import InlineMarkdownArea

IMAGE_DOC = (
    "<!-- wp:image -->\n"
    '<figure class="wp-block-image"><img src="https://x/a.png" alt="old"/></figure>\n'
    "<!-- /wp:image -->"
)
PARA_DOC = "<!-- wp:paragraph -->\n<p>Hello world.</p>\n<!-- /wp:paragraph -->"


class RecordingClient:
    def __init__(self, content: str) -> None:
        self._content = content
        self.saved_content: str | None = None

    async def get_post(self, post_id, post_type="post"):
        return PostDetail(post_id, "T", self._content, "draft", "2026-01-01T00:00:00", "http://x/1")

    async def update_post(self, post_id, *, content_raw=None, title_raw=None, settings=None, expected_modified_gmt=None):
        self.saved_content = content_raw
        return PostDetail(post_id, title_raw or "", content_raw or "", "draft", "2026-01-02T00:00:00", "http://x/1")

    async def aclose(self):
        pass


async def _open_editor(pilot, app, content):
    from wptui.screens.editor import EditorScreen

    app.push_screen(EditorScreen(PostSummary(1, "T", "draft", "2026-01-01T00:00:00", "http://x/1")))
    await pilot.pause()
    await pilot.pause()


# ------------------------------------------------------------------ image card


@pytest.mark.asyncio
async def test_image_card_edits_and_saves():
    from wptui.app import WPTuiApp
    from wptui.widgets.image_card import ImageCard

    client = RecordingClient(IMAGE_DOC)
    app = WPTuiApp()
    app.client = client
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_editor(pilot, app, IMAGE_DOC)

        card = app.screen.query_one(ImageCard)
        card.query_one("#img-src").value = "https://x/new.jpg"
        card.query_one("#img-alt").value = "new alt"
        card.query_one("#img-caption").value = "a **bold** caption"
        await pilot.pause()

        await pilot.press("ctrl+s")
        await pilot.pause()
        await pilot.pause()

    out = client.saved_content
    assert out is not None
    assert 'src="https://x/new.jpg"' in out
    assert 'alt="new alt"' in out
    assert "<figcaption" in out and "a <strong>bold</strong> caption" in out


# --------------------------------------------------------------- paste as link


class Harness(App):
    def compose(self) -> ComposeResult:
        yield InlineMarkdownArea("select me please", id="a")


@pytest.mark.asyncio
async def test_paste_url_over_selection_makes_link():
    app = Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        area = app.query_one("#a", InlineMarkdownArea)
        area.focus()
        area.selection = Selection((0, 0), (0, 6))  # "select"
        await pilot.pause()
        await area._on_paste(events.Paste("https://example.com"))
        assert area.text.startswith("[select](https://example.com)")


@pytest.mark.asyncio
async def test_paste_non_url_over_selection_is_normal():
    app = Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        area = app.query_one("#a", InlineMarkdownArea)
        area.focus()
        area.selection = Selection((0, 0), (0, 6))
        await pilot.pause()
        await area._on_paste(events.Paste("plain text"))
        # Selection replaced by the pasted text; no link syntax added.
        assert "[" not in area.text
        assert area.text.startswith("plain text")


@pytest.mark.asyncio
async def test_paste_not_duplicated_through_event_dispatch():
    # Regression: Paste bubbles and the Screen re-forwards it to the focused widget, so a
    # handler that doesn't stop the event inserts the pasted text twice. Post a REAL Paste
    # (not a direct _on_paste call) so the dispatch-doubling is exercised.
    app = Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        area = app.query_one("#a", InlineMarkdownArea)
        area.focus()
        area.text = "[example link]()"
        area.move_cursor((0, 15))  # between the parens, no selection
        await pilot.pause()
        area.post_message(events.Paste("https://example.com"))
        await pilot.pause()
        await pilot.pause()
        assert area.text == "[example link](https://example.com)"


@pytest.mark.asyncio
async def test_plain_paste_not_duplicated_through_event_dispatch():
    app = Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        area = app.query_one("#a", InlineMarkdownArea)
        area.focus()
        area.text = ""
        area.move_cursor((0, 0))
        await pilot.pause()
        area.post_message(events.Paste("hello"))
        await pilot.pause()
        await pilot.pause()
        assert area.text == "hello"


# ----------------------------------------------------------------------- vim


@pytest.mark.asyncio
async def test_vim_delete_char_and_insert():
    from wptui.keys import Mode

    app = Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        area = app.query_one("#a", InlineMarkdownArea)
        area.focus()
        area.text = "hello"
        area.move_cursor((0, 0))
        app.vim_mode = True
        area.refresh_vim()
        await pilot.pause()

        await pilot.press("x")  # delete char under cursor
        await pilot.pause()
        assert area.text == "ello"

        await pilot.press("i")  # insert before
        assert area._vim.mode is Mode.INSERT
        await pilot.press("Z")
        await pilot.pause()
        assert area.text == "Zello"

        await pilot.press("escape")
        assert area._vim.mode is Mode.NORMAL


@pytest.mark.asyncio
async def test_vim_write_command_saves():
    from wptui.app import WPTuiApp

    client = RecordingClient(PARA_DOC)
    app = WPTuiApp()
    app.client = client
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_editor(pilot, app, PARA_DOC)
        app.vim_mode = True
        area = app.screen.query_one(InlineMarkdownArea)
        area.focus()
        area.refresh_vim()
        await pilot.pause()

        # :w<enter>
        await pilot.press("colon")
        await pilot.press("w")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

    assert client.saved_content is not None
    assert "<p>Hello world.</p>" in client.saved_content

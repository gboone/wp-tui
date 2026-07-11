"""Phase 3 milestone: markdown-style editing round-trips through the editor widget."""

from __future__ import annotations

import pytest

from wptui.api.dto import PostDetail, PostSummary

# A paragraph that already carries inline formatting, plus an opaque table to guard.
POST_CONTENT = (
    "<!-- wp:paragraph -->\n"
    '<p>Intro with <em>emphasis</em> and a <a href="https://x.io">link</a>.</p>\n'
    "<!-- /wp:paragraph -->\n\n"
    "<!-- wp:table -->\n<figure><table><tbody><tr><td>keep</td></tr></tbody></table></figure>\n"
    "<!-- /wp:table -->"
)


class RecordingClient:
    def __init__(self) -> None:
        self.saved_content: str | None = None

    async def get_post(self, post_id: int) -> PostDetail:
        return PostDetail(
            id=post_id,
            title_raw="My Post",
            content_raw=POST_CONTENT,
            status="draft",
            modified_gmt="2026-01-01T00:00:00",
            link="http://x/1",
        )

    async def update_post(
        self, post_id, *, content_raw=None, title_raw=None, expected_modified_gmt=None
    ) -> PostDetail:
        self.saved_content = content_raw
        return PostDetail(
            id=post_id,
            title_raw=title_raw or "",
            content_raw=content_raw or "",
            status="draft",
            modified_gmt="2026-01-02T00:00:00",
            link="http://x/1",
        )

    async def aclose(self) -> None:
        pass


@pytest.mark.asyncio
async def test_markdown_edit_saves_as_wp_html_and_preserves_opaque():
    from wptui.app import WPTuiApp
    from wptui.screens.editor import EditorScreen
    from wptui.widgets.inline_area import InlineMarkdownArea
    from wptui.widgets.text_block import TextBlockEditor

    client = RecordingClient()
    app = WPTuiApp()
    app.client = client

    summary = PostSummary(1, "My Post", "draft", "2026-01-01T00:00:00", "http://x/1")

    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(EditorScreen(summary))
        await pilot.pause()
        await pilot.pause()

        editors = list(app.screen.query(TextBlockEditor))
        assert len(editors) == 1
        area = editors[0].query_one("#body", InlineMarkdownArea)

        # Existing WP formatting is shown to the user as markdown-style markers.
        assert area.text == "Intro with *emphasis* and a [link](https://x.io)."

        # The live-highlight map tags the emphasis and marks the delimiters as dim.
        names = {name for spans in area._highlights.values() for *_, name in spans}
        assert "italic" in names
        assert "link" in names
        assert "marker" in names

        # Edit: make the intro word bold.
        area.text = "**Bold** with *emphasis* and a [link](https://x.io)."
        await pilot.pause()

        await pilot.press("ctrl+s")
        await pilot.pause()
        await pilot.pause()

    out = client.saved_content
    assert out is not None
    # Markdown became real WordPress inline HTML.
    assert "<strong>Bold</strong>" in out
    assert "<em>emphasis</em>" in out
    assert '<a href="https://x.io">link</a>' in out
    # The opaque table block is preserved byte-for-byte.
    assert (
        "<!-- wp:table -->\n<figure><table><tbody><tr><td>keep</td></tr>"
        "</tbody></table></figure>\n<!-- /wp:table -->"
    ) in out

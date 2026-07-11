"""End-to-end editor test: edit a paragraph, save, and check the PUT payload."""

from __future__ import annotations

import pytest

from wptui.api.dto import PostDetail, PostSummary

POST_CONTENT = (
    "<!-- wp:paragraph -->\n<p>Original text.</p>\n<!-- /wp:paragraph -->\n\n"
    '<!-- wp:table -->\n<figure class="wp-block-table"><table><tbody>'
    "<tr><td>keep me exact</td></tr></tbody></table></figure>\n<!-- /wp:table -->"
)


class RecordingClient:
    """Captures the content sent to update_post."""

    def __init__(self) -> None:
        self.saved_content: str | None = None
        self.saved_title: str | None = None

    async def get_post(self, post_id: int, post_type: str = "post") -> PostDetail:
        return PostDetail(
            id=post_id,
            title_raw="My Post",
            content_raw=POST_CONTENT,
            status="draft",
            modified_gmt="2026-01-01T00:00:00",
            link="http://x/1",
        )

    async def update_post(
        self, post_id, *, content_raw=None, title_raw=None, settings=None, expected_modified_gmt=None
    ) -> PostDetail:
        self.saved_content = content_raw
        self.saved_title = title_raw
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
async def test_edit_paragraph_saves_and_preserves_opaque_blocks():
    from wptui.app import WPTuiApp
    from wptui.screens.editor import EditorScreen
    from wptui.widgets.text_block import TextBlockEditor

    client = RecordingClient()
    app = WPTuiApp()
    app.client = client  # inject fake client, skip the connect screen

    summary = PostSummary(1, "My Post", "draft", "2026-01-01T00:00:00", "http://x/1")

    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(EditorScreen(summary))
        await pilot.pause()
        await pilot.pause()

        editor = app.screen
        assert isinstance(editor, EditorScreen)

        # There should be exactly one editable text block (the paragraph) and the
        # table should be an opaque card.
        text_editors = list(app.screen.query(TextBlockEditor))
        assert len(text_editors) == 1
        body = text_editors[0].query_one("#body")
        assert body.text == "Original text."

        # Edit the paragraph body.
        body.text = "Brand new text."
        await pilot.pause()

        # Save.
        await pilot.press("ctrl+s")
        await pilot.pause()
        await pilot.pause()

    assert client.saved_content is not None
    out = client.saved_content
    # Edited paragraph reflects the change...
    assert "<p>Brand new text.</p>" in out
    assert "Original text." not in out
    # ...and the opaque table block is preserved byte-for-byte.
    assert (
        '<!-- wp:table -->\n<figure class="wp-block-table"><table><tbody>'
        "<tr><td>keep me exact</td></tr></tbody></table></figure>\n<!-- /wp:table -->"
    ) in out
    # The inter-block whitespace is preserved too.
    assert "<!-- /wp:paragraph -->\n\n<!-- wp:table -->" in out

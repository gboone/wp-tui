"""Editor card for ``core/image``: edit the URL, alt text, and caption.

v1 references existing media (no upload) — the URL is whatever the user types or pastes.
The caption is edited with the same markdown-style inline engine as text blocks; alt and
URL are plain values. The ``commit()`` contract matches :class:`TextBlockEditor` so the
canvas treats both uniformly.
"""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Button, Input, Static

from wptui.blocks.image import get_image_parts, set_image_parts
from wptui.blocks.model import Block
from wptui.inline import (
    document_to_html,
    document_to_markdown,
    html_to_document,
    markdown_to_document,
)


class ImageCard(Vertical):
    """A labeled form bound to one image block."""

    def __init__(self, block: Block) -> None:
        super().__init__()
        self.block = block
        parts = get_image_parts(block)
        self._src = parts.src if parts else ""
        self._alt = parts.alt if parts else ""
        self._caption = (
            document_to_markdown(html_to_document(parts.caption_html)) if parts else ""
        )

    def compose(self) -> ComposeResult:
        yield Static("🖼 image", classes="image-label")
        yield Input(value=self._src, placeholder="image URL", id="img-src", classes="image-field")
        yield Input(value=self._alt, placeholder="alt text", id="img-alt", classes="image-field")
        yield Input(
            value=self._caption, placeholder="caption", id="img-caption", classes="image-field"
        )
        yield Button("Choose image…", id="img-card-upload", classes="image-field")

    @on(Button.Pressed, "#img-card-upload")
    def _open_upload(self) -> None:
        from wptui.widgets.media_picker import MediaPickerModal

        self.app.push_screen(MediaPickerModal(), self._uploaded)

    def _uploaded(self, media) -> None:
        """Fill this card's fields from a chosen/uploaded media item."""
        if media is None:
            return
        self.query_one("#img-src", Input).value = media.source_url
        if media.alt:
            self.query_one("#img-alt", Input).value = media.alt
        if media.caption_raw:
            self.query_one("#img-caption", Input).value = media.caption_raw

    def commit(self) -> None:
        """Write the current field values back into the block if they changed."""
        src = self.query_one("#img-src", Input).value
        alt = self.query_one("#img-alt", Input).value
        caption = self.query_one("#img-caption", Input).value
        if (src, alt, caption) == (self._src, self._alt, self._caption):
            return
        caption_html = document_to_html(markdown_to_document(caption)) if caption else ""
        set_image_parts(self.block, src=src, alt=alt, caption_html=caption_html)
        self._src, self._alt, self._caption = src, alt, caption

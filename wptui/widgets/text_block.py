"""Editable text-block widget with live markdown-style inline formatting (Phase 3).

The block stores WordPress inner-HTML (``Hi <strong>bold</strong>``); the user edits it
as markdown-style text (``Hi **bold**``) in an :class:`InlineMarkdownArea` that live-styles
the markers. On load, HTML is converted to markdown for display; on ``commit()``, markdown
is converted back to WordPress HTML. The ``commit()`` contract is unchanged from Phase 2 so
the canvas is unaffected by the swap.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from wptui.blocks.model import Block
from wptui.blocks.text import get_editable_body, set_editable_body
from wptui.inline import html_to_markdown, markdown_to_html
from wptui.widgets.inline_area import InlineMarkdownArea


class TextBlockEditor(Vertical):
    """A labeled editor bound to one editable text block."""

    def __init__(self, block: Block) -> None:
        super().__init__()
        self.block = block
        html_body = get_editable_body(block) or ""
        # Display the block as markdown-style markers; keep the seed to detect edits.
        self._markdown = html_to_markdown(html_body)

    def compose(self) -> ComposeResult:
        name = (self.block.block_name or "").removeprefix("core/")
        if self.block.block_name == "core/heading":
            name = f"heading {self.block.attributes.get('level', 2)}"
        yield Static(name, classes="block-label")
        yield InlineMarkdownArea(self._markdown, id="body", classes="block-body")

    def commit(self) -> None:
        """Write the current editor markdown back into the block if it changed."""
        area = self.query_one("#body", InlineMarkdownArea)
        new_markdown = area.text
        if new_markdown != self._markdown:
            new_html = markdown_to_html(new_markdown)
            set_editable_body(self.block, new_html)
            self._markdown = new_markdown

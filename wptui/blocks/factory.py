"""Factories for brand-new blocks created in the editor (Phase 4 insertion)."""

from __future__ import annotations

from wptui.blocks.model import Block

# WordPress separates top-level blocks with a blank line.
BLOCK_SEPARATOR = "\n\n"


def new_paragraph_block() -> Block:
    """An empty, already-dirty paragraph ready to serialize as valid block grammar."""
    inner = "\n<p></p>\n"
    return Block(
        block_name="core/paragraph",
        inner_html=inner,
        inner_content=[inner],
        dirty=True,
    )


def separator_freeform() -> Block:
    """A freeform whitespace block used to space inserted top-level blocks apart."""
    return Block(
        block_name=None,
        inner_html=BLOCK_SEPARATOR,
        inner_content=[BLOCK_SEPARATOR],
        original_raw=BLOCK_SEPARATOR,
    )

"""Factories for brand-new blocks created in the editor."""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING

from wptui.blocks.model import Block

if TYPE_CHECKING:  # avoid a runtime dependency; factory stays in the headless layer
    from wptui.api.dto import MediaItem

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


def new_image_block(media: "MediaItem", *, alt: str = "", caption: str = "") -> Block:
    """Mint a ``core/image`` block referencing an uploaded media item.

    Uses the same inner-HTML shape that ``blocks/image.py`` reads and the serializer
    round-trips, so an inserted image behaves like any other block. ``alt``/``caption``
    default to the media item's own values when not given.
    """
    alt_text = alt or media.alt
    caption_text = caption or media.caption_raw
    figcaption = (
        f'<figcaption class="wp-element-caption">{escape(caption_text)}</figcaption>'
        if caption_text
        else ""
    )
    inner = (
        '\n<figure class="wp-block-image size-full">'
        f'<img src="{escape(media.source_url, quote=True)}" '
        f'alt="{escape(alt_text, quote=True)}" class="wp-image-{media.id}"/>'
        f"{figcaption}</figure>\n"
    )
    return Block(
        block_name="core/image",
        attributes={"id": media.id, "sizeSlug": "full", "linkDestination": "none"},
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

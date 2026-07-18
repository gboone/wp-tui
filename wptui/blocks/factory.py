"""Factories for brand-new blocks created in the editor."""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING

from wptui.blocks.model import Block
from wptui.blocks.text import get_editable_body, split_wrapper

if TYPE_CHECKING:  # avoid a runtime dependency; factory stays in the headless layer
    from wptui.api.dto import MediaItem

# WordPress separates top-level blocks with a blank line.
BLOCK_SEPARATOR = "\n\n"


def _leaf_block(block_name: str, inner: str, attributes: dict | None = None) -> Block:
    """A minted, already-``dirty`` single-wrapper block (no child blocks)."""
    return Block(
        block_name=block_name,
        attributes=attributes or {},
        inner_html=inner,
        inner_content=[inner],
        dirty=True,
    )


def new_paragraph_block() -> Block:
    """An empty, already-dirty paragraph ready to serialize as valid block grammar."""
    return _leaf_block("core/paragraph", "\n<p></p>\n")


def new_heading_block(level: int = 2) -> Block:
    """An empty ``core/heading`` at the given level. WordPress omits the ``level``
    attribute for the default H2 and includes it otherwise."""
    attributes = {} if level == 2 else {"level": level}
    return _leaf_block(
        "core/heading", f'\n<h{level} class="wp-block-heading"></h{level}>\n', attributes
    )


def set_heading_level(block: Block, level: int) -> None:
    """Change a ``core/heading`` block's level in place, preserving its body.

    Swaps only the wrapper tag name (keeping any other wrapper attributes — an anchor id,
    alignment class — intact) and updates the ``level`` attribute to match WordPress
    (``level`` omitted for the default H2, present otherwise). Clears ``attributes_raw`` so
    the changed attributes re-encode, and marks the block dirty. Falls back to a fresh
    wrapper if the inner HTML isn't a recognizable single wrapper."""
    old = block.attributes.get("level", 2)
    wrapped = split_wrapper(block.inner_html)
    if wrapped is None:
        inner = f'\n<h{level} class="wp-block-heading">{get_editable_body(block) or ""}</h{level}>\n'
    else:
        prefix = wrapped.prefix.replace(f"<h{old}", f"<h{level}", 1)
        suffix = wrapped.suffix.replace(f"</h{old}>", f"</h{level}>", 1)
        inner = f"{prefix}{wrapped.body}{suffix}"
    block.inner_html = inner
    block.inner_content = [inner]
    if level == 2:
        block.attributes.pop("level", None)
    else:
        block.attributes["level"] = level
    block.attributes_raw = None
    block.mark_dirty()


def new_list_item(body: str = "") -> Block:
    """A single ``core/list-item`` child (matches WordPress's ``\\n<li>…</li>\\n`` shape)."""
    return _leaf_block("core/list-item", f"\n<li>{body}</li>\n")


def _container_block(
    block_name: str, open_chunk: str, close_chunk: str, child: Block, attributes: dict | None = None
) -> Block:
    """A minted, already-``dirty`` container wrapping a single child block.

    ``inner_content`` interleaves the wrapper chunks with a ``None`` placeholder marking
    where the child block is spliced back in on serialization. Both container and child
    are ``dirty`` so serialization rebuilds them from structure.
    """
    return Block(
        block_name=block_name,
        attributes=attributes or {},
        inner_blocks=[child],
        inner_html=f"{open_chunk}{close_chunk}",
        inner_content=[open_chunk, None, close_chunk],
        dirty=True,
    )


def new_list_block(ordered: bool = False) -> Block:
    """An empty ``core/list`` (``<ul>``/``<ol>``) wrapping one empty ``core/list-item``."""
    tag = "ol" if ordered else "ul"
    attributes = {"ordered": True} if ordered else {}
    return _container_block(
        "core/list", f'\n<{tag} class="wp-block-list">', f"</{tag}>\n", new_list_item(), attributes
    )


def new_quote_block() -> Block:
    """An empty ``core/quote`` wrapping one empty ``core/paragraph`` (WordPress's shape)."""
    return _container_block(
        "core/quote", '\n<blockquote class="wp-block-quote">', "</blockquote>\n", new_paragraph_block()
    )


def new_code_block() -> Block:
    """An empty ``core/code`` block (``<pre class="wp-block-code"><code></code></pre>``)."""
    return _leaf_block("core/code", '\n<pre class="wp-block-code"><code></code></pre>\n')


def new_preformatted_block() -> Block:
    """An empty ``core/preformatted`` block."""
    return _leaf_block("core/preformatted", '\n<pre class="wp-block-preformatted"></pre>\n')


def new_separator_block() -> Block:
    """A ``core/separator`` (horizontal rule)."""
    return _leaf_block(
        "core/separator", '\n<hr class="wp-block-separator has-alpha-channel-opacity"/>\n'
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

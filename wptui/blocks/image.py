"""Surgical accessors for ``core/image`` inner HTML (alt / caption / URL).

An image block's inner HTML looks like::

    <figure class="wp-block-image size-large">
      <img src="https://x/p.jpg" alt="Alt" class="wp-image-12"/>
      <figcaption class="wp-element-caption">A caption</figcaption>
    </figure>

To keep the round-trip tight, edits patch only the ``src``/``alt`` attribute values and
the ``<figcaption>`` body in place — every class, id, and whitespace byte is otherwise
left untouched. The caption body is HTML (produced by the inline engine); alt and src are
plain values that are attribute-escaped on write and unescaped on read.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape, unescape

from wptui.blocks.model import Block

_IMG_RE = re.compile(r"<img\b[^>]*>", re.DOTALL)
_FIGCAP_RE = re.compile(r"<figcaption\b[^>]*>(.*?)</figcaption>", re.DOTALL)


def _attr_re(name: str) -> re.Pattern[str]:
    # Accept either quote style; group 2 is the delimiter, group 3 the value.
    return re.compile(r"(\b" + re.escape(name) + r"=)([\"'])(.*?)\2", re.DOTALL)


@dataclass(frozen=True)
class ImageParts:
    """The user-editable pieces of an image block."""

    src: str
    alt: str
    caption_html: str  # raw inner HTML of the <figcaption>, "" if none


def _get_attr(tag: str, name: str) -> str:
    match = _attr_re(name).search(tag)
    return unescape(match.group(3)) if match else ""


def _set_attr(tag: str, name: str, value: str) -> str:
    escaped = escape(value, quote=True)
    match = _attr_re(name).search(tag)
    if match is not None:
        # Replace only the value, preserving the original quote delimiter.
        return tag[: match.start(3)] + escaped + tag[match.end(3) :]
    # Attribute absent: insert it right after "<img".
    return tag[:4] + f' {name}="{escaped}"' + tag[4:]


def get_image_parts(block: Block) -> ImageParts | None:
    """Extract the src/alt/caption from an image block, or ``None`` if it has no img."""
    match = _IMG_RE.search(block.inner_html)
    if match is None:
        return None
    tag = match.group(0)
    caption = _FIGCAP_RE.search(block.inner_html)
    return ImageParts(
        src=_get_attr(tag, "src"),
        alt=_get_attr(tag, "alt"),
        caption_html=caption.group(1) if caption else "",
    )


def set_image_parts(block: Block, *, src: str, alt: str, caption_html: str) -> bool:
    """Patch src/alt/caption back into the block, preserving all other markup.

    Returns ``False`` if the block has no ``<img>`` to edit.
    """
    match = _IMG_RE.search(block.inner_html)
    if match is None:
        return False
    tag = match.group(0)
    new_tag = _set_attr(_set_attr(tag, "src", src), "alt", alt)
    inner = block.inner_html[: match.start()] + new_tag + block.inner_html[match.end() :]
    inner = _set_caption(inner, caption_html)

    block.inner_html = inner
    block.inner_content = [inner]
    block.inner_blocks = []
    block.mark_dirty()
    return True


def _set_caption(inner: str, caption_html: str) -> str:
    match = _FIGCAP_RE.search(inner)
    if caption_html:
        figcaption = f'<figcaption class="wp-element-caption">{caption_html}</figcaption>'
        if match:
            return inner[: match.start(1)] + caption_html + inner[match.end(1) :]
        close = inner.rfind("</figure>")
        if close != -1:
            return inner[:close] + figcaption + inner[close:]
        # No <figure>: wrap the img with the caption so the figcaption is well-formed
        # rather than dangling after the markup.
        img = _IMG_RE.search(inner)
        if img is not None:
            wrapped = f"<figure>{img.group(0)}{figcaption}</figure>"
            return inner[: img.start()] + wrapped + inner[img.end() :]
        return inner  # nothing to attach a caption to
    # Empty caption: drop an existing figcaption entirely.
    return inner[: match.start()] + inner[match.end() :] if match else inner

"""Helpers for editing simple text blocks while preserving their HTML wrapper.

A text block like a paragraph stores inner HTML such as ``"\\n<p class=\\"x\\">Hi</p>\\n"``.
When the user edits "the text", we must preserve the surrounding whitespace, the wrapper
tag, and its attributes, and change only the content between the tags.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from wptui.blocks.model import Block

# Matches: leading ws + a single wrapper element + trailing ws, capturing the inner body.
# The wrapper is the first tag (p, h1-6, pre, blockquote, ...); \1 back-reference closes it.
_WRAPPER_RE = re.compile(
    r"^(?P<prefix>\s*<(?P<tag>[a-zA-Z][\w-]*)(?:\s[^>]*)?>)"
    r"(?P<body>.*)"
    r"(?P<suffix></(?P=tag)>\s*)$",
    re.DOTALL,
)


@dataclass(frozen=True)
class WrappedText:
    """A text block's inner HTML split into an editable body plus its fixed wrapper."""

    prefix: str  # leading whitespace + opening tag (with attributes)
    body: str    # the editable inner HTML
    suffix: str  # closing tag + trailing whitespace

    def rebuild(self, new_body: str) -> str:
        return f"{self.prefix}{new_body}{self.suffix}"


def split_wrapper(inner_html: str) -> WrappedText | None:
    """Split ``inner_html`` into (prefix, body, suffix); ``None`` if not a single wrapper."""
    match = _WRAPPER_RE.match(inner_html)
    if match is None:
        return None
    return WrappedText(
        prefix=match.group("prefix"),
        body=match.group("body"),
        suffix=match.group("suffix"),
    )


def get_editable_body(block: Block) -> str | None:
    """Return the editable inner-HTML body of a simple text block, or ``None``."""
    wrapped = split_wrapper(block.inner_html)
    return wrapped.body if wrapped is not None else None


def set_editable_body(block: Block, new_body: str) -> bool:
    """Write ``new_body`` back into a simple text block, preserving its wrapper.

    Marks the block dirty and keeps ``inner_content`` consistent. Returns ``False`` if
    the block has no single-wrapper body (e.g. it contains nested blocks).
    """
    wrapped = split_wrapper(block.inner_html)
    if wrapped is None:
        return False
    rebuilt = wrapped.rebuild(new_body)
    block.inner_html = rebuilt
    block.inner_content = [rebuilt]
    block.inner_blocks = []
    block.mark_dirty()
    return True

"""Parser for the WordPress block grammar.

Mirrors the algorithm of the official ``@wordpress/block-serialization-default-parser``
(a stack machine over HTML-comment delimiters), and additionally records each block's
exact source span (``original_raw``) so untouched blocks re-serialize byte-for-byte.

Delimiter forms handled::

    <!-- wp:paragraph -->…<!-- /wp:paragraph -->     opener / closer
    <!-- wp:image {"id":5} /-->                       self-closing (void)
    <!-- wp:acme/widget {"x":1} -->…<!-- /wp:acme/widget -->

Core blocks are written without the ``core/`` namespace in the delimiter; we normalize
``block_name`` to the full ``core/…`` form while preserving the original text verbatim.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from wptui.blocks.model import Block

# One regex matching any block delimiter comment. ``name`` includes an optional
# ``namespace/`` prefix. ``attrs`` uses a negative lookahead so nested ``}`` inside the
# JSON don't terminate the match early — only a ``}`` followed by ``\s+/?-->`` does.
_TOKEN_RE = __import__("re").compile(
    r"<!--\s+"
    r"(?P<closer>/)?"
    r"wp:"
    r"(?P<name>[a-z][a-z0-9_-]*(?:/[a-z][a-z0-9_-]*)?)"
    r"(?:\s+(?P<attrs>\{(?:(?!\}\s+/?-->).)*?\}))?"
    r"\s+"
    r"(?P<void>/)?"
    r"-->",
    __import__("re").DOTALL,
)


@dataclass
class _Frame:
    """A block whose opener has been seen but whose closer has not yet."""

    block: Block
    token_start: int  # source offset of this block's opening delimiter
    prev_offset: int  # source offset just past the last consumed inner token
    leading_html_start: int | None  # start of freeform text preceding this opener


def parse(document: str) -> list[Block]:
    """Parse block-grammar ``document`` into a flat list of top-level blocks.

    Freeform HTML between/around blocks becomes ``Block`` nodes with
    ``block_name is None``. Nested blocks are attached to their parent's
    ``inner_blocks`` / ``inner_content``.
    """
    output: list[Block] = []
    stack: list[_Frame] = []
    offset = 0

    for match in _TOKEN_RE.finditer(document):
        token_start = match.start()
        token_end = match.end()
        # Freeform text preceding this token spans [offset, token_start).
        leading_html_start = offset if token_start > offset else None

        kind = _classify(match)

        if kind == "void":
            block = _make_block(match, document[token_start:token_end])
            if not stack:
                _emit_leading(document, leading_html_start, token_start, output)
                output.append(block)
            else:
                _add_inner(stack[-1], block, document, token_start, token_end)
            offset = token_end

        elif kind == "opener":
            stack.append(
                _Frame(
                    block=_make_block(match, ""),
                    token_start=token_start,
                    prev_offset=token_end,
                    leading_html_start=leading_html_start,
                )
            )
            offset = token_end

        else:  # closer
            if not stack:
                # Stray closer with no opener: keep it as freeform so nothing is lost.
                _emit_freeform(document[offset:token_end], output)
                offset = token_end
                continue
            frame = stack.pop()
            _close_frame(frame, document, token_start)
            frame.block.original_raw = document[frame.token_start:token_end]
            if stack:
                parent = stack[-1]
                _splice_inner_html(parent, document, frame.token_start)
                parent.block.inner_blocks.append(frame.block)
                parent.block.inner_content.append(None)
                parent.prev_offset = token_end
            else:
                _emit_leading(document, frame.leading_html_start, frame.token_start, output)
                output.append(frame.block)
            offset = token_end

    # Any unterminated openers: fall back to emitting their raw source so we never
    # drop bytes (malformed input).
    for frame in stack:
        _emit_freeform(document[frame.token_start:], output)
        return output  # remaining tokens already consumed into this tail

    # Trailing freeform after the last token.
    if offset < len(document):
        _emit_freeform(document[offset:], output)

    return output


def _classify(match) -> str:
    if match.group("closer"):
        return "closer"
    if match.group("void"):
        return "void"
    return "opener"


def _make_block(match, original_raw: str) -> Block:
    name = _full_name(match.group("name"))
    attrs = _parse_attrs(match.group("attrs"))
    return Block(block_name=name, attributes=attrs, original_raw=original_raw)


def _full_name(name: str) -> str:
    return name if "/" in name else f"core/{name}"


def _parse_attrs(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _add_inner(parent: _Frame, block: Block, document: str, start: int, end: int) -> None:
    """Attach a void child block to an open parent frame."""
    _splice_inner_html(parent, document, start)
    parent.block.inner_blocks.append(block)
    parent.block.inner_content.append(None)
    parent.prev_offset = end


def _splice_inner_html(parent: _Frame, document: str, up_to: int) -> None:
    """Record the HTML chunk between the parent's last token and ``up_to``."""
    html = document[parent.prev_offset:up_to]
    if html:
        parent.block.inner_html += html
        parent.block.inner_content.append(html)


def _close_frame(frame: _Frame, document: str, closer_start: int) -> None:
    """Finalize a block's trailing inner HTML (between last child and its closer)."""
    html = document[frame.prev_offset:closer_start]
    if html:
        frame.block.inner_html += html
        frame.block.inner_content.append(html)


def _emit_leading(document: str, start: int | None, end: int, output: list[Block]) -> None:
    if start is not None:
        _emit_freeform(document[start:end], output)


def _emit_freeform(text: str, output: list[Block]) -> None:
    if text == "":
        return
    output.append(
        Block(
            block_name=None,
            inner_html=text,
            inner_content=[text],
            original_raw=text,
        )
    )

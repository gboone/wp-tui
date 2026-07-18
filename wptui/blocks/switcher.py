"""The block-type registry behind the slash-command switcher.

Headless by construction — this module must not import ``textual`` (per the
headless-library rule). It maps a user-typed query to the block types an empty block can
be switched to, and each entry knows how to mint a fresh block of that type. The picker
modal (``wptui/widgets/block_switcher.py``) is a thin view over this table.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from wptui.blocks.factory import (
    new_code_block,
    new_heading_block,
    new_list_block,
    new_paragraph_block,
    new_preformatted_block,
    new_quote_block,
    new_separator_block,
)
from wptui.blocks.model import Block


@dataclass(frozen=True)
class BlockType:
    """One switchable target: a display label, search aliases, and a factory."""

    label: str
    aliases: frozenset[str]
    factory: Callable[[], Block]


# One switchable entry per heading level. H2 leads (the common content default that a bare
# "heading" query should pick) and H1 trails (rarely wanted in post body — the title is H1).
# The default arg pins ``n`` per lambda.
_HEADINGS: tuple[BlockType, ...] = tuple(
    BlockType(
        f"Heading {n}",
        frozenset({f"heading {n}", f"h{n}", "heading", "header", "title"}),
        lambda n=n: new_heading_block(n),
    )
    for n in (2, 3, 4, 5, 6, 1)
)

# Registry order is the display order in the picker.
REGISTRY: tuple[BlockType, ...] = (
    BlockType("Paragraph", frozenset({"paragraph", "text", "p"}), new_paragraph_block),
    *_HEADINGS,
    BlockType(
        "Bulleted list",
        frozenset({"bulleted list", "bullet list", "unordered list", "bullets", "ul"}),
        lambda: new_list_block(ordered=False),
    ),
    BlockType(
        "Numbered list",
        frozenset({"numbered list", "ordered list", "numbers", "ol"}),
        lambda: new_list_block(ordered=True),
    ),
    BlockType("Quote", frozenset({"quote", "blockquote"}), new_quote_block),
    BlockType("Code", frozenset({"code", "code block"}), new_code_block),
    BlockType("Preformatted", frozenset({"preformatted", "pre"}), new_preformatted_block),
    BlockType(
        "Separator",
        frozenset({"separator", "divider", "horizontal rule", "hr", "rule"}),
        new_separator_block,
    ),
)


def match(query: str) -> list[BlockType]:
    """Block types whose label or any alias contains ``query`` (case-insensitive).

    An empty/whitespace query returns the whole registry in display order.
    """
    q = query.strip().lower()
    if not q:
        return list(REGISTRY)
    # Labels match on substring (so "list" finds both lists); aliases match on prefix so
    # short abbreviations like "ul" stay precise instead of hitting inside "rule".
    return [
        bt
        for bt in REGISTRY
        if q in bt.label.lower() or any(alias.startswith(q) for alias in bt.aliases)
    ]

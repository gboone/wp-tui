"""The editable block tree.

A ``Block`` mirrors the canonical WordPress block shape (name, attributes,
innerBlocks, innerHTML, innerContent) and adds two round-trip fields:

* ``original_raw`` — the exact source substring this block occupied at parse time.
* ``dirty`` — set only when a block is edited. Serialization re-emits ``original_raw``
  verbatim while a block is clean, which is what makes opaque passthrough and
  untouched content lossless by construction.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Block names that get rich in-TUI editing. Everything else is opaque passthrough.
EDITABLE_BLOCKS: frozenset[str] = frozenset(
    {
        "core/paragraph",
        "core/heading",
        "core/list",
        "core/list-item",
        "core/quote",
        "core/code",
        "core/preformatted",
        "core/separator",
        "core/image",
    }
)


@dataclass
class Block:
    """One node in the block tree (or a freeform HTML chunk when ``block_name`` is None)."""

    block_name: str | None
    """Full block name, e.g. ``"core/paragraph"``. ``None`` = freeform/classic HTML."""
    attributes: dict = field(default_factory=dict)
    """Parsed JSON block attributes (``{}`` if none)."""
    inner_blocks: list["Block"] = field(default_factory=list)
    """Nested child blocks, in order."""
    inner_html: str = ""
    """Concatenated HTML chunks of the inner content (child-block markers removed)."""
    inner_content: list[str | None] = field(default_factory=list)
    """Interleaved inner content: HTML strings and ``None`` placeholders marking where
    each child block from :attr:`inner_blocks` is spliced back in."""
    attributes_raw: str | None = None
    """Exact JSON attribute substring as parsed (without the leading space), or ``None``
    when the block had no attributes. Re-emitted verbatim on a dirty rebuild so an
    untouched block's attributes never drift from WordPress's exact byte encoding
    (slash/unicode/``--`` escaping). Set to ``None`` if you actually change
    :attr:`attributes`, so they get re-encoded."""
    original_raw: str = ""
    """Exact source substring for this block (for freeform blocks, the text itself)."""
    void: bool = False
    """True for a self-closing block (``<!-- wp:name /-->``). Tracked explicitly so a
    dirtied *empty* opener/closer pair rebuilds as a pair, not as a void block."""
    dirty: bool = False
    """True once edited; gates whether serialization rebuilds or re-emits verbatim."""

    # -- classification -----------------------------------------------------

    @property
    def is_freeform(self) -> bool:
        """A classic/freeform HTML chunk that lives outside any block delimiter."""
        return self.block_name is None

    @property
    def is_editable(self) -> bool:
        """Whether this block type gets rich editing (vs. opaque passthrough)."""
        return self.block_name in EDITABLE_BLOCKS

    @property
    def is_opaque(self) -> bool:
        """A recognized block that v1 preserves verbatim rather than deeply editing."""
        return not self.is_freeform and not self.is_editable

    def mark_dirty(self) -> None:
        self.dirty = True

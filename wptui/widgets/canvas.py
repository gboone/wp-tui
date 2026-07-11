"""BlockCanvas: the scrollable stack of block widgets for one post.

Editable text blocks (paragraph, heading, code, preformatted, and — via container
descent — list items and quote paragraphs) render as inline editors; separators and
opaque passthrough blocks render as focusable cards. Structural operations (move, delete,
insert) act on the *top-level* block that owns the focused widget; nested reordering is
deferred. Editing a nested child dirties its ancestors at ``sync()`` time via
:func:`propagate_dirty` so the parent re-serializes rather than re-emitting stale source.
"""

from __future__ import annotations

from textual.containers import VerticalScroll
from textual.css.query import NoMatches
from textual.widget import Widget
from textual.widgets import Static

from wptui.blocks.factory import new_paragraph_block, separator_freeform
from wptui.blocks.model import Block
from wptui.blocks.serialize import propagate_dirty
from wptui.blocks.text import get_editable_body
from wptui.widgets.image_card import ImageCard
from wptui.widgets.opaque_card import OpaqueCard
from wptui.widgets.separator_card import SeparatorCard
from wptui.widgets.text_block import TextBlockEditor

# Text blocks that get an inline editor when they have a single wrapper and no children.
_LEAF_EDITABLE = frozenset(
    {"core/paragraph", "core/heading", "core/code", "core/preformatted", "core/list-item"}
)
# Container blocks we descend into to edit their children in place.
_CONTAINERS = frozenset({"core/list", "core/quote"})


class BlockCanvas(VerticalScroll):
    """Renders a post's blocks; owns the block list used for serialization."""

    def __init__(self, blocks: list[Block]) -> None:
        super().__init__()
        self.blocks = blocks
        # Widgets with a commit() method (text editors and image cards).
        self._editors: list[TextBlockEditor | ImageCard] = []
        # Maps each rendered widget to the top-level block that owns it.
        self._owner: dict[Widget, Block] = {}

    # -- rendering --------------------------------------------------------

    def compose(self):
        self._editors = []
        self._owner = {}
        for block in self.blocks:
            yield from self._render_block(block, owner=block, depth=0)

    def _render_block(self, block: Block, *, owner: Block, depth: int):
        kind = _classify(block)
        if kind == "editor":
            widget = TextBlockEditor(block)
            self._editors.append(widget)
            yield self._track(widget, owner, depth)
        elif kind == "image":
            card = ImageCard(block)
            self._editors.append(card)
            yield self._track(card, owner, depth)
        elif kind == "separator":
            yield self._track(SeparatorCard(block), owner, depth)
        elif kind == "container":
            name = (block.block_name or "").removeprefix("core/")
            yield self._track(Static(f"▾ {name}", classes="container-label"), owner, depth)
            for child in block.inner_blocks:
                yield from self._render_block(child, owner=owner, depth=depth + 1)
        elif kind == "opaque":
            yield self._track(OpaqueCard(block), owner, depth)
        # whitespace-only freeform: kept in the model, not shown.

    def _track(self, widget: Widget, owner: Block, depth: int) -> Widget:
        self._owner[widget] = owner
        if depth:
            widget.add_class("nested")
        return widget

    # -- committing / saving ----------------------------------------------

    def sync(self) -> None:
        """Flush editor widgets into their blocks, then dirty their ancestors."""
        for editor in self._editors:
            try:
                editor.commit()
            except NoMatches:
                # A recompose can leave an editor in _editors whose child inputs aren't
                # mounted yet; skip it rather than crash the save. It has no edits to flush.
                continue
        propagate_dirty(self.blocks)

    # -- structural operations (top-level blocks) -------------------------

    async def move_focused(self, delta: int) -> bool:
        """Move the focused top-level block up (-1) or down (+1). Returns success."""
        block = self._focused_owner()
        if block is None:
            return False
        index = self.blocks.index(block)
        target = self._neighbor_content_index(index, delta)
        if target is None:
            return False
        self.sync()
        self.blocks[index], self.blocks[target] = self.blocks[target], self.blocks[index]
        await self._rerender(focus=block)
        return True

    async def delete_focused(self) -> bool:
        """Delete the focused top-level block (and one adjacent blank separator)."""
        block = self._focused_owner()
        if block is None:
            return False
        self.sync()
        index = self.blocks.index(block)
        # Focus a surviving neighbour after removal.
        neighbor_i = self._neighbor_content_index(index, +1) or self._neighbor_content_index(
            index, -1
        )
        neighbor = self.blocks[neighbor_i] if neighbor_i is not None else None
        self.blocks.pop(index)
        self._drop_adjacent_blank(index)
        await self._rerender(focus=neighbor)
        return True

    async def insert_paragraph(self) -> bool:
        """Insert a new empty paragraph after the focused top-level block."""
        block = self._focused_owner()
        self.sync()
        paragraph = new_paragraph_block()
        if block is None:
            self.blocks.append(separator_freeform())
            self.blocks.append(paragraph)
        else:
            index = self.blocks.index(block)
            self.blocks[index + 1 : index + 1] = [separator_freeform(), paragraph]
        await self._rerender(focus=paragraph)
        return True

    # -- helpers ----------------------------------------------------------

    def _focused_owner(self) -> Block | None:
        focused = self.screen.focused
        node: Widget | None = focused
        while node is not None:
            if node in self._owner:
                return self._owner[node]
            node = node.parent if isinstance(node.parent, Widget) else None
        return None

    def _neighbor_content_index(self, index: int, delta: int) -> int | None:
        """Index of the nearest rendered (non-blank) block in the given direction."""
        i = index + delta
        while 0 <= i < len(self.blocks):
            if _is_content(self.blocks[i]):
                return i
            i += delta
        return None

    def _drop_adjacent_blank(self, index: int) -> None:
        """After removing a block at ``index``, drop one blank separator beside the gap."""
        if index < len(self.blocks) and _is_blank_freeform(self.blocks[index]):
            self.blocks.pop(index)
        elif index - 1 >= 0 and _is_blank_freeform(self.blocks[index - 1]):
            self.blocks.pop(index - 1)

    async def _rerender(self, *, focus: Block | None) -> None:
        await self.recompose()
        self._restore_focus(focus)

    def _restore_focus(self, target: Block | None) -> None:
        if target is None:
            return
        for widget, owner in self._owner.items():
            if isinstance(widget, TextBlockEditor) and widget.block is target:
                widget.query_one("#body").focus()
                return
            if isinstance(widget, ImageCard) and widget.block is target:
                widget.query_one("#img-src").focus()
                return
            if owner is target:
                widget.focus()
                return


def _classify(block: Block) -> str:
    if block.block_name == "core/separator":
        return "separator"
    if block.block_name == "core/image":
        return "image"
    if block.block_name in _CONTAINERS and block.inner_blocks:
        return "container"
    if (
        block.block_name in _LEAF_EDITABLE
        and not block.inner_blocks
        and get_editable_body(block) is not None
    ):
        return "editor"
    if _is_content(block):
        return "opaque"
    return "blank"


def _is_content(block: Block) -> bool:
    """Whether a top-level block is rendered (blank inter-block freeform is not)."""
    return not _is_blank_freeform(block)


def _is_blank_freeform(block: Block) -> bool:
    return block.is_freeform and block.original_raw.strip() == ""

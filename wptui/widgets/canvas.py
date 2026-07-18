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

from wptui.blocks.containers import child_factory_for, set_container_children
from wptui.blocks.factory import new_paragraph_block, separator_freeform, set_heading_level
from wptui.blocks.model import Block
from wptui.blocks.serialize import propagate_dirty
from wptui.blocks.text import get_editable_body, set_editable_body
from wptui.inline import html_to_markdown, markdown_to_html
from wptui.widgets.image_card import ImageCard
from wptui.widgets.inline_area import InlineMarkdownArea
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
            # Semantic signal, not only styling: InlineMarkdownArea._slash_triggers reads
            # "nested" (any depth) to keep the "/" switcher from firing inside a child.
            widget.add_class("nested")
        if depth == 1:
            # A direct child of a top-level container (a list-item, a quote paragraph) —
            # the only depth Enter/Backspace structural editing operates on. Deeper nesting
            # (a list inside a quote) is left to default key handling.
            widget.add_class("container-child")
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

    def _index_of(self, block: Block) -> int | None:
        """Identity-based index of ``block`` in ``self.blocks``.

        ``list.index``/``in`` compare by value, and ``Block`` is a plain dataclass — so
        two structurally-identical blocks (e.g. two empty paragraphs) are equal and
        ``.index`` would return the *first* twin, not the one the user focused. Every
        structural op must locate its target by identity.
        """
        return _identity_index(self.blocks, block)

    async def move_focused(self, delta: int) -> bool:
        """Move the focused top-level block up (-1) or down (+1). Returns success."""
        block = self._focused_owner()
        if block is None:
            return False
        index = self._index_of(block)
        if index is None:
            return False
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
        index = self._index_of(block)
        if index is None:
            return False
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
        return await self.insert_block(new_paragraph_block())

    def focused_block(self) -> Block | None:
        """The top-level block owning the currently focused widget, or ``None``."""
        return self._focused_owner()

    async def replace_focused(self, new_block: Block) -> bool:
        """Replace the focused top-level block with ``new_block`` at the same position."""
        block = self._focused_owner()
        if block is None:
            return False
        return await self.replace_block(block, new_block)

    async def replace_block(self, old: Block, new_block: Block) -> bool:
        """Replace a specific top-level block with ``new_block`` at the same position.

        Used by the slash-command switcher, which captures the target block *before*
        opening the picker modal (focus moves to the modal), then converts that exact
        block on selection. No separator is added — this is a positional swap.
        """
        self.sync()
        index = self._index_of(old)
        if index is None:
            return False
        self.blocks[index] = new_block
        await self._rerender(focus=new_block)
        return True

    async def set_heading_level_on(self, block: Block, level: int) -> bool:
        """Change ``block``'s heading level in place, preserving its text. Captured before
        the picker opens (focus moves to the modal), like the switcher's convert path."""
        if block.block_name != "core/heading" or self._index_of(block) is None:
            return False
        self.sync()
        set_heading_level(block, level)
        await self._rerender(focus=block)
        return True

    async def insert_block(self, new_block: Block) -> bool:
        """Insert an arbitrary new top-level block after the focused one (or at the end)."""
        block = self._focused_owner()
        self.sync()
        index = None if block is None else self._index_of(block)
        if index is None:
            self.blocks.append(separator_freeform())
            self.blocks.append(new_block)
        else:
            self.blocks[index + 1 : index + 1] = [separator_freeform(), new_block]
        await self._rerender(focus=new_block)
        return True

    # -- nested child (list-item / quote paragraph) structural ops --------

    async def nested_enter(self) -> bool:
        """Handle Enter in a container child: read the *live* editor's text and caret, then
        split (or exit when the child is empty). Reading at handle time — not from the key
        event — keeps queued Enters correct: a second Enter sees the freshly-focused new
        child, so Enter-Enter is "new item, then exit", never a stale re-split."""
        area = self._focused_inline_area()
        if area is None:
            return False
        offset = _location_to_offset(area.text, area.cursor_location)
        before, after = area.text[:offset], area.text[offset:]
        if not before and not after:
            return await self.exit_container()
        return await self.split_child(before, after)

    async def nested_backspace(self) -> bool:
        """Handle Backspace at the start of a container child: remove it when empty, else
        merge it into the previous child. Reads the live editor to stay queue-safe."""
        area = self._focused_inline_area()
        if area is None:
            return False
        if area.text == "":
            return await self.remove_child()
        return await self.merge_child_into_previous()

    async def split_child(self, before_md: str, after_md: str) -> bool:
        """Split the focused container child at the caret: ``before_md`` stays, ``after_md``
        moves to a new sibling inserted below; caret at the start of the new child."""
        located = self._locate_focused_child()
        if located is None:
            return False
        container, child, children, idx = located
        set_editable_body(child, markdown_to_html(before_md))
        new_child = child_factory_for(container)()
        set_editable_body(new_child, markdown_to_html(after_md))
        children.insert(idx + 1, new_child)
        set_container_children(container, children)
        await self._rerender(focus=new_child, caret="start")
        return True

    async def exit_container(self) -> bool:
        """Exit the container from the focused (empty) child: drop it, insert a paragraph
        after the container (or replace the container when it becomes empty)."""
        found = self._focused_child()
        if found is None:
            return False
        container, child = found
        self.sync()
        cidx = self._index_of(container)
        if cidx is None:
            return False
        remaining = [c for c in container.inner_blocks if c is not child]
        paragraph = new_paragraph_block()
        if remaining:
            set_container_children(container, remaining)
            self.blocks[cidx + 1 : cidx + 1] = [separator_freeform(), paragraph]
        else:
            self.blocks[cidx] = paragraph  # the list/quote is empty now — replace it
        await self._rerender(focus=paragraph, caret="start")
        return True

    async def merge_child_into_previous(self) -> bool:
        """Merge the focused child's text into the previous sibling; caret at the join.
        No-op at the first child, or when the previous sibling is not an editable
        single-wrapper block (e.g. a nested list) — merging into it would destroy it."""
        located = self._locate_focused_child()
        if located is None:
            return False
        container, child, children, idx = located
        if idx == 0:
            return False
        previous = children[idx - 1]
        prev_body = get_editable_body(previous)
        if previous.inner_blocks or prev_body is None:
            # A container (e.g. a nested list) or a non-single-wrapper block — merging text
            # into it would wipe its children or drop this child's text. Leave it be.
            return False
        prev_md = html_to_markdown(prev_body)
        child_md = html_to_markdown(get_editable_body(child) or "")
        if not set_editable_body(previous, markdown_to_html(prev_md + child_md)):
            return False
        children.pop(idx)
        set_container_children(container, children)
        await self._rerender(focus=previous, caret=len(prev_md))
        return True

    async def remove_child(self) -> bool:
        """Remove the focused (empty) child; focus the previous sibling's end. When it was
        the only child, remove the container and focus a neighbour — or, if the container
        was the whole document, replace it with an empty paragraph so the caret has a home."""
        located = self._locate_focused_child()
        if located is None:
            return False
        container, child, children, idx = located
        remaining = [c for c in children if c is not child]
        if remaining:
            set_container_children(container, remaining)
            focus_target = children[idx - 1] if idx > 0 else remaining[0]
            await self._rerender(focus=focus_target, caret="end")
            return True
        cidx = self._index_of(container)
        if cidx is None:
            return False
        neighbor_i = self._neighbor_content_index(cidx, +1) or self._neighbor_content_index(cidx, -1)
        if neighbor_i is not None:
            neighbor = self.blocks[neighbor_i]
            self.blocks.pop(cidx)
            self._drop_adjacent_blank(cidx)
            await self._rerender(focus=neighbor, caret="end")
        else:  # the container was the only block — never leave an empty, unfocusable doc
            paragraph = new_paragraph_block()
            self.blocks[cidx] = paragraph
            await self._rerender(focus=paragraph, caret="start")
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

    def _focused_editor(self) -> TextBlockEditor | None:
        node: Widget | None = self.screen.focused
        while node is not None:
            if isinstance(node, TextBlockEditor):
                return node
            node = node.parent if isinstance(node.parent, Widget) else None
        return None

    def _focused_inline_area(self) -> InlineMarkdownArea | None:
        focused = self.screen.focused
        return focused if isinstance(focused, InlineMarkdownArea) else None

    def _focused_child(self) -> tuple[Block, Block] | None:
        """``(container, child)`` when a nested container child is focused, else ``None``.

        The focused editor's ``.block`` is the child; its ``_owner`` entry is the top-level
        container. A top-level editor owns itself (``owner is child``) — not nested."""
        editor = self._focused_editor()
        if editor is None:
            return None
        child = editor.block
        container = self._owner.get(editor)
        if container is None or container is child:
            return None
        return container, child

    def _locate_focused_child(self) -> tuple[Block, Block, list[Block], int] | None:
        """``(container, child, children, idx)`` for the focused child, after ``sync()``.

        Shared preamble for the split/merge/remove ops. Locates the child by identity so a
        structural twin (two empty items) never mis-targets."""
        found = self._focused_child()
        if found is None:
            return None
        container, child = found
        self.sync()
        children = list(container.inner_blocks)
        idx = _identity_index(children, child)
        if idx is None:
            return None
        return container, child, children, idx

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

    async def _rerender(self, *, focus: Block | None, caret: str | int | None = None) -> None:
        await self.recompose()
        self._restore_focus(focus, caret)

    def _restore_focus(self, target: Block | None, caret: str | int | None = None) -> None:
        if target is None:
            return
        focus_target = self._focus_widget_for(target)
        if focus_target is None:
            return
        focus_target.focus()
        # focus() schedules a scroll-into-view, but right after a recompose the new
        # widget isn't laid out yet, so that scroll evaluates a stale region and skips.
        # Re-scroll (and place the caret) once layout has settled.
        self.call_after_refresh(self._settle_focus, focus_target, caret)

    def _settle_focus(self, widget: Widget, caret: str | int | None) -> None:
        if not widget.is_mounted:
            return
        widget.scroll_visible(animate=False)
        if caret is not None and isinstance(widget, InlineMarkdownArea):
            if caret == "start":
                widget.move_cursor((0, 0))
            elif caret == "end":
                widget.move_cursor(widget.document.end)
            elif isinstance(caret, int):
                widget.move_cursor(_offset_to_location(widget.text, caret))

    def _focus_widget_for(self, target: Block) -> Widget | None:
        """The widget that should receive focus for a top-level block (inner field first)."""
        # For a container (list/quote), focus its first rendered child editor so the user
        # can type the first item/line immediately, not the container's label.
        if target.block_name in _CONTAINERS and target.inner_blocks:
            for widget, owner in self._owner.items():
                if owner is target and isinstance(widget, TextBlockEditor):
                    return widget.query_one("#body")
        for widget, owner in self._owner.items():
            if isinstance(widget, TextBlockEditor) and widget.block is target:
                return widget.query_one("#body")
            if isinstance(widget, ImageCard) and widget.block is target:
                return widget.query_one("#img-src")
            if owner is target:
                return widget
        return None

def _identity_index(blocks: list[Block], target: Block) -> int | None:
    """Index by identity (list.index would match a structural twin — two empty items)."""
    for i, block in enumerate(blocks):
        if block is target:
            return i
    return None


def _offset_to_location(text: str, offset: int) -> tuple[int, int]:
    """Convert a character offset in ``text`` to a TextArea ``(row, column)`` location."""
    before = text[:offset]
    row = before.count("\n")
    column = len(before) - (before.rfind("\n") + 1)
    return row, column


def _location_to_offset(text: str, location: tuple[int, int]) -> int:
    """Convert a TextArea ``(row, column)`` location to a character offset in ``text``."""
    row, column = location
    lines = text.split("\n")
    return sum(len(line) + 1 for line in lines[:row]) + column


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

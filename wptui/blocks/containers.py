"""Headless mutation of container blocks (``core/list``, ``core/quote``).

Editing a list or quote means adding, removing, or splitting its children. When
``inner_blocks`` change, ``inner_content`` — the interleaving of wrapper HTML chunks with
``None`` placeholders that :func:`wptui.blocks.serialize._rebuild_inner` splices children
into — must change with it. Rather than patch that list surgically, we regenerate it from
the (already ``dirty``) container's structure: the byte-for-byte round-trip only holds for
*clean* blocks, so a container being edited rebuilds from structure anyway.

Headless by construction — this module must not import ``textual``.
"""

from __future__ import annotations

from collections.abc import Callable

from wptui.blocks.factory import new_list_block, new_list_item, new_paragraph_block
from wptui.blocks.model import Block
from wptui.blocks.text import split_wrapper

# Maximum list nesting depth (a top-level list is depth 1); Tab past this is a no-op.
MAX_LIST_NEST_DEPTH = 4


def child_factory_for(container: Block) -> Callable[[], Block]:
    """The factory that mints a fresh child for ``container``'s type.

    ``core/list`` -> an empty ``core/list-item``; ``core/quote`` -> an empty
    ``core/paragraph``.
    """
    if container.block_name == "core/list":
        return new_list_item
    return new_paragraph_block


def _wrappers(container: Block) -> tuple[str, str]:
    """The container's leading/trailing HTML chunks (e.g. ``\\n<ul …>`` and ``</ul>\\n``).

    For every container we build or parse, ``inner_content`` opens and closes with a string
    chunk around the child placeholders, so the first and last entries are those wrappers.
    """
    content = container.inner_content
    open_chunk = content[0] if content and isinstance(content[0], str) else ""
    close_chunk = content[-1] if content and isinstance(content[-1], str) else ""
    return open_chunk, close_chunk


def set_container_children(container: Block, children: list[Block]) -> None:
    """Replace ``container``'s children and regenerate its ``inner_content``.

    ``inner_content`` becomes ``[open, *(None per child), close]`` — children serialize
    back-to-back inside the preserved wrapper. Marks the container ``dirty`` so it rebuilds
    from structure.
    """
    open_chunk, close_chunk = _wrappers(container)
    container.inner_blocks = list(children)
    container.inner_content = [open_chunk, *([None] * len(children)), close_chunk]
    container.inner_html = f"{open_chunk}{close_chunk}"
    container.dirty = True


# -- list nesting (Tab / Shift+Tab) -----------------------------------------


def identity_index(items: list[Block], target: Block) -> int | None:
    """Index of ``target`` by identity — ``list.index``/``in`` compare by value, and ``Block``
    is a plain dataclass, so a structural twin (two empty items) would mis-target."""
    for i, block in enumerate(items):
        if block is target:
            return i
    return None


_identity_index = identity_index  # internal alias used by this module's transforms


def _sublist_of(item: Block) -> Block | None:
    """The nested ``core/list`` held by a list-item, or ``None``."""
    for child in item.inner_blocks:
        if child.block_name == "core/list":
            return child
    return None


def list_depth(chain: list[Block]) -> int:
    """Nesting depth = number of ``core/list`` ancestors in the item's ancestry chain."""
    return sum(1 for block in chain if block.block_name == "core/list")


def subtree_list_height(item: Block) -> int:
    """How many further list levels ``item`` carries below itself (0 for a leaf item)."""
    sublist = _sublist_of(item)
    if sublist is None:
        return 0
    return 1 + max((subtree_list_height(child) for child in sublist.inner_blocks), default=0)


def _attach_sublist_to_leaf(item: Block, sublist: Block) -> bool:
    """Turn a leaf list-item into a parent holding ``sublist`` after its text. Returns
    ``False`` (touching nothing) if the item's HTML isn't a recognizable ``<li>`` wrapper —
    never silently drop its text."""
    wrapped = split_wrapper(item.inner_html)
    if wrapped is None:
        return False
    item.inner_blocks = [sublist]
    item.inner_content = [f"{wrapped.prefix}{wrapped.body}", None, wrapped.suffix]
    item.inner_html = f"{wrapped.prefix}{wrapped.body}{wrapped.suffix}"
    item.dirty = True
    return True


def _detach_sublist_from_leaf(item: Block) -> None:
    """Turn a parent list-item back into a leaf (its sublist has been emptied/removed)."""
    inner = "".join(chunk for chunk in item.inner_content if chunk is not None)
    item.inner_blocks = []
    item.inner_content = [inner]
    item.inner_html = inner
    item.dirty = True


def indent_item(enclosing_list: Block, item: Block) -> bool:
    """Indent ``item`` into a sublist under its previous sibling. No-op on the first item.

    The moved item keeps its own sublist (moves as a unit). The sublist inherits the
    enclosing list's ordered/unordered kind."""
    items = enclosing_list.inner_blocks
    idx = _identity_index(items, item)
    if idx is None or idx == 0:
        return False
    previous = items[idx - 1]
    sublist = _sublist_of(previous)
    if sublist is None:
        new_sub = new_list_block(ordered=bool(enclosing_list.attributes.get("ordered")))
        set_container_children(new_sub, [item])
        if not _attach_sublist_to_leaf(previous, new_sub):
            return False  # previous isn't a clean <li> — leave the tree untouched
    else:
        set_container_children(sublist, [*sublist.inner_blocks, item])
    set_container_children(enclosing_list, [b for b in items if b is not item])
    return True


def outdent_item(chain: list[Block], item: Block) -> bool:
    """Outdent ``item`` to the enclosing list, after the item that held its sublist. No-op
    at the top level. ``chain`` is the ancestry ``[…, enclosing_list, parent_item, sublist]``.

    Sublist items *before* ``item`` stay nested; items *after* ``item`` are reparented under
    it (they follow it out visually, like WordPress), becoming its sublist."""
    if len(chain) < 3:
        return False
    sublist, parent_item, enclosing_list = chain[-1], chain[-2], chain[-3]
    if parent_item.block_name != "core/list-item" or enclosing_list.block_name != "core/list":
        # A non-list container (e.g. a quote nested inside a list-item) interrupts the
        # list-in-list chain; the positional unpacking would mis-bind — bail rather than corrupt.
        return False
    subitems = sublist.inner_blocks
    idx = _identity_index(subitems, item)
    if idx is None:
        return False
    before, following = subitems[:idx], subitems[idx + 1 :]
    if following:  # following siblings become the outdented item's own children
        existing = _sublist_of(item)
        if existing is not None:
            set_container_children(existing, [*following, *existing.inner_blocks])
        else:
            new_sub = new_list_block(ordered=bool(sublist.attributes.get("ordered")))
            set_container_children(new_sub, following)
            _attach_sublist_to_leaf(item, new_sub)
    if before:
        set_container_children(sublist, before)
    else:
        _detach_sublist_from_leaf(parent_item)  # the sublist is now empty
    items = list(enclosing_list.inner_blocks)
    pidx = _identity_index(items, parent_item)
    if pidx is None:
        return False
    items.insert(pidx + 1, item)
    set_container_children(enclosing_list, items)
    return True

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

from wptui.blocks.factory import new_list_item, new_paragraph_block
from wptui.blocks.model import Block


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

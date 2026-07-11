"""Serialize a block tree back to block-grammar text.

The round-trip invariant — ``serialize(parse(x)) == x`` byte-for-byte — is guaranteed
by the dirty-tracking gate: a block that has not been edited re-emits its captured
``original_raw`` unchanged. Only edited (``dirty``) blocks are rebuilt from structure.
"""

from __future__ import annotations

import json

from wptui.blocks.model import Block


def serialize(blocks: list[Block]) -> str:
    """Serialize a list of top-level blocks to a single document string."""
    return "".join(serialize_block(b) for b in blocks)


def propagate_dirty(blocks: list[Block]) -> bool:
    """Mark every ancestor of a dirty block dirty; return whether any block is dirty.

    A container re-emits its captured ``original_raw`` while clean, so editing a nested
    child (e.g. a ``core/list-item``) must dirty its ancestors or the parent would
    re-serialize its stale source and drop the edit.
    """
    any_dirty = False
    for block in blocks:
        if propagate_dirty(block.inner_blocks):
            block.dirty = True
        any_dirty = any_dirty or block.dirty
    return any_dirty


def serialize_block(block: Block) -> str:
    """Serialize one block (recursively).

    Clean blocks re-emit ``original_raw`` verbatim; dirty blocks are rebuilt.
    """
    if not block.dirty:
        return block.original_raw
    return _rebuild(block)


def _rebuild(block: Block) -> str:
    if block.is_freeform:
        return block.inner_html

    short = _short_name(block.block_name or "")
    attrs = _encode_attrs_for(block)

    if _is_void(block):
        return f"<!-- wp:{short}{attrs} /-->"

    opener = f"<!-- wp:{short}{attrs} -->"
    closer = f"<!-- /wp:{short} -->"
    body = _rebuild_inner(block)
    return f"{opener}{body}{closer}"


def _rebuild_inner(block: Block) -> str:
    """Reconstruct inner content, splicing child blocks at their ``None`` markers."""
    if not block.inner_content:
        # No recorded interleaving: fall back to raw HTML + any children appended.
        return block.inner_html + "".join(serialize_block(c) for c in block.inner_blocks)
    parts: list[str] = []
    children = iter(block.inner_blocks)
    for chunk in block.inner_content:
        if chunk is None:
            parts.append(serialize_block(next(children)))
        else:
            parts.append(chunk)
    return "".join(parts)


def _is_void(block: Block) -> bool:
    return (
        not block.inner_blocks
        and not block.inner_content
        and block.inner_html == ""
    )


def _short_name(full_name: str) -> str:
    """Core blocks serialize without their namespace; others keep it."""
    if full_name.startswith("core/"):
        return full_name[len("core/"):]
    return full_name


def _encode_attrs_for(block: Block) -> str:
    """Prefer the exact parsed attribute bytes; only re-encode when they were changed.

    Re-encoding can't perfectly reproduce WordPress's slash/unicode/``--`` escaping, so
    an untouched block (including a container dirtied only because a child was edited)
    re-emits its original attribute substring verbatim — no drift, no delimiter risk.
    """
    if not block.attributes:
        return ""
    if block.attributes_raw is not None:
        return f" {block.attributes_raw}"
    return _encode_attrs(block.attributes)


def _encode_attrs(attrs: dict) -> str:
    if not attrs:
        return ""
    # Compact JSON with a leading space. ``ensure_ascii`` escapes non-ASCII to \uXXXX,
    # and we escape ``--`` so an attribute value can never terminate the HTML comment
    # delimiter. This is best-effort WP matching for synthesized/edited attrs; parsed
    # blocks re-emit their exact bytes via _encode_attrs_for instead.
    encoded = json.dumps(attrs, separators=(",", ":"), ensure_ascii=True)
    encoded = encoded.replace("--", "\\u002d\\u002d")
    return f" {encoded}"

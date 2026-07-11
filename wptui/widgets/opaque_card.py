"""Collapsed placeholder for blocks that v1 preserves verbatim (opaque passthrough)."""

from __future__ import annotations

import re

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from wptui.blocks.model import Block

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


class OpaqueCard(Vertical):
    """Shows a block's type and a short text preview; the block is not deeply editable."""

    can_focus = True

    def __init__(self, block: Block) -> None:
        super().__init__()
        self.block = block

    def compose(self) -> ComposeResult:
        if self.block.is_freeform:
            label = "freeform HTML"
        else:
            label = self.block.block_name or "unknown"
        yield Static(f"▚ {label}", classes="opaque-label")
        preview = _preview(self.block.original_raw)
        if preview:
            yield Static(preview, classes="opaque-preview")


def _preview(raw: str, limit: int = 120) -> str:
    text = _TAG_RE.sub(" ", raw)
    text = _WS_RE.sub(" ", text).strip()
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text

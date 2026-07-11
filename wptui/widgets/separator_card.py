"""A focusable card for ``core/separator`` — a horizontal rule with no editable text."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from wptui.blocks.model import Block


class SeparatorCard(Vertical):
    """Represents a separator block; preserved verbatim, movable and deletable."""

    can_focus = True

    def __init__(self, block: Block) -> None:
        super().__init__()
        self.block = block

    def compose(self) -> ComposeResult:
        yield Static("─" * 24, classes="separator-rule")

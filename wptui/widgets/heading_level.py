"""HeadingLevelModal: pick a level (H1-H6) for the focused heading.

A thin picker modeled on :class:`wptui.widgets.block_switcher.BlockSwitcherModal`.
Dismisses with the chosen level (1-6), or ``None`` on cancel.
"""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static


class HeadingLevelModal(ModalScreen[int]):
    """Choose a heading level for the focused ``core/heading`` block."""

    # Layout CSS lives here so it applies in test harnesses that don't load app.tcss.
    DEFAULT_CSS = """
    HeadingLevelModal {
        align: center middle;
    }
    #heading-level {
        width: 40;
        max-width: 90%;
        height: auto;
        max-height: 80%;
        padding: 1 2;
        border: round $accent;
        background: $surface;
    }
    #heading-level-list {
        height: auto;
        max-height: 12;
    }
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(id="heading-level"):
            yield Static("Heading level", classes="switch-title")
            yield OptionList(*(f"Heading {n}" for n in range(1, 7)), id="heading-level-list")

    def on_mount(self) -> None:
        self.query_one("#heading-level-list", OptionList).focus()

    @on(OptionList.OptionSelected, "#heading-level-list")
    def _pick(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option_index + 1)  # option 0 -> level 1

    def action_cancel(self) -> None:
        self.dismiss(None)

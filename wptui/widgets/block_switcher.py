"""BlockSwitcherModal: pick a block type to convert the current empty block into.

A thin view over the headless ``wptui/blocks/switcher.py`` registry, modeled on
:class:`wptui.widgets.media_picker.MediaPickerModal`. Type to filter, Enter selects the
top match, or click an option; Escape cancels. Dismisses with the chosen
:class:`~wptui.blocks.switcher.BlockType`, or ``None`` on cancel.
"""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Static

from wptui.blocks.switcher import BlockType, match


class BlockSwitcherModal(ModalScreen[BlockType]):
    """Choose a block type to switch an empty block to."""

    # Layout-critical CSS lives here so it applies even in test harnesses that don't
    # load app.tcss (a container in a modal can otherwise collapse to height 1).
    DEFAULT_CSS = """
    BlockSwitcherModal {
        align: center middle;
    }
    #block-switcher {
        width: 60;
        max-width: 90%;
        height: auto;
        max-height: 80%;
        padding: 1 2;
        border: round $accent;
        background: $surface;
    }
    #switch-list {
        height: auto;
        max-height: 15;
    }
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self) -> None:
        super().__init__()
        self._matches: list[BlockType] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="block-switcher"):
            yield Static("Change block to…", classes="switch-title")
            yield Input(placeholder="type a block name…", id="switch-search")
            yield OptionList(id="switch-list")

    def on_mount(self) -> None:
        self._refilter("")
        self.query_one("#switch-search", Input).focus()

    def _refilter(self, query: str) -> None:
        self._matches = match(query)
        options = self.query_one("#switch-list", OptionList)
        options.clear_options()
        for block_type in self._matches:
            options.add_option(block_type.label)
        if self._matches:
            options.highlighted = 0

    @on(Input.Changed, "#switch-search")
    def _filter(self, event: Input.Changed) -> None:
        self._refilter(event.value)

    @on(Input.Submitted, "#switch-search")
    def _submit(self) -> None:
        # Enter in the search box picks the highlighted (top) match.
        options = self.query_one("#switch-list", OptionList)
        self._select(options.highlighted if options.highlighted is not None else 0)

    @on(OptionList.OptionSelected, "#switch-list")
    def _pick(self, event: OptionList.OptionSelected) -> None:
        self._select(event.option_index)

    def _select(self, index: int) -> None:
        if 0 <= index < len(self._matches):
            self.dismiss(self._matches[index])

    def action_cancel(self) -> None:
        self.dismiss(None)

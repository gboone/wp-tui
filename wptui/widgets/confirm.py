"""ConfirmModal: a minimal yes/no dialog that dismisses with a bool.

Used where a worker needs an explicit user decision before an irreversible-ish action
(e.g. creating a post whose earlier save may already have landed). Await it from a worker
with ``await self.app.push_screen_wait(ConfirmModal(...))``.
"""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ConfirmModal(ModalScreen[bool]):
    """Ask a yes/no question; dismiss ``True`` on confirm, ``False`` on cancel/escape."""

    DEFAULT_CSS = """
    ConfirmModal { align: center middle; }
    #confirm-modal { width: 64; height: auto; padding: 1 2; background: $surface; border: thick $primary; }
    #confirm-buttons { height: auto; align: right middle; margin-top: 1; }
    #confirm-buttons Button { margin-left: 1; }
    """

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(
        self, message: str, *, confirm_label: str = "OK", cancel_label: str = "Cancel"
    ) -> None:
        super().__init__()
        self._message = message
        self._confirm_label = confirm_label
        self._cancel_label = cancel_label

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-modal"):
            yield Static(self._message, id="confirm-message")
            with Horizontal(id="confirm-buttons"):
                yield Button(self._confirm_label, id="confirm-yes", variant="primary")
                yield Button(self._cancel_label, id="confirm-no")

    @on(Button.Pressed, "#confirm-yes")
    def _yes(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#confirm-no")
    def _no(self) -> None:
        self.dismiss(False)

    def action_cancel(self) -> None:
        self.dismiss(False)

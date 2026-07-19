"""ConflictModal: resolve a save conflict when another author changed the post.

Shown when a save is blocked because the post's ``modified_gmt`` moved on the server since
we loaded it. Offers three explicit choices, dismissing with a stable string result:

- ``"overwrite"`` — force-save our version, discarding the server's change.
- ``"reload"`` — discard our local edits and load the server's version.
- ``"cancel"`` — keep editing; decide later.

Modeled on :class:`wptui.widgets.heading_level.HeadingLevelModal`.
"""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


class ConflictModal(ModalScreen[str]):
    """Ask how to resolve a save conflict; dismiss with ``overwrite``/``reload``/``cancel``."""

    # Layout CSS lives here so it applies in test harnesses that don't load app.tcss.
    DEFAULT_CSS = """
    ConflictModal {
        align: center middle;
    }
    #conflict-box {
        width: 60;
        max-width: 90%;
        height: auto;
        max-height: 80%;
        padding: 1 2;
        border: round $error;
        background: $surface;
    }
    #conflict-message {
        height: auto;
        margin-bottom: 1;
    }
    #conflict-buttons {
        height: auto;
        align-horizontal: center;
    }
    #conflict-buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [("escape", "cancel", "Keep editing")]

    def __init__(self, server_modified_gmt: str | None = None) -> None:
        super().__init__()
        self._server_modified_gmt = server_modified_gmt

    def compose(self) -> ComposeResult:
        detail = (
            f" (server last modified {self._server_modified_gmt})"
            if self._server_modified_gmt
            else ""
        )
        with Vertical(id="conflict-box"):
            yield Static(
                f"Another author changed this post since you opened it{detail}.\n"
                "Overwrite with your version, reload theirs (losing your edits), "
                "or keep editing?",
                id="conflict-message",
            )
            with Horizontal(id="conflict-buttons"):
                yield Button("Overwrite", variant="error", id="conflict-overwrite")
                yield Button("Reload", variant="primary", id="conflict-reload")
                yield Button("Keep editing", id="conflict-cancel")

    @on(Button.Pressed, "#conflict-overwrite")
    def _overwrite(self) -> None:
        self.dismiss("overwrite")

    @on(Button.Pressed, "#conflict-reload")
    def _reload(self) -> None:
        self.dismiss("reload")

    @on(Button.Pressed, "#conflict-cancel")
    def _cancel_button(self) -> None:
        self.dismiss("cancel")

    def action_cancel(self) -> None:
        self.dismiss("cancel")

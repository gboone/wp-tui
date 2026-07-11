"""TermPicker: a modal to multi-select taxonomy terms and create new ones.

Parameterized by a taxonomy REST route (``categories`` / ``tags``) and the currently
selected term ids. Dismisses with the chosen id list. Off-page selections (ids not in the
current search results) are preserved so closing the picker never silently drops an
assignment the user couldn't see.
"""

from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, SelectionList, Static

from wptui.api import ApiError


class TermPicker(ModalScreen[list[int]]):
    """Select existing terms and optionally create new ones."""

    BINDINGS = [("escape", "done", "Done")]

    def __init__(self, taxonomy: str, selected: list[int]) -> None:
        super().__init__()
        self._taxonomy = taxonomy
        self._selected: set[int] = set(selected)
        self._shown: set[int] = set()

    def compose(self) -> ComposeResult:
        with Vertical(id="term-picker"):
            yield Static(f"Select {self._taxonomy}", classes="term-title")
            yield Input(placeholder="search…", id="term-search")
            yield SelectionList[int](id="term-list")
            with Horizontal(id="term-add-row"):
                yield Input(placeholder="new name", id="term-new")
                yield Button("Add", id="term-add")
            yield Static("", id="term-status")

    def on_mount(self) -> None:
        self._load()

    @work(exclusive=True, group="term-load")
    async def _load(self, search: str | None = None) -> None:
        client = self.app.client  # type: ignore[attr-defined]
        if client is None:
            return
        try:
            terms = await client.list_terms(self._taxonomy, search)
        except ApiError as err:
            self.query_one("#term-status", Static).update(f"Failed to load: {err}")
            return
        sl = self.query_one("#term-list", SelectionList)
        sl.clear_options()
        self._shown = set()
        for term in terms:
            sl.add_option((term.name, term.id, term.id in self._selected))
            self._shown.add(term.id)

    @on(Input.Submitted, "#term-search")
    def _search(self, event: Input.Submitted) -> None:
        self._load(event.value.strip() or None)

    @on(SelectionList.SelectedChanged, "#term-list")
    def _sync_selection(self, event: SelectionList.SelectedChanged) -> None:
        # Reconcile toggles among the shown options while keeping off-page selections.
        checked = set(self.query_one("#term-list", SelectionList).selected)
        self._selected = (self._selected - self._shown) | checked

    @on(Button.Pressed, "#term-add")
    def _add_pressed(self) -> None:
        self._create()

    @work(exclusive=True, group="term-create")
    async def _create(self) -> None:
        name = self.query_one("#term-new", Input).value.strip()
        if not name:
            return
        client = self.app.client  # type: ignore[attr-defined]
        try:
            term = await client.create_term(self._taxonomy, name)
        except ApiError as err:
            self.query_one("#term-status", Static).update(f"Failed to add: {err}")
            return
        sl = self.query_one("#term-list", SelectionList)
        sl.add_option((term.name, term.id, True))
        self._shown.add(term.id)
        self._selected.add(term.id)
        self.query_one("#term-new", Input).value = ""

    def action_done(self) -> None:
        self.dismiss(sorted(self._selected))

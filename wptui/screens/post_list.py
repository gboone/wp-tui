"""Post list screen: browse posts and open one to view its raw content."""

from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Input, Static
from textual.widgets.data_table import RowKey

from wptui.api import ApiError, PostSummary
from wptui.screens.editor import EditorScreen


class PostListScreen(Screen[None]):
    """A searchable table of posts."""

    BINDINGS = [
        ("/", "focus_search", "Search"),
        ("n", "new_post", "New post"),
        ("N", "new_page", "New page"),
        ("r", "reload", "Reload"),
        ("escape", "app.pop_screen", "Back"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._rows: dict[RowKey, PostSummary] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        yield Input(placeholder="Search posts… (press / )", id="post-search")
        yield DataTable(id="post-table", cursor_type="row", zebra_stripes=True)
        yield Static("", id="post-status")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#post-table", DataTable)
        table.add_columns("ID", "Title", "Status", "Modified (GMT)")
        table.focus()
        self._load()

    def action_focus_search(self) -> None:
        self.query_one("#post-search", Input).focus()

    def action_reload(self) -> None:
        self._load()

    @on(Input.Submitted, "#post-search")
    def _on_search(self, event: Input.Submitted) -> None:
        self._load(search=event.value.strip() or None)
        self.query_one("#post-table", DataTable).focus()

    @on(DataTable.RowSelected, "#post-table")
    def _on_row_selected(self, event: DataTable.RowSelected) -> None:
        summary = self._rows.get(event.row_key)
        if summary is not None:
            self.app.push_screen(EditorScreen(summary), self.on_editor_closed)

    def action_new_post(self) -> None:
        self.app.push_screen(EditorScreen(post_type="post"), self.on_editor_closed)

    def action_new_page(self) -> None:
        self.app.push_screen(EditorScreen(post_type="page"), self.on_editor_closed)

    def on_editor_closed(self, _result: object) -> None:
        """Refresh the list when returning from the editor (new/edited posts show up)."""
        self._load()

    @work(exclusive=True)
    async def _load(self, *, search: str | None = None) -> None:
        client = self.app.client  # type: ignore[attr-defined]
        if client is None:
            self._set_status("Not connected.", error=True)
            return
        self._set_status("Loading posts…")
        try:
            posts = await client.list_posts(search=search)
        except ApiError as err:
            self._set_status(f"Failed to load posts: {err}", error=True)
            return
        table = self.query_one("#post-table", DataTable)
        table.clear()
        self._rows.clear()
        for post in posts:
            key = table.add_row(
                str(post.id),
                post.title,
                post.status,
                post.modified_gmt.replace("T", " "),
            )
            self._rows[key] = post
        self._set_status(f"{len(posts)} post(s). Enter to open, / to search, r to reload.")

    def _set_status(self, text: str, *, error: bool = False) -> None:
        status = self.query_one("#post-status", Static)
        status.update(text)
        status.set_class(error, "error")

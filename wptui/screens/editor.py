"""EditorScreen: create or open a post/page, edit its blocks, and save back."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, Static

from wptui.api import ApiError, ConflictError, PostSettings, PostSummary
from wptui.blocks import parse, serialize
from wptui.widgets.canvas import BlockCanvas


class EditorScreen(Screen[None]):
    """Edit one post/page's title, block content, and settings.

    Two modes: pass a ``summary`` to open an existing post, or pass ``post_type`` (with no
    summary) to create a new one. A new post issues no write until the first save (no
    orphan drafts) and skips the conflict pre-check.
    """

    BINDINGS = [
        ("ctrl+s", "save", "Save"),
        Binding("ctrl+e", "open_settings", "Settings", priority=True),
        Binding("ctrl+up", "move_up", "Move up", priority=True),
        Binding("ctrl+down", "move_down", "Move down", priority=True),
        Binding("ctrl+n", "insert_paragraph", "New ¶", priority=True),
        Binding("ctrl+delete", "delete_block", "Delete block", priority=True),
        ("escape", "app.pop_screen", "Back"),
    ]

    def __init__(self, summary: PostSummary | None = None, *, post_type: str = "post") -> None:
        super().__init__()
        self._summary = summary
        self._post_id: int | None = summary.id if summary is not None else None
        self._post_type = summary.post_type if summary is not None else post_type
        self._modified_gmt: str | None = None
        self._settings = PostSettings(post_type=self._post_type)
        self._canvas: BlockCanvas | None = None
        self._saving = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Input(placeholder="(title)", id="editor-title")
        yield Static("Loading…", id="editor-body")
        yield Static("", id="editor-status")
        yield Footer()

    def on_mount(self) -> None:
        if self._summary is not None:
            self._load()
        else:
            self.call_later(self._start_blank)

    async def _start_blank(self) -> None:
        """Set up an empty canvas for a brand-new post/page (no fetch)."""
        canvas = BlockCanvas([])
        self._canvas = canvas
        await self.query_one("#editor-body", Static).remove()
        await self.mount(canvas, before=self.query_one("#editor-status"))
        self.query_one("#editor-title", Input).focus()
        self._set_status(f"New {self._post_type} · Ctrl+E settings · Ctrl+S to save")

    @work(exclusive=True, group="editor-load")
    async def _load(self) -> None:
        client = self.app.client  # type: ignore[attr-defined]
        if client is None:
            self._set_status("Not connected.", error=True)
            return
        try:
            detail = await client.get_post(self._summary.id, self._post_type)
        except ApiError as err:
            self._set_status(f"Failed to load: {err}", error=True)
            return
        self._modified_gmt = detail.modified_gmt
        self._post_type = detail.post_type or self._post_type
        self._settings = PostSettings.from_detail(detail)
        self.query_one("#editor-title", Input).value = detail.title_raw
        blocks = parse(detail.content_raw)
        canvas = BlockCanvas(blocks)
        self._canvas = canvas
        body = self.query_one("#editor-body", Static)
        await body.remove()
        await self.mount(canvas, before=self.query_one("#editor-status"))
        self._set_status(
            f"status: {detail.status} · {len(blocks)} block(s) · Ctrl+E settings · Ctrl+S to save"
        )

    async def action_open_settings(self) -> None:
        """Open the post-settings screen (wired in U5); no-op until the canvas exists."""
        if self._canvas is None:
            return
        from wptui.screens.post_settings import PostSettingsScreen

        self.app.push_screen(PostSettingsScreen(self._settings))

    async def action_move_up(self) -> None:
        if self._canvas is not None:
            await self._canvas.move_focused(-1)

    async def action_move_down(self) -> None:
        if self._canvas is not None:
            await self._canvas.move_focused(+1)

    async def action_insert_paragraph(self) -> None:
        if self._canvas is not None:
            await self._canvas.insert_paragraph()

    async def action_delete_block(self) -> None:
        if self._canvas is not None:
            await self._canvas.delete_focused()

    def on_inline_markdown_area_vim_command(self, message) -> None:
        """Handle ``:w`` / ``:q`` from a Vim command line."""
        if message.name == "save":
            self._save()
        elif message.name == "quit":
            self.app.pop_screen()

    def action_save(self) -> None:
        self._save()

    @work(group="editor-save")
    async def _save(self) -> None:
        client = self.app.client  # type: ignore[attr-defined]
        if client is None or self._canvas is None:
            return
        # Ignore a second save while one is in flight rather than cancel-and-restart it:
        # cancelling a PUT that already committed would re-check with a stale timestamp
        # and report a false conflict, tempting the user to reload and lose their edits.
        if self._saving:
            return
        self._saving = True
        self._set_status("Saving…")
        try:
            # Building the payload can itself raise (serialization); keep it inside the
            # guard so a bad block reports an error instead of crashing the save worker.
            self._canvas.sync()
            content = serialize(self._canvas.blocks)
            title = self.query_one("#editor-title", Input).value
            if self._post_id is None:
                detail = await client.create_post(
                    self._post_type,
                    title_raw=title,
                    content_raw=content,
                    settings=self._settings,
                )
            else:
                detail = await client.update_post(
                    self._post_id,
                    content_raw=content,
                    title_raw=title,
                    settings=self._settings,
                    expected_modified_gmt=self._modified_gmt,
                )
        except ConflictError as err:
            self._set_status(f"Not saved: {err} Reload to get the latest.", error=True)
            return
        except ApiError as err:
            self._set_status(f"Save failed: {err}", error=True)
            return
        except Exception as err:  # never let a save crash the whole TUI
            self._set_status(f"Save failed unexpectedly: {err}", error=True)
            return
        finally:
            self._saving = False
        # Adopt the server's copy (id on create, fresh timestamp, resolved settings).
        self._post_id = detail.id
        self._post_type = detail.post_type or self._post_type
        self._modified_gmt = detail.modified_gmt
        self._settings = PostSettings.from_detail(detail)
        self._set_status(f"Saved · {detail.status} · modified {detail.modified_gmt}")

    def _set_status(self, text: str, *, error: bool = False) -> None:
        status = self.query_one("#editor-status", Static)
        status.update(text)
        status.set_class(error, "error")

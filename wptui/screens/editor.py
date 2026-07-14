"""EditorScreen: create or open a post/page, edit its blocks, and save back."""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, Input, Static

from wptui.api import (
    ApiError,
    ConflictError,
    NetworkError,
    PostDetail,
    PostSettings,
    PostSummary,
)
from wptui.autosave import clear_snapshot, list_snapshots, read_snapshot, write_snapshot
from wptui.blocks import Block, parse, serialize
from wptui.widgets.canvas import BlockCanvas

# How often the editor snapshots the in-progress buffer to disk (crash safety).
_AUTOSAVE_INTERVAL = 2.0


class EditorScreen(Screen[None]):
    """Edit one post/page's title, block content, and settings.

    Three modes: pass a ``summary`` to open an existing post; pass ``post_type`` (with no
    summary) to create a blank new one; or pass ``import_blocks``/``import_title`` (with no
    summary) to open a new post pre-filled with already-built content (e.g. piped-in
    markdown). All new-post modes issue no write until the first save (no orphan drafts)
    and skip the conflict pre-check; the pre-filled mode additionally skips the "resume an
    unsaved draft?" prompt, since the imported content is itself the just-arrived unsaved
    state.
    """

    BINDINGS = [
        ("ctrl+s", "save", "Save"),
        Binding("ctrl+e", "open_settings", "Settings", priority=True),
        Binding("ctrl+up", "move_up", "Move up", priority=True),
        Binding("ctrl+down", "move_down", "Move down", priority=True),
        Binding("ctrl+n", "insert_paragraph", "New ¶", priority=True),
        Binding("ctrl+g", "add_image", "Add image", priority=True),
        Binding("ctrl+delete", "delete_block", "Delete block", priority=True),
        ("escape", "app.pop_screen", "Back"),
    ]

    def __init__(
        self,
        summary: PostSummary | None = None,
        *,
        post_type: str = "post",
        import_blocks: list[Block] | None = None,
        import_title: str | None = None,
    ) -> None:
        super().__init__()
        self._summary = summary
        self._post_id: int | None = summary.id if summary is not None else None
        self._post_type = summary.post_type if summary is not None else post_type
        # Pre-built content (e.g. converted from piped markdown) to open with instead of
        # starting blank or fetching from the server. ``None`` unless the caller passed it.
        self._import_blocks = import_blocks
        self._import_title = import_title
        self._modified_gmt: str | None = None
        self._settings = PostSettings(post_type=self._post_type)
        self._canvas: BlockCanvas | None = None
        self._saving = False
        # Set when a create fails with a lost response (it may have committed): the next save
        # reconciles before creating again so a retry can't silently duplicate the post.
        self._unverified_create = False
        # Local autosave: a per-session id keys a brand-new post (no server id yet); the draft
        # key + last-written signature drive crash-safe snapshots to disk.
        self._session = uuid4().hex
        self._draft_key: str | None = None
        self._last_saved_sig: str | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Input(placeholder="(title)", id="editor-title")
        yield Static("Loading…", id="editor-body")
        yield Static("", id="editor-status")
        yield Footer()

    def on_mount(self) -> None:
        self._draft_key = self._draft_key_for(self._post_id)
        if self._summary is not None:
            self._load()
        elif self._import_blocks is not None:
            self.call_later(self._start_import)
        else:
            self.call_later(self._start_blank)
        # Snapshot the buffer on a timer so a crash/quit never loses unsaved work.
        self.set_interval(_AUTOSAVE_INTERVAL, self._autosave_tick)

    async def _start_blank(self) -> None:
        """Set up an empty canvas for a brand-new post/page (no fetch)."""
        canvas = BlockCanvas([])
        self._canvas = canvas
        await self.query_one("#editor-body", Static).remove()
        await self.mount(canvas, before=self.query_one("#editor-status"))
        self.query_one("#editor-title", Input).focus()
        self._set_status(f"New {self._post_type} · Ctrl+E settings · Ctrl+S to save")
        self._maybe_offer_resume_new()

    async def _start_import(self) -> None:
        """Set up a new post pre-filled with already-converted content (no fetch).

        No WordPress write happens here — this behaves exactly like ``_start_blank``
        content-wise, just pre-populated — and unlike a blank new post, it deliberately
        skips ``_maybe_offer_resume_new``: the imported content is itself the just-arrived
        unsaved state, and offering an unrelated stale draft here risks discarding the
        import if the user declines it.
        """
        blocks = self._import_blocks or []
        title = self._import_title or ""
        self.query_one("#editor-title", Input).value = title
        canvas = BlockCanvas(blocks)
        self._canvas = canvas
        await self.query_one("#editor-body", Static).remove()
        await self.mount(canvas, before=self.query_one("#editor-status"))
        self._set_status(f"Imported {len(blocks)} block(s) · Ctrl+E settings · Ctrl+S to save")
        if title:
            self._focus_first_block()
        else:
            self.query_one("#editor-title", Input).focus()
        # Piped content arrives instantly and fully formed, so the usual "typing takes
        # longer than the first tick" assumption doesn't hold: snapshot right away rather
        # than risk losing it to a quit within the first autosave interval.
        self._autosave_tick()

    def _focus_first_block(self) -> None:
        """Focus the first rendered block widget (used when a title is already filled in)."""
        if self._canvas is not None:
            self._canvas.focus_first_block()

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
        if not self.is_mounted:  # screen popped while the fetch was in flight
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
        # Prime the autosave signature to the loaded content so an unedited buffer never
        # re-writes (which would clobber the very recovery snapshot we're about to offer).
        self._last_saved_sig = f"{detail.title_raw}\x00{serialize(blocks)}"
        self._maybe_offer_restore(detail.content_raw, detail.title_raw)

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

    def action_add_image(self) -> None:
        """Open the media picker; on selection, insert a new image block."""
        if self._canvas is None:
            return
        from wptui.widgets.media_picker import MediaPickerModal

        self.app.push_screen(MediaPickerModal(), self._image_uploaded)

    def _image_uploaded(self, media) -> None:
        if media is None or self._canvas is None:
            return
        from wptui.blocks.factory import new_image_block

        self.run_worker(self._canvas.insert_block(new_image_block(media)))

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
            detail = await self._commit_save(client, title, content)
        except ConflictError as err:
            self._set_status(f"Not saved: {err} Reload to get the latest.", error=True)
            return
        except NetworkError as err:
            # A create whose response was lost may have committed server-side; _commit_save
            # flags it so the next Ctrl+S reconciles before creating a (duplicate) post.
            if self._unverified_create:
                self._set_status(
                    f"Save failed: {err} Your post may already have been created — "
                    "press Ctrl+S to retry safely.",
                    error=True,
                )
            else:
                self._set_status(f"Save failed: {err}", error=True)
            return
        except ApiError as err:
            self._set_status(f"Save failed: {err}", error=True)
            return
        except Exception as err:  # never let a save crash the whole TUI
            self._set_status(f"Save failed unexpectedly: {err}", error=True)
            return
        finally:
            self._saving = False
        if detail is None:  # create deferred — the user declined the create-anyway prompt
            self._set_status("Save cancelled — check your post list for the earlier draft.")
            return
        if not self.is_mounted:  # screen popped while the save was in flight
            return
        self._adopt(detail)
        # The work is safely on the server now; drop the local recovery snapshot.
        if self._draft_key is not None:
            clear_snapshot(self._draft_key)
        self._last_saved_sig = None
        self._set_status(f"Saved · {detail.status} · modified {detail.modified_gmt}")

    async def _commit_save(
        self, client, title: str, content: str
    ) -> PostDetail | None:
        """Create or update the post; return the saved detail, or None if a create was
        deferred pending user confirmation.

        A create whose response is lost (NetworkError) may still have committed. Rather than
        blindly re-creating on the next save — which would duplicate the post — we look for
        the post that ambiguous create may have made and adopt it, turning the retry into an
        update. When the server confirms no such post exists we create; when we genuinely
        can't tell (no title to match on, search failed, or several matches) we ask first.
        """
        if self._post_id is not None:
            return await client.update_post(
                self._post_id,
                content_raw=content,
                title_raw=title,
                settings=self._settings,
                expected_modified_gmt=self._modified_gmt,
            )

        if self._unverified_create:
            status, existing = await self._find_unverified_post(client, title)
            if status == "found":
                self._unverified_create = False
                self._post_id = existing.id
                self._modified_gmt = existing.modified_gmt
                return await client.update_post(
                    existing.id,
                    content_raw=content,
                    title_raw=title,
                    settings=self._settings,
                    expected_modified_gmt=None,  # just fetched -> skip the conflict pre-check
                )
            if status == "unknown" and not await self._confirm_create_anyway():
                return None
            self._unverified_create = False  # "absent", or the user confirmed create-anyway

        try:
            return await client.create_post(
                self._post_type,
                title_raw=title,
                content_raw=content,
                settings=self._settings,
            )
        except NetworkError:
            # Response lost; the create may have landed. Flag so the next save reconciles.
            self._unverified_create = True
            raise

    async def _find_unverified_post(
        self, client, title: str
    ) -> tuple[str, PostSummary | None]:
        """Classify whether an ambiguous create landed, matching on exact title + post type.

        Returns ``("found", post)`` for a unique match, ``("absent", None)`` when the server
        was reachable and has no matching post (safe to create), or ``("unknown", None)``
        when we can't tell — empty title, search failure, or several matches — so the caller
        should ask the user before creating.
        """
        if not title.strip():
            return ("unknown", None)
        try:
            candidates = await client.list_posts(search=title, per_page=20)
        except ApiError:
            return ("unknown", None)
        norm = title.strip().casefold()
        matches = [
            p
            for p in candidates
            if p.post_type == self._post_type and p.title.strip().casefold() == norm
        ]
        if len(matches) == 1:
            return ("found", matches[0])
        if not matches:
            return ("absent", None)
        return ("unknown", None)  # several same-title posts -> can't safely auto-pick

    async def _confirm_create_anyway(self) -> bool:
        from wptui.widgets.confirm import ConfirmModal

        return bool(
            await self.app.push_screen_wait(
                ConfirmModal(
                    "Couldn't confirm whether your earlier save already created this post. "
                    "Create a new post anyway? This might make a duplicate.",
                    confirm_label="Create anyway",
                    cancel_label="Cancel",
                )
            )
        )

    def _adopt(self, detail: PostDetail) -> None:
        """Adopt the server's saved copy (id on create, fresh timestamp, resolved settings)."""
        old_key = self._draft_key
        self._post_id = detail.id
        self._post_type = detail.post_type or self._post_type
        self._modified_gmt = detail.modified_gmt
        self._settings = PostSettings.from_detail(detail)
        self._unverified_create = False
        # A create just earned a real id, so the draft key changes new-* -> post-id; drop the
        # now-orphaned new-* snapshot.
        self._draft_key = self._draft_key_for(self._post_id)
        if old_key is not None and old_key != self._draft_key:
            clear_snapshot(old_key)

    # -- local autosave -----------------------------------------------------

    def _site(self) -> str:
        profile = getattr(self.app, "profile", None)
        return profile.base_url if profile is not None else "local"

    def _draft_key_for(self, post_id: int | None) -> str:
        """A stable key for this draft: by post id when saved, else by editor session."""
        if post_id is not None:
            return f"{self._site()}|{self._post_type}|{post_id}"
        return f"{self._site()}|new|{self._session}"

    def _autosave_tick(self) -> None:
        """Write a crash-recovery snapshot if the buffer changed since the last one."""
        if not self.is_mounted or self._canvas is None or self._draft_key is None:
            return
        try:
            self._canvas.sync()
            content = serialize(self._canvas.blocks)
        except Exception:
            return  # a transiently unserializable block must not break autosave
        title = self.query_one("#editor-title", Input).value
        if not title.strip() and not content.strip():
            return  # nothing worth saving yet
        sig = f"{title}\x00{content}"
        if sig == self._last_saved_sig:
            return
        write_snapshot(self._draft_key, self._snapshot(title, content))
        self._last_saved_sig = sig

    def _snapshot(self, title: str, content: str) -> dict[str, Any]:
        return {
            "title": title,
            "content": content,
            "settings": dataclasses.asdict(self._settings),
            "post_id": self._post_id,
            "post_type": self._post_type,
            "modified_gmt": self._modified_gmt,
            "site": self._site(),
            "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    def _maybe_offer_restore(self, server_content: str, server_title: str) -> None:
        """On opening an existing post, offer to restore a newer local snapshot."""
        if self._draft_key is None:
            return
        snap = read_snapshot(self._draft_key)
        if snap is None:
            return
        # Normalize the server copy through the same parse/serialize path the snapshot took,
        # so whitespace-only differences don't trigger a needless restore prompt.
        normalized_server = serialize(parse(server_content))
        if snap.get("content", "") == normalized_server and snap.get("title", "") == server_title:
            clear_snapshot(self._draft_key)  # identical to the server -> nothing to recover
            return
        self._offer_restore(snap)

    def _maybe_offer_resume_new(self) -> None:
        """On opening a fresh new-post editor, offer to resume a prior unsaved new-post draft."""
        site = self._site()
        drafts = [
            s
            for s in list_snapshots()
            if s.get("post_id") is None and s.get("site") == site and s.get("key")
        ]
        if drafts:
            self._offer_restore(drafts[0])  # list_snapshots is newest-first

    def _offer_restore(self, snap: dict[str, Any]) -> None:
        from wptui.widgets.confirm import ConfirmModal

        key = snap.get("key")
        when = snap.get("saved_at", "an earlier session")

        def _decide(restore: bool | None) -> None:
            if restore:
                self._apply_snapshot(snap)
            elif key:
                clear_snapshot(key)  # the user chose to discard the recovery copy

        self.app.push_screen(
            ConfirmModal(
                f"Found unsaved changes from {when}. Restore them?",
                confirm_label="Restore",
                cancel_label="Discard",
            ),
            _decide,
        )

    @work(group="editor-restore")
    async def _apply_snapshot(self, snap: dict[str, Any]) -> None:
        """Replace the editor buffer with a restored snapshot."""
        if not self.is_mounted:
            return
        self.query_one("#editor-title", Input).value = snap.get("title", "")
        settings = _settings_from_snapshot(snap)
        if settings is not None:
            self._settings = settings
        self._post_id = snap.get("post_id")
        self._post_type = snap.get("post_type") or self._post_type
        self._modified_gmt = snap.get("modified_gmt")
        self._draft_key = snap.get("key") or self._draft_key
        canvas = BlockCanvas(parse(snap.get("content", "")))
        old = self._canvas
        self._canvas = canvas
        if old is not None:
            await old.remove()
        await self.mount(canvas, before=self.query_one("#editor-status"))
        self._last_saved_sig = None  # re-snapshot from the restored state on the next tick
        self._set_status("Restored unsaved changes · Ctrl+S to save")

    def _set_status(self, text: str, *, error: bool = False) -> None:
        if not self.is_mounted:  # a save/load worker may finish after the screen is popped
            return
        status = self.query_one("#editor-status", Static)
        status.update(text)
        status.set_class(error, "error")


def _settings_from_snapshot(snap: dict[str, Any]) -> PostSettings | None:
    """Rebuild PostSettings from a snapshot, tolerating a drifted/partial shape."""
    raw = snap.get("settings")
    if not isinstance(raw, dict):
        return None
    fields = {f.name for f in dataclasses.fields(PostSettings)}
    try:
        return PostSettings(**{k: v for k, v in raw.items() if k in fields})
    except TypeError:
        return None

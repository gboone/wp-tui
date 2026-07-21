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
from wptui.blocks import parse, serialize
from wptui.history import DocumentHistory
from wptui.widgets.canvas import BlockCanvas

# How often the editor snapshots the in-progress buffer to disk (crash safety).
_AUTOSAVE_INTERVAL = 2.0


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
        Binding("ctrl+g", "add_image", "Add image", priority=True),
        Binding("f3", "heading_level", "Heading level", priority=True),
        Binding("ctrl+z", "undo", "Undo", priority=True),
        Binding("ctrl+y", "redo", "Redo", priority=True),
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
        self._history: DocumentHistory | None = None
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
        else:
            self.call_later(self._start_blank)
        # Snapshot the buffer on a timer so a crash/quit never loses unsaved work.
        self.set_interval(_AUTOSAVE_INTERVAL, self._autosave_tick)

    async def _start_blank(self) -> None:
        """Set up an empty canvas for a brand-new post/page (no fetch)."""
        canvas = BlockCanvas([])
        self._canvas = canvas
        self._history = DocumentHistory("")
        await self.query_one("#editor-body", Static).remove()
        await self.mount(canvas, before=self.query_one("#editor-status"))
        self.query_one("#editor-title", Input).focus()
        self._set_status(f"New {self._post_type} · Ctrl+E settings · Ctrl+S to save")
        self._maybe_offer_resume_new()

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
        self._history = DocumentHistory(serialize(blocks))
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
            self._checkpoint()
            await self._canvas.move_focused(-1)

    async def action_move_down(self) -> None:
        if self._canvas is not None:
            self._checkpoint()
            await self._canvas.move_focused(+1)

    async def action_insert_paragraph(self) -> None:
        if self._canvas is not None:
            self._checkpoint()
            await self._canvas.insert_paragraph()

    async def action_delete_block(self) -> None:
        if self._canvas is not None:
            self._checkpoint()
            await self._canvas.delete_focused()

    def action_add_image(self) -> None:
        """Open the media picker; on selection, insert a new image block."""
        if self._canvas is None:
            return
        from wptui.widgets.media_picker import MediaPickerModal

        self.app.push_screen(MediaPickerModal(), self._image_uploaded)

    def _checkpoint(self) -> None:
        """Flush editors and record the current document snapshot for undo/redo."""
        if self._canvas is None or self._history is None:
            return
        try:
            self._canvas.sync()
            self._history.record(serialize(self._canvas.blocks))
        except Exception:
            pass  # a transiently unserializable block must not break editing

    async def action_undo(self) -> None:
        """Restore the previous document snapshot."""
        if self._canvas is None or self._history is None:
            return
        self._checkpoint()  # capture the current change before stepping back
        snapshot = self._history.undo()
        if snapshot is not None:
            await self._canvas.reload(parse(snapshot))

    async def action_redo(self) -> None:
        """Re-apply an undone snapshot."""
        if self._canvas is None or self._history is None:
            return
        self._checkpoint()  # an edit made since the last undo records here, clearing redo
        snapshot = self._history.redo()
        if snapshot is not None:
            await self._canvas.reload(parse(snapshot))

    def action_heading_level(self) -> None:
        """Open the heading-level picker for the focused heading (no-op otherwise)."""
        if self._canvas is None:
            return
        target = self._canvas.focused_block()
        if target is None or target.block_name != "core/heading":
            return
        from wptui.widgets.heading_level import HeadingLevelModal

        self.app.push_screen(HeadingLevelModal(), lambda level: self._apply_heading_level(target, level))

    def _apply_heading_level(self, target, level) -> None:
        if level is None or self._canvas is None:
            return
        self._checkpoint()
        self.run_worker(self._canvas.set_heading_level_on(target, level))

    def _image_uploaded(self, media) -> None:
        if media is None or self._canvas is None:
            return
        from wptui.blocks.factory import new_image_block

        self._checkpoint()
        self.run_worker(self._canvas.insert_block(new_image_block(media)))

    def on_inline_markdown_area_slash_requested(self, message) -> None:
        """Open the block-type switcher for the focused empty block."""
        if self._canvas is None:
            return
        # Capture the target now, while it is still focused — pushing the modal moves
        # focus away, so we cannot rely on the focus at selection time.
        target = self._canvas.focused_block()
        if target is None:
            return
        from wptui.widgets.block_switcher import BlockSwitcherModal

        self.app.push_screen(BlockSwitcherModal(), lambda bt: self._convert_block(target, bt))

    def _convert_block(self, target, block_type) -> None:
        if block_type is None or self._canvas is None:
            return
        self.run_worker(self._do_convert(target, block_type))

    async def _do_convert(self, target, block_type) -> None:
        canvas = self._canvas
        if canvas is None:
            return
        self._checkpoint()
        if not await canvas.replace_block(target, block_type.factory()):
            # The captured block is gone (e.g. deleted before the picker closed).
            self._set_status("Couldn't switch block — it's no longer here.", error=True)

    async def on_inline_markdown_area_nested_enter(self, message) -> None:
        """Enter in a list-item / quote paragraph. Awaited (not run_worker) so Textual
        processes queued Enters one at a time — each re-reads live focus, so a fast
        Enter-Enter is "new item then exit", never a stale re-split."""
        if self._canvas is not None:
            self._checkpoint()
            await self._canvas.nested_enter()

    async def on_inline_markdown_area_nested_backspace(self, message) -> None:
        """Backspace at the start of a child: remove it (empty) or merge into the previous."""
        if self._canvas is not None:
            self._checkpoint()
            await self._canvas.nested_backspace()

    async def on_inline_markdown_area_indent_requested(self, message) -> None:
        """Tab in a list-item: indent it under the previous sibling."""
        if self._canvas is not None:
            self._checkpoint()
            await self._canvas.indent_focused()

    async def on_inline_markdown_area_outdent_requested(self, message) -> None:
        """Shift+Tab in a list-item: outdent it to the enclosing list."""
        if self._canvas is not None:
            self._checkpoint()
            await self._canvas.outdent_focused()

    def on_inline_markdown_area_vim_command(self, message) -> None:
        """Handle ``:w`` / ``:q`` from a Vim command line."""
        if message.name == "save":
            self._save()
        elif message.name == "quit":
            self.app.pop_screen()

    def action_save(self) -> None:
        self._save()

    @work(group="editor-save")
    async def _save(self, *, force: bool = False) -> None:
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
            detail = await self._commit_save(client, title, content, force=force)
        except ConflictError as err:
            # A forced overwrite that still conflicts (another author saved again in the
            # same instant) shouldn't loop back into the modal — report and let the user
            # retry deliberately.
            if force:
                self._set_status(f"Overwrite failed: {err} Try again.", error=True)
            else:
                self._offer_conflict_resolution(err)
            return
        except NetworkError as err:
            # A create whose response was lost may have committed server-side; _commit_save
            # flags it so the next Ctrl+S reconciles before creating a (duplicate) post.
            if self._unverified_create:
                self._flush_local_snapshot()  # guarantee the work is on disk regardless
                self._set_status(
                    f"Not saved to {self._site()}: {err} Your post may already have been "
                    "created — kept locally; press Ctrl+S to retry safely.",
                    error=True,
                )
                self.notify(
                    "Couldn't confirm the save. Your work is kept locally on this "
                    "computer — press Ctrl+S to retry.",
                    title="Saved locally only",
                    severity="warning",
                )
            else:
                self._announce_saved_local(str(err))
            return
        except ApiError as err:
            self._announce_saved_local(str(err))
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
        self._announce_saved_remote(detail)

    def _offer_conflict_resolution(self, err: ConflictError) -> None:
        """Ask how to resolve a save conflict and act on the choice."""
        from wptui.widgets.conflict_modal import ConflictModal

        def _resolve(choice: str | None) -> None:
            if choice == "overwrite":
                self._save(force=True)
            elif choice == "reload":
                self._reload_from_server()
            else:  # "cancel" or dismissed
                self._set_status(
                    "Kept your edits — not saved. Overwrite or reload from the menu "
                    "on the next Ctrl+S.",
                    error=True,
                )

        self.app.push_screen(ConflictModal(err.server_modified_gmt), _resolve)

    @work(exclusive=True, group="editor-load")
    async def _reload_from_server(self) -> None:
        """Discard local edits and reload the server's current version of the post.

        Destructive by design — only reached from the explicit "Reload" conflict choice.
        Resets the baseline (``modified_gmt``, settings, undo history) so the next save
        checks against the freshly-loaded state instead of immediately re-conflicting.
        """
        client = self.app.client  # type: ignore[attr-defined]
        if client is None or self._post_id is None:
            return
        # Hold the save guard across the whole reload: the editor stays interactive while
        # get_post is in flight, and a Ctrl+S in that window would re-check the still-stale
        # timestamp and stack a phantom second conflict modal over content we're replacing.
        self._saving = True
        try:
            try:
                detail = await client.get_post(self._post_id, self._post_type)
            except ApiError as err:
                self._set_status(f"Reload failed: {err}", error=True)
                return
            if not self.is_mounted:  # screen popped while the fetch was in flight
                return
            self._modified_gmt = detail.modified_gmt
            self._post_type = detail.post_type or self._post_type
            self._settings = PostSettings.from_detail(detail)
            self.query_one("#editor-title", Input).value = detail.title_raw
            blocks = parse(detail.content_raw)
            serialized = serialize(blocks)
            canvas = BlockCanvas(blocks)
            old = self._canvas
            self._canvas = canvas
            self._history = DocumentHistory(serialized)
            if old is not None:
                await old.remove()
            await self.mount(canvas, before=self.query_one("#editor-status"))
            # The local edits are gone by the user's explicit choice — drop their on-disk
            # recovery snapshot now (matching the save path) instead of waiting for the next
            # autosave tick, so a crash in that window can't offer to restore discarded work.
            if self._draft_key is not None:
                clear_snapshot(self._draft_key)
            # Prime the signature to the reloaded content (like _load) so an untouched buffer
            # doesn't immediately re-snapshot.
            self._last_saved_sig = f"{detail.title_raw}\x00{serialized}"
            self._set_status(
                f"Reloaded server version · {len(blocks)} block(s) · "
                "your earlier edits were discarded"
            )
        finally:
            self._saving = False

    async def _commit_save(
        self, client, title: str, content: str, *, force: bool = False
    ) -> PostDetail | None:
        """Create or update the post; return the saved detail, or None if a create was
        deferred pending user confirmation.

        ``force`` skips the update's ``modified_gmt`` conflict pre-check so a deliberate
        overwrite wins — used only after the user chose "Overwrite" on a conflict.

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
                expected_modified_gmt=None if force else self._modified_gmt,
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
        # Normalize the trailing slash: the URL seeds both the draft key and the recovery
        # filter, so "https://site.com/" and "https://site.com" must not fork into two keys
        # that hide each other's snapshots across a reconnect.
        return profile.base_url.rstrip("/") if profile is not None else "local"

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
        if self._history is not None:
            self._history.record(content)  # coarse text-edit checkpoint for undo/redo
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

    def _flush_local_snapshot(self) -> bool:
        """Write the current buffer to the recovery store *now* (not on the timer).

        Called when a remote save fails so the latest work is guaranteed on disk before we
        tell the user it's safe locally, instead of relying on the next autosave tick (which
        the user may never reach if they quit after seeing the failure). Returns whether a
        snapshot was actually persisted.
        """
        if self._canvas is None or self._draft_key is None:
            return False
        try:
            self._canvas.sync()
            content = serialize(self._canvas.blocks)
        except Exception:
            return False  # a transiently unserializable block must not break the flush
        title = self.query_one("#editor-title", Input).value
        if not title.strip() and not content.strip():
            return False  # nothing worth saving yet
        write_snapshot(self._draft_key, self._snapshot(title, content))
        self._last_saved_sig = f"{title}\x00{content}"
        return True

    def _announce_saved_remote(self, detail: PostDetail) -> None:
        """Confirm — unmistakably — that the post is now on the server."""
        msg = f"Saved to {self._site()} · {detail.status}"
        self._set_status(f"✓ {msg} · modified {detail.modified_gmt}")
        self.notify(msg, title="Saved to site", severity="information")

    def _announce_saved_local(self, problem: str) -> None:
        """Report a failed remote save, distinguishing "kept locally" from "lost".

        On a reachable-but-rejected or unreachable server the buffer is flushed to disk and
        the user is told their work is safe on this computer; only if even the local flush
        fails (nothing to save, or an unserializable buffer) is it a bare failure.
        """
        if self._flush_local_snapshot():
            self._set_status(
                f"⚠ Not saved to {self._site()}: {problem} Kept locally on this "
                "computer — reopen to recover, or press Ctrl+S to retry.",
                error=True,
            )
            self.notify(
                f"Couldn't reach {self._site()}. Your work is saved locally on this "
                "computer only — press Ctrl+S to retry.",
                title="Saved locally only",
                severity="warning",
            )
        else:
            self._set_status(f"Save failed: {problem}", error=True)
            self.notify(f"Save failed: {problem}", title="Save failed", severity="error")

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
        self._history = DocumentHistory(serialize(canvas.blocks))  # baseline on the restored content
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

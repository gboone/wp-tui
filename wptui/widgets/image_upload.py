"""ImageUploadModal: add an image by local filepath, with a metadata prompt.

The user supplies a path (typed, pasted, or drag-dropped — normalized via
:func:`wptui.paths.normalize_dropped_path`) plus optional alt/caption/title/description,
and the file is uploaded to the media library in one request. Dismisses with the created
:class:`MediaItem`, or ``None`` if cancelled.
"""

from __future__ import annotations

import os

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

from wptui.api import ApiError, MediaItem
from wptui.paths import normalize_dropped_path


class ImageUploadModal(ModalScreen[MediaItem]):
    """Prompt for a filepath + media metadata, then upload."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(id="upload-modal"):
            yield Static("Add image from file", classes="upload-title")
            yield Input(placeholder="path (paste or drag a file here)", id="img-path")
            yield Input(placeholder="alt text", id="img-alt")
            yield Input(placeholder="caption", id="img-caption")
            yield Input(placeholder="title", id="img-title")
            yield Input(placeholder="description", id="img-desc")
            yield Button("Upload", id="img-upload", variant="primary")
            yield Static("", id="img-upload-status")

    @on(Button.Pressed, "#img-upload")
    def _upload_pressed(self) -> None:
        self._upload()

    @on(Input.Submitted, "#img-path")
    def _path_submitted(self) -> None:
        self._upload()

    @work(exclusive=True, group="media-upload")
    async def _upload(self) -> None:
        raw = self.query_one("#img-path", Input).value
        path = normalize_dropped_path(raw)
        status = self.query_one("#img-upload-status", Static)
        if not path or not os.path.exists(path):
            status.update("File not found — check the path.")
            return
        client = self.app.client  # type: ignore[attr-defined]
        if client is None:
            status.update("Not connected.")
            return
        status.update("Uploading…")
        try:
            media = await client.upload_media(
                path,
                title=self.query_one("#img-title", Input).value.strip(),
                alt=self.query_one("#img-alt", Input).value,
                caption=self.query_one("#img-caption", Input).value,
                description=self.query_one("#img-desc", Input).value,
            )
        except ApiError as err:
            status.update(f"Upload failed: {err}")
            return
        self.dismiss(media)

    def action_cancel(self) -> None:
        self.dismiss(None)

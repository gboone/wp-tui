"""MediaPickerModal: pick an existing library image, or upload a new one.

The unified image entry point. Lists recent library images (searchable) as text rows —
a terminal can't show thumbnails — and dismisses with the chosen :class:`MediaItem`.
"Upload new file…" chains to the existing :class:`ImageUploadModal` and passes its result
straight back out, so a caller can't tell a picked image from a freshly uploaded one.
Dismisses ``None`` on cancel.
"""

from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, OptionList, Static

from wptui.api import ApiError, MediaItem


class MediaPickerModal(ModalScreen[MediaItem]):
    """Choose an existing image from the media library, or upload a new one."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self) -> None:
        super().__init__()
        self._items: list[MediaItem] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="media-picker"):
            yield Static("Choose an image", classes="media-title")
            yield Input(placeholder="search…", id="media-search")
            yield OptionList(id="media-list")
            yield Button("Upload new file…", id="media-upload")
            yield Static("", id="media-status")

    def on_mount(self) -> None:
        self._load()

    @work(exclusive=True, group="media-load")
    async def _load(self, search: str | None = None) -> None:
        client = self.app.client  # type: ignore[attr-defined]
        if client is None:
            return
        try:
            items = await client.list_media(search)
        except ApiError as err:
            if self.is_mounted:
                self.query_one("#media-status", Static).update(f"Failed to load: {err}")
            return
        if not self.is_mounted:  # picker dismissed while loading
            return
        self._items = items
        option_list = self.query_one("#media-list", OptionList)
        option_list.clear_options()
        for item in items:
            option_list.add_option(_row_label(item))
        status = "" if items else "No images found — use Upload new file…"
        self.query_one("#media-status", Static).update(status)

    @on(Input.Submitted, "#media-search")
    def _search(self, event: Input.Submitted) -> None:
        self._load(event.value.strip() or None)

    @on(OptionList.OptionSelected, "#media-list")
    def _pick(self, event: OptionList.OptionSelected) -> None:
        if 0 <= event.option_index < len(self._items):
            self.dismiss(self._items[event.option_index])

    @on(Button.Pressed, "#media-upload")
    def _upload_new(self) -> None:
        from wptui.widgets.image_upload import ImageUploadModal

        self.app.push_screen(ImageUploadModal(), self._uploaded)

    def _uploaded(self, media: MediaItem | None) -> None:
        # A successful upload flows back out of the picker as the selection.
        if media is not None and self.is_mounted:
            self.dismiss(media)

    def action_cancel(self) -> None:
        self.dismiss(None)


def _row_label(item: MediaItem) -> str:
    name = item.source_url.rsplit("/", 1)[-1] or item.title_raw or f"media {item.id}"
    return f"{name} — {item.mime} (#{item.id})"

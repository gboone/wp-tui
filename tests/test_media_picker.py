"""Tests for the media library picker (U2) and the entries routed through it (U3)."""

from __future__ import annotations

import pytest
from textual.app import App
from textual.widgets import Button, Input, OptionList

from wptui.api import MediaItem
from wptui.widgets.media_picker import MediaPickerModal

IMAGES = [
    MediaItem(1, "https://x/cat.png", alt="a cat", mime="image/png"),
    MediaItem(2, "https://x/dog.jpg", alt="a dog", mime="image/jpeg"),
]


class MediaClient:
    def __init__(self, items=IMAGES) -> None:
        self.items = items
        self.searched: list = []

    async def list_media(self, search=None, *, per_page=30):
        self.searched.append(search)
        if search:
            return [m for m in self.items if search.lower() in m.source_url.lower()]
        return self.items

    async def upload_media(self, path, *, title="", alt="", caption="", description=""):
        return MediaItem(999, "https://x/new.png", alt=alt, caption_raw=caption)

    async def aclose(self):
        pass


class _Harness(App):
    def __init__(self, client) -> None:
        super().__init__()
        self.client = client

    def compose(self):
        yield from ()


async def _open_picker(pilot, app, result):
    app.push_screen(MediaPickerModal(), lambda m: result.update(media=m))
    await pilot.pause()
    await pilot.pause()
    return app.screen


@pytest.mark.asyncio
async def test_select_existing_image_dismisses_with_it():
    app = _Harness(MediaClient())
    result: dict = {}
    async with app.run_test() as pilot:
        await pilot.pause()
        picker = await _open_picker(pilot, app, result)
        ol = picker.query_one("#media-list", OptionList)
        assert ol.option_count == 2
        ol.focus()
        ol.highlighted = 1  # the dog
        await pilot.press("enter")
        await pilot.pause()
    assert result["media"].id == 2


@pytest.mark.asyncio
async def test_search_requeries_and_filters():
    client = MediaClient()
    app = _Harness(client)
    result: dict = {}
    async with app.run_test() as pilot:
        await pilot.pause()
        picker = await _open_picker(pilot, app, result)
        picker.query_one("#media-search", Input).value = "cat"
        await pilot.pause()
        await picker.query_one("#media-search", Input).action_submit()
        await pilot.pause()
        await pilot.pause()
        assert client.searched[-1] == "cat"
        assert picker.query_one("#media-list", OptionList).option_count == 1


@pytest.mark.asyncio
async def test_upload_new_chains_result_out_of_picker():
    app = _Harness(MediaClient())
    result: dict = {}
    async with app.run_test() as pilot:
        await pilot.pause()
        picker = await _open_picker(pilot, app, result)
        picker.query_one("#media-upload", Button).press()
        await pilot.pause()
        from wptui.widgets.image_upload import ImageUploadModal

        assert isinstance(app.screen, ImageUploadModal)
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".png") as tf:
            tf.write(b"img")
            tf.flush()
            app.screen.query_one("#img-path", Input).value = tf.name
            await pilot.pause()
            app.screen.query_one("#img-upload", Button).press()
            await pilot.pause()
            await pilot.pause()
    # The uploaded media flowed back out of the picker as the selection.
    assert result["media"].id == 999


@pytest.mark.asyncio
async def test_escape_dismisses_none():
    app = _Harness(MediaClient())
    result: dict = {}
    async with app.run_test() as pilot:
        await pilot.pause()
        await _open_picker(pilot, app, result)
        await pilot.press("escape")
        await pilot.pause()
    assert result["media"] is None


@pytest.mark.asyncio
async def test_empty_library_shows_status_and_upload_available():
    app = _Harness(MediaClient(items=[]))
    result: dict = {}
    async with app.run_test() as pilot:
        await pilot.pause()
        picker = await _open_picker(pilot, app, result)
        assert picker.query_one("#media-list", OptionList).option_count == 0
        assert picker.query_one("#media-upload", Button)  # upload still reachable

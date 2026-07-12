"""Tests for image upload: the factory, the modal, and editor insertion (U7)."""

from __future__ import annotations

import pytest
from textual.app import App
from textual.widgets import Button, Input

from wptui.api import MediaItem
from wptui.api.errors import NetworkError
from wptui.blocks import parse, serialize
from wptui.blocks.factory import new_image_block
from wptui.blocks.image import get_image_parts


# ---------------------------------------------------------------- factory (headless)


def test_new_image_block_serializes_and_round_trips():
    media = MediaItem(31, "https://x/pic.png", alt="a cat", caption_raw="my cat")
    block = new_image_block(media)
    out = serialize([block])
    assert out.startswith("<!-- wp:image ")
    assert 'src="https://x/pic.png"' in out
    assert 'class="wp-image-31"' in out
    assert "my cat" in out

    reparsed = parse(out)[0]
    parts = get_image_parts(reparsed)
    assert parts.src == "https://x/pic.png"
    assert parts.alt == "a cat"
    assert "my cat" in parts.caption_html


def test_new_image_block_escapes_metadata():
    media = MediaItem(1, "https://x/a.png?x=1&y=2", alt='he said "hi"', caption_raw="a < b")
    out = serialize([new_image_block(media)])
    assert "x=1&amp;y=2" in out
    assert "&quot;hi&quot;" in out
    assert "a &lt; b" in out


# ---------------------------------------------------------------- modal


class UploadClient:
    def __init__(self) -> None:
        self.path: str | None = None
        self.meta: tuple | None = None

    async def upload_media(self, path, *, title="", alt="", caption="", description=""):
        self.path = path
        self.meta = (title, alt, caption, description)
        return MediaItem(5, "https://x/up.png", alt=alt, caption_raw=caption)

    async def aclose(self):
        pass


class _Harness(App):
    def compose(self):
        yield from ()


@pytest.mark.asyncio
async def test_modal_normalizes_path_and_uploads(tmp_path):
    from wptui.widgets.image_upload import ImageUploadModal

    real = tmp_path / "photo.png"
    real.write_bytes(b"img")

    client = UploadClient()
    app = _Harness()
    app.client = client
    result: dict = {}
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(ImageUploadModal(), lambda m: result.update(media=m))
        await pilot.pause()
        screen = app.screen
        # A quoted path (as a terminal drag delivers) must be normalized before upload.
        screen.query_one("#img-path", Input).value = f'"{real}"'
        screen.query_one("#img-alt", Input).value = "alt text"
        screen.query_one("#img-caption", Input).value = "cap"
        await pilot.pause()
        screen.query_one("#img-upload", Button).press()
        await pilot.pause()
        await pilot.pause()

    assert client.path == str(real)  # unquoted, normalized
    assert client.meta == ("", "alt text", "cap", "")
    assert result["media"].id == 5


@pytest.mark.asyncio
async def test_modal_missing_file_does_not_upload_or_dismiss():
    from wptui.widgets.image_upload import ImageUploadModal

    client = UploadClient()
    app = _Harness()
    app.client = client
    dismissed: dict = {}
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(ImageUploadModal(), lambda m: dismissed.update(m=m))
        await pilot.pause()
        app.screen.query_one("#img-path", Input).value = "/no/such/file.png"
        await pilot.pause()
        app.screen.query_one("#img-upload", Button).press()
        await pilot.pause()
        await pilot.pause()
        assert client.path is None  # never uploaded
        assert isinstance(app.screen, ImageUploadModal)  # still open, not dismissed
        assert "m" not in dismissed


@pytest.mark.asyncio
async def test_modal_upload_failure_keeps_modal_open(tmp_path):
    from wptui.widgets.image_upload import ImageUploadModal

    real = tmp_path / "p.png"
    real.write_bytes(b"x")

    class FailClient:
        async def upload_media(self, *a, **k):
            raise NetworkError("server said no")

        async def aclose(self):
            pass

    app = _Harness()
    app.client = FailClient()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(ImageUploadModal())
        await pilot.pause()
        app.screen.query_one("#img-path", Input).value = str(real)
        await pilot.pause()
        app.screen.query_one("#img-upload", Button).press()
        await pilot.pause()
        await pilot.pause()
        assert isinstance(app.screen, ImageUploadModal)  # error surfaced, not crashed


# ---------------------------------------------------------------- editor insertion


@pytest.mark.asyncio
async def test_ctrl_g_inserts_uploaded_image_block(tmp_path):
    # Ctrl+G now opens the media picker; "Upload new file…" reaches the upload modal,
    # and the uploaded image is inserted as a block (the pre-existing path, one hop deeper).
    from wptui.api.dto import PostDetail, PostSummary
    from wptui.app import WPTuiApp
    from wptui.screens.editor import EditorScreen
    from wptui.widgets.canvas import BlockCanvas
    from wptui.widgets.image_upload import ImageUploadModal
    from wptui.widgets.media_picker import MediaPickerModal

    real = tmp_path / "x.png"
    real.write_bytes(b"img")

    class Client(UploadClient):
        async def get_post(self, pid, post_type="post"):
            return PostDetail(pid, "T", "<!-- wp:paragraph -->\n<p>hi</p>\n<!-- /wp:paragraph -->",
                              "draft", "2026-01-01T00:00:00", "http://x/1")

        async def list_media(self, search=None, *, per_page=30):
            return []  # empty library — force the upload path

    app = WPTuiApp()
    app.client = Client()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(EditorScreen(PostSummary(1, "T", "draft", "2026-01-01T00:00:00", "http://x/1")))
        await pilot.pause()
        await pilot.pause()
        await pilot.press("ctrl+g")
        await pilot.pause()
        await pilot.pause()
        assert isinstance(app.screen, MediaPickerModal)
        app.screen.query_one("#media-upload", Button).press()
        await pilot.pause()
        assert isinstance(app.screen, ImageUploadModal)
        app.screen.query_one("#img-path", Input).value = str(real)
        await pilot.pause()
        app.screen.query_one("#img-upload", Button).press()
        await pilot.pause()
        await pilot.pause()
        # Back on the editor; a new image block is in the canvas model.
        canvas = app.screen.query_one(BlockCanvas)
        assert any(b.block_name == "core/image" for b in canvas.blocks)

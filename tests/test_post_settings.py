"""Tests for the post settings screen (U5)."""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Input, Select

from wptui.api import PostSettings
from wptui.screens.post_settings import PostSettingsScreen


class Harness(App):
    def __init__(self, settings) -> None:
        super().__init__()
        self._settings = settings

    def compose(self) -> ComposeResult:
        yield from ()

    async def on_mount(self) -> None:
        self.push_screen(PostSettingsScreen(self._settings))


@pytest.mark.asyncio
async def test_editing_fields_writes_back_to_settings():
    settings = PostSettings(post_type="post", status="draft")
    app = Harness(settings)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        screen.query_one("#set-status", Select).value = "publish"
        screen.query_one("#set-slug", Input).value = "my-slug"
        screen.query_one("#set-excerpt", Input).value = "a summary"
        screen.query_one("#set-date", Input).value = "2026-07-11T09:00:00"
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()

    assert settings.status == "publish"
    assert settings.slug == "my-slug"
    assert settings.excerpt_raw == "a summary"
    assert settings.date == "2026-07-11T09:00:00"


@pytest.mark.asyncio
async def test_post_shows_taxonomy_fields_not_page_fields():
    app = Harness(PostSettings(post_type="post"))
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        assert screen.query("#set-categories")  # taxonomy controls present
        assert screen.query("#set-tags")
        assert not screen.query("#set-parent")  # no page fields
        assert not screen.query("#set-template")


@pytest.mark.asyncio
async def test_page_shows_hierarchy_fields_and_writes_them_back():
    settings = PostSettings(post_type="page")
    app = Harness(settings)
    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        assert screen.query("#set-parent") and screen.query("#set-template")
        assert not screen.query("#set-categories")  # no taxonomy for pages
        screen.query_one("#set-parent", Input).value = "12"
        screen.query_one("#set-template", Input).value = "full-width.php"
        screen.query_one("#set-menu-order", Input).value = "3"
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()

    assert settings.parent == 12
    assert settings.template == "full-width.php"
    assert settings.menu_order == 3


@pytest.mark.asyncio
async def test_editor_ctrl_e_opens_settings():
    from wptui.app import WPTuiApp
    from wptui.screens.editor import EditorScreen

    class Client:
        async def get_post(self, pid, post_type="post"):
            from wptui.api.dto import PostDetail

            return PostDetail(pid, "T", "<!-- wp:paragraph -->\n<p>x</p>\n<!-- /wp:paragraph -->",
                              "draft", "2026-01-01T00:00:00", "http://x/1")

        async def aclose(self):
            pass

    from wptui.api.dto import PostSummary

    app = WPTuiApp()
    app.client = Client()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(EditorScreen(PostSummary(1, "T", "draft", "2026-01-01T00:00:00", "http://x/1")))
        await pilot.pause()
        await pilot.pause()
        await pilot.press("ctrl+e")
        await pilot.pause()
        assert isinstance(app.screen, PostSettingsScreen)

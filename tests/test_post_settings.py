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


class TermClient:
    """Fake client for term picker tests."""

    def __init__(self) -> None:
        self.created: list[tuple[str, str]] = []

    async def list_terms(self, taxonomy, search=None, **kw):
        from wptui.api import Term

        rows = [Term(1, "News", "category"), Term(2, "Reviews", "category"), Term(3, "Life", "category")]
        if search:
            rows = [t for t in rows if search.lower() in t.name.lower()]
        return rows

    async def create_term(self, taxonomy, name):
        from wptui.api import Term

        self.created.append((taxonomy, name))
        return Term(99, name, "category")

    async def aclose(self):
        pass


@pytest.mark.asyncio
async def test_term_picker_selects_and_returns_ids():
    from textual.widgets import SelectionList

    from wptui.widgets.term_picker import TermPicker

    class App2(App):
        def compose(self):
            yield from ()

    app = App2()
    app.client = TermClient()
    result: dict = {}
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(TermPicker("categories", [1]), lambda ids: result.update(ids=ids))
        await pilot.pause()
        await pilot.pause()
        sl = app.screen.query_one("#term-list", SelectionList)
        # id 1 came in pre-selected; add id 2 as well.
        sl.select(2)
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
    assert result["ids"] == [1, 2]


@pytest.mark.asyncio
async def test_term_picker_creates_new_term():
    from wptui.widgets.term_picker import TermPicker

    class App2(App):
        def compose(self):
            yield from ()

    client = TermClient()
    app = App2()
    app.client = client
    result: dict = {}
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(TermPicker("tags", []), lambda ids: result.update(ids=ids))
        await pilot.pause()
        await pilot.pause()
        from textual.widgets import Input as TInput

        from textual.widgets import Button as TButton

        app.screen.query_one("#term-new", TInput).value = "Fresh"
        await pilot.pause()
        app.screen.query_one("#term-add", TButton).press()
        await pilot.pause()
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
    assert client.created == [("tags", "Fresh")]
    assert 99 in result["ids"]  # newly created term is selected


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

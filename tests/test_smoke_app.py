"""Headless smoke test: boot the app and drive connect -> list -> view."""

from __future__ import annotations

import pytest

from wptui.api.dto import PostDetail, PostSummary


class FakeClient:
    """Stand-in for WordPressClient with no network."""

    def __init__(self) -> None:
        self.closed = False

    async def verify(self) -> dict:
        return {"id": 1, "name": "tester"}

    async def list_posts(self, *, search=None, **_kw) -> list[PostSummary]:
        posts = [
            PostSummary(1, "Hello World", "publish", "2026-01-01T00:00:00", "http://x/1"),
            PostSummary(2, "Draft Two", "draft", "2026-02-02T00:00:00", "http://x/2"),
        ]
        if search:
            posts = [p for p in posts if search.lower() in p.title.lower()]
        return posts

    async def get_post(self, post_id: int) -> PostDetail:
        return PostDetail(
            id=post_id,
            title_raw="Hello World",
            content_raw="<!-- wp:paragraph -->\n<p>Hi there.</p>\n<!-- /wp:paragraph -->",
            status="publish",
            modified_gmt="2026-01-01T00:00:00",
            link="http://x/1",
        )

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_connect_list_view_flow(monkeypatch):
    import wptui.screens.connect as connect_mod

    fake = FakeClient()
    monkeypatch.setattr(connect_mod, "WordPressClient", lambda *a, **k: fake)
    monkeypatch.setattr(connect_mod, "save_profile", lambda *a, **k: None)
    monkeypatch.setattr(connect_mod, "list_profiles", lambda: [])

    from wptui.app import WPTuiApp

    app = WPTuiApp()
    async with app.run_test() as pilot:
        await pilot.pause()  # let on_mount push the connect screen
        # Fill in the connect form (query the active screen, not the base screen).
        app.screen.query_one("#site-url").value = "https://example.com"
        app.screen.query_one("#username").value = "tester"
        app.screen.query_one("#app-password").value = "pass word pass word"
        await pilot.click("#connect")
        await pilot.pause()
        # After connecting, the post list screen should be on top.
        from wptui.screens.post_list import PostListScreen

        assert isinstance(app.screen, PostListScreen)
        table = app.screen.query_one("#post-table")
        assert table.row_count == 2

        # Open the first post in the editor.
        table.move_cursor(row=0)
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()
        from wptui.screens.editor import EditorScreen
        from wptui.widgets.text_block import TextBlockEditor

        assert isinstance(app.screen, EditorScreen)
        editors = list(app.screen.query(TextBlockEditor))
        assert len(editors) == 1
        assert editors[0].query_one("#body").text == "Hi there."

"""Tests for EditorScreen's pre-fill ("pipe import") mode (U3) and the app/__main__-level
wiring that threads piped stdin through conversion and into the connect-to-editor flow
(U4).

The U3 tests exercise the ``import_blocks``/``import_title`` constructor path added to
``EditorScreen`` so it can open with already-built content instead of starting blank or
fetching from the server. The U4 tests (below the U3 ones) cover ``WPTuiApp.pending_import``
and ``wptui.__main__.main()``'s read/convert/reattach wiring.
"""

from __future__ import annotations

import pytest
from textual.widgets import Input

from wptui.api.dto import PostDetail, PostSummary
from wptui.autosave import read_snapshot, write_snapshot
from wptui.blocks import parse
from wptui.widgets.canvas import BlockCanvas
from wptui.widgets.text_block import TextBlockEditor

SAMPLE_CONTENT = "<!-- wp:paragraph -->\n<p>Hello from import.</p>\n<!-- /wp:paragraph -->"


class _FakeConnectClient:
    """Stand-in for WordPressClient with no network (mirrors test_smoke_app.FakeClient)."""

    def __init__(self) -> None:
        self.closed = False

    async def verify(self) -> dict:
        return {"id": 1, "name": "tester"}

    async def list_posts(self, *, search=None, **_kw) -> list[PostSummary]:
        return [PostSummary(1, "Hello World", "publish", "2026-01-01T00:00:00", "http://x/1")]

    async def get_post(self, post_id: int, post_type: str = "post") -> PostDetail:
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


async def _run_connect_flow(pilot, app) -> None:
    """Drive the scripted connect form, mirroring test_smoke_app::test_connect_list_view_flow."""
    await pilot.pause()  # let on_mount push the connect screen
    app.screen.query_one("#site-url").value = "https://example.com"
    app.screen.query_one("#username").value = "tester"
    app.screen.query_one("#app-password").value = "pass word pass word"
    await pilot.click("#connect")
    await pilot.pause()
    await pilot.pause()


class RecordingClient:
    """Minimal fake client that records create_post calls (mirrors test_create_flow.py)."""

    def __init__(self) -> None:
        self.created: list[tuple] = []
        self.updated: list[tuple] = []

    async def get_post(self, pid, post_type="post"):
        raise AssertionError("get_post should never be called for a pre-filled new post")

    async def create_post(self, post_type, *, title_raw="", content_raw="", settings=None):
        self.created.append((post_type, title_raw, content_raw, settings))
        return _detail(123, title_raw, content_raw, post_type)

    async def update_post(
        self, post_id, *, content_raw=None, title_raw=None, settings=None, expected_modified_gmt=None
    ):
        self.updated.append((post_id, content_raw, title_raw, settings, expected_modified_gmt))
        return _detail(post_id, title_raw or "", content_raw or "", "post")

    async def aclose(self):
        pass


def _detail(post_id, title, content, post_type):
    from wptui.api.dto import PostDetail

    return PostDetail(
        id=post_id,
        title_raw=title,
        content_raw=content,
        status="draft",
        modified_gmt="2026-01-02T00:00:00",
        link=f"http://x/{post_id}",
        post_type=post_type,
    )


async def _push_import_editor(pilot, app, *, title=None, content=SAMPLE_CONTENT):
    from wptui.screens.editor import EditorScreen

    blocks = parse(content) if content is not None else []
    app.push_screen(EditorScreen(import_blocks=blocks, import_title=title))
    await pilot.pause()
    await pilot.pause()
    return app.screen


@pytest.mark.asyncio
async def test_prefilled_content_renders_on_mount():
    from wptui.app import WPTuiApp

    app = WPTuiApp()
    app.client = RecordingClient()
    async with app.run_test() as pilot:
        await pilot.pause()
        editor = await _push_import_editor(pilot, app, title="My Title")

        assert editor.query_one("#editor-title", Input).value == "My Title"
        text_editors = list(editor.query(TextBlockEditor))
        assert len(text_editors) == 1
        assert text_editors[0].query_one("#body").text == "Hello from import."

        status = editor.query_one("#editor-status")._Static__content
        assert str(status) == "Imported 1 block(s) · Ctrl+E settings · Ctrl+S to save"


@pytest.mark.asyncio
async def test_ctrl_s_creates_via_normal_new_post_path():
    from wptui.app import WPTuiApp

    client = RecordingClient()
    app = WPTuiApp()
    app.client = client
    async with app.run_test() as pilot:
        await pilot.pause()
        editor = await _push_import_editor(pilot, app, title="My Title")

        await pilot.press("ctrl+s")
        await pilot.pause()
        await pilot.pause()

        # Only the first Ctrl+S creates the post -- no write happened before it (R11).
        assert len(client.created) == 1 and len(client.updated) == 0
        post_type, title, content, settings = client.created[0]
        assert post_type == "post"
        assert title == "My Title"
        assert "Hello from import." in content


@pytest.mark.asyncio
async def test_empty_import_shows_distinct_status_line():
    from wptui.app import WPTuiApp

    app = WPTuiApp()
    app.client = RecordingClient()
    async with app.run_test() as pilot:
        await pilot.pause()
        editor = await _push_import_editor(pilot, app, title=None, content="")

        assert isinstance(editor._canvas, BlockCanvas)
        assert editor._canvas.blocks == []
        status = editor.query_one("#editor-status")._Static__content
        assert str(status) == "Imported 0 block(s) · Ctrl+E settings · Ctrl+S to save"


@pytest.mark.asyncio
async def test_resume_prompt_never_appears_even_with_stale_snapshot():
    from wptui.app import WPTuiApp
    from wptui.screens.editor import EditorScreen

    # An unrelated stale new-post draft for the same ("local") site.
    write_snapshot(
        "local|new|some-earlier-session",
        {
            "title": "Stale draft",
            "content": "<!-- wp:paragraph -->\n<p>Stale.</p>\n<!-- /wp:paragraph -->",
            "settings": {},
            "post_id": None,
            "post_type": "post",
            "modified_gmt": None,
            "site": "local",
            "saved_at": "2020-01-01T00:00:00",
        },
    )

    app = WPTuiApp()
    app.client = RecordingClient()
    async with app.run_test() as pilot:
        await pilot.pause()
        editor = await _push_import_editor(pilot, app, title="My Title")
        await pilot.pause()

        # No ConfirmModal ("resume unsaved draft?") got pushed on top.
        assert isinstance(app.screen, EditorScreen)
        assert app.screen is editor

        # Escape pops straight back off the editor (no modal to dismiss first).
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, EditorScreen)


@pytest.mark.asyncio
async def test_autosave_snapshot_exists_immediately_after_mount():
    from wptui.app import WPTuiApp

    app = WPTuiApp()
    app.client = RecordingClient()
    async with app.run_test() as pilot:
        await pilot.pause()
        editor = await _push_import_editor(pilot, app, title="My Title")

        # No timer tick has fired yet (autosave interval is 2s); the snapshot must already
        # be on disk from the synchronous write in _start_import.
        assert editor._draft_key is not None
        snap = read_snapshot(editor._draft_key)
        assert snap is not None
        assert snap["title"] == "My Title"
        assert "Hello from import." in snap["content"]


@pytest.mark.asyncio
async def test_focus_lands_on_title_when_no_title_provided():
    from wptui.app import WPTuiApp

    app = WPTuiApp()
    app.client = RecordingClient()
    async with app.run_test() as pilot:
        await pilot.pause()
        editor = await _push_import_editor(pilot, app, title=None)
        await pilot.pause()

        assert editor.focused is editor.query_one("#editor-title", Input)


@pytest.mark.asyncio
async def test_focus_lands_on_first_block_when_title_provided():
    from wptui.app import WPTuiApp

    app = WPTuiApp()
    app.client = RecordingClient()
    async with app.run_test() as pilot:
        await pilot.pause()
        editor = await _push_import_editor(pilot, app, title="My Title")
        await pilot.pause()

        first_body = editor.query_one(TextBlockEditor).query_one("#body")
        assert editor.focused is first_body


# --------------------------------------------------------------------------------- U4
# App-level wiring: WPTuiApp.pending_import + on_connect_screen_connected, and
# wptui.__main__.main()'s read/convert/reattach sequence.


@pytest.mark.asyncio
async def test_pending_import_opens_prefilled_editor_on_top_of_post_list(monkeypatch):
    """AE1/AE7: with pending_import set, connecting opens post list then a pre-filled
    editor on top of it -- Escape pops to a live post list, not the connect screen."""
    import wptui.screens.connect as connect_mod

    fake = _FakeConnectClient()
    monkeypatch.setattr(connect_mod, "WordPressClient", lambda *a, **k: fake)
    monkeypatch.setattr(connect_mod, "save_profile", lambda *a, **k: None)
    monkeypatch.setattr(connect_mod, "list_profiles", lambda: [])

    from wptui.app import WPTuiApp
    from wptui.screens.editor import EditorScreen
    from wptui.screens.post_list import PostListScreen

    blocks = parse(SAMPLE_CONTENT)
    app = WPTuiApp()
    app.pending_import = ("Imported Title", blocks)

    async with app.run_test() as pilot:
        await _run_connect_flow(pilot, app)

        # The pre-filled editor is on top, with the post list underneath it.
        assert isinstance(app.screen, EditorScreen)
        assert app.screen.query_one("#editor-title", Input).value == "Imported Title"
        assert isinstance(app.screen_stack[-2], PostListScreen)

        # Covers R10: post type is always "post" regardless of what was piped in.
        assert app.screen._post_type == "post"

        # The pending-import attribute is cleared immediately after it's consumed.
        assert app.pending_import is None

        # Escape pops to a live post list, not back to the connect screen.
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, PostListScreen)


@pytest.mark.asyncio
async def test_no_pending_import_leaves_post_list_on_top(monkeypatch):
    """Regression: an ordinary interactive connect (no pending import) is unchanged --
    the post list is the top screen, and no editor is pushed."""
    import wptui.screens.connect as connect_mod

    fake = _FakeConnectClient()
    monkeypatch.setattr(connect_mod, "WordPressClient", lambda *a, **k: fake)
    monkeypatch.setattr(connect_mod, "save_profile", lambda *a, **k: None)
    monkeypatch.setattr(connect_mod, "list_profiles", lambda: [])

    from wptui.app import WPTuiApp
    from wptui.screens.editor import EditorScreen
    from wptui.screens.post_list import PostListScreen

    app = WPTuiApp()
    assert app.pending_import is None

    async with app.run_test() as pilot:
        await _run_connect_flow(pilot, app)

        assert isinstance(app.screen, PostListScreen)
        assert not any(isinstance(s, EditorScreen) for s in app.screen_stack)
        assert app.pending_import is None


def test_main_conversion_exception_exits_nonzero_without_launching_app(monkeypatch):
    """R16/AE9: a conversion-time exception is caught, reported to stderr, and exits
    nonzero -- WPTuiApp is never constructed."""
    import wptui.__main__ as main_mod

    monkeypatch.setattr(main_mod, "read_piped_input", lambda: "# Title\n\nBody text")

    def _boom(_text: str):
        raise ValueError("boom: malformed input")

    monkeypatch.setattr(main_mod, "convert_markdown", _boom)

    constructed: list[bool] = []

    class _ExplodingApp:
        def __init__(self) -> None:
            constructed.append(True)

        def run(self) -> None:  # pragma: no cover - must never be reached
            raise AssertionError("app.run() should never be called")

    monkeypatch.setattr(main_mod, "WPTuiApp", _ExplodingApp)

    with pytest.raises(SystemExit) as exc_info:
        main_mod.main()

    assert exc_info.value.code != 0
    assert constructed == []


def test_main_reattach_failure_exits_nonzero_without_launching_app(monkeypatch):
    """R3/AE4: reattachment failing (no controlling terminal) prints a clear stderr
    error and exits nonzero -- WPTuiApp is never constructed or run."""
    import wptui.__main__ as main_mod
    from wptui.stdin_import import NoControllingTerminalError

    monkeypatch.setattr(main_mod, "read_piped_input", lambda: "# Title\n\nBody text")
    monkeypatch.setattr(main_mod, "convert_markdown", lambda _text: ("Title", []))

    def _raise() -> None:
        raise NoControllingTerminalError("no controlling terminal available")

    monkeypatch.setattr(main_mod, "reattach_controlling_terminal", _raise)

    constructed: list[bool] = []

    class _ExplodingApp:
        def __init__(self) -> None:
            constructed.append(True)

        def run(self) -> None:  # pragma: no cover - must never be reached
            raise AssertionError("app.run() should never be called")

    monkeypatch.setattr(main_mod, "WPTuiApp", _ExplodingApp)

    with pytest.raises(SystemExit) as exc_info:
        main_mod.main()

    assert exc_info.value.code != 0
    assert constructed == []


def test_main_no_piped_input_skips_conversion_and_reattachment(monkeypatch):
    """Regression: a normal interactive launch (stdin is a tty) never converts anything,
    never attempts reattachment, and runs the app with no pending import set."""
    import wptui.__main__ as main_mod

    monkeypatch.setattr(main_mod, "read_piped_input", lambda: None)

    def _unexpected_convert(_text: str):
        raise AssertionError("convert_markdown should never be called with no piped input")

    def _unexpected_reattach() -> None:
        raise AssertionError(
            "reattach_controlling_terminal should never be called with no piped input"
        )

    monkeypatch.setattr(main_mod, "convert_markdown", _unexpected_convert)
    monkeypatch.setattr(main_mod, "reattach_controlling_terminal", _unexpected_reattach)

    calls: dict[str, object] = {}

    class _FakeApp:
        def __init__(self) -> None:
            calls["constructed"] = True

        def run(self) -> None:
            calls["pending_import"] = getattr(self, "pending_import", "unset")

    monkeypatch.setattr(main_mod, "WPTuiApp", _FakeApp)

    main_mod.main()

    assert calls == {"constructed": True, "pending_import": "unset"}


def test_main_successful_piped_import_sets_pending_import_and_reattaches(monkeypatch):
    """R2/R12: with content piped and converted successfully, main() reattaches the
    terminal, then constructs WPTuiApp with the converted (title, blocks) pair set as
    pending_import before running it."""
    import wptui.__main__ as main_mod

    monkeypatch.setattr(main_mod, "read_piped_input", lambda: "# Title\n\nBody text")
    monkeypatch.setattr(main_mod, "convert_markdown", lambda _text: ("Title", ["sentinel-block"]))

    reattached: list[bool] = []
    monkeypatch.setattr(
        main_mod, "reattach_controlling_terminal", lambda: reattached.append(True)
    )

    calls: dict[str, object] = {}

    class _FakeApp:
        def __init__(self) -> None:
            pass

        def run(self) -> None:
            calls["pending_import"] = self.pending_import

    monkeypatch.setattr(main_mod, "WPTuiApp", _FakeApp)

    main_mod.main()

    assert reattached == [True]
    assert calls["pending_import"] == ("Title", ["sentinel-block"])

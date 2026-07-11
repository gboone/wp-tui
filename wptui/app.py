"""The top-level Textual application."""

from __future__ import annotations

from textual.app import App

from wptui.api import WordPressClient
from wptui.config import SiteProfile
from wptui.screens.connect import ConnectScreen
from wptui.screens.post_list import PostListScreen


class WPTuiApp(App[None]):
    """A terminal UI for editing WordPress posts."""

    TITLE = "wp-tui"
    CSS_PATH = "app.tcss"
    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("f2", "toggle_vim", "Vim mode"),
    ]

    def __init__(self) -> None:
        super().__init__()
        # Set once the user connects; owned by the app so screens can share it.
        self.client: WordPressClient | None = None
        self.profile: SiteProfile | None = None
        # Global Vim keymap toggle; editors consult it on each keypress.
        self.vim_mode: bool = False

    def action_toggle_vim(self) -> None:
        from wptui.widgets.inline_area import InlineMarkdownArea

        self.vim_mode = not self.vim_mode
        for area in self.screen.query(InlineMarkdownArea):
            area.refresh_vim()
        self.notify(f"Vim mode {'on' if self.vim_mode else 'off'}")

    def on_mount(self) -> None:
        self.push_screen(ConnectScreen())

    async def on_connect_screen_connected(self, message: ConnectScreen.Connected) -> None:
        """Handle a successful connection from the connect screen."""
        if self.client is not None and self.client is not message.client:
            # Reconnecting: close the previous client so its socket pool isn't leaked.
            try:
                await self.client.aclose()
            except Exception:
                pass
        self.client = message.client
        self.profile = message.profile
        self.sub_title = message.profile.base_url
        self.push_screen(PostListScreen())

    async def action_quit(self) -> None:  # type: ignore[override]
        if self.client is not None:
            try:
                await self.client.aclose()
            except Exception:
                pass  # never let cleanup failure block the quit
        self.exit()

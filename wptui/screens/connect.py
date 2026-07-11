"""Connect screen: pick a saved profile or enter site credentials."""

from __future__ import annotations

from textual import on, work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Select, Static

from wptui.api import ApiError, WordPressClient
from wptui.config import (
    SiteProfile,
    get_credentials,
    list_profiles,
    save_profile,
)

_NEW_PROFILE = "\x00new"


class ConnectScreen(Screen[None]):
    """Collect a site URL, username, and Application Password, then verify."""

    class Connected(Message):
        """Posted when credentials verify successfully."""

        def __init__(self, client: WordPressClient, profile: SiteProfile) -> None:
            super().__init__()
            self.client = client
            self.profile = profile

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="connect-box"):
            yield Label("Connect to a WordPress site", id="connect-title")
            profiles = list_profiles()
            if profiles:
                options = [(f"{p.name} — {p.base_url}", p.name) for p in profiles]
                options.append(("+ New connection…", _NEW_PROFILE))
                yield Select(
                    options,
                    prompt="Saved connections",
                    value=profiles[0].name,
                    id="profile-select",
                )
            yield Input(placeholder="https://example.com", id="site-url")
            yield Input(placeholder="username", id="username")
            yield Input(
                placeholder="Application Password (xxxx xxxx xxxx xxxx)",
                password=True,
                id="app-password",
            )
            with Horizontal(id="connect-buttons"):
                yield Button("Connect", variant="primary", id="connect")
            yield Static("", id="connect-status")
        yield Footer()

    def on_mount(self) -> None:
        self._apply_selected_profile()
        self.query_one("#site-url", Input).focus()

    @on(Select.Changed, "#profile-select")
    def _on_profile_changed(self, _: Select.Changed) -> None:
        self._apply_selected_profile()

    def _selected_profile(self) -> SiteProfile | None:
        try:
            select = self.query_one("#profile-select", Select)
        except Exception:
            return None
        value = select.value
        if value in (Select.BLANK, _NEW_PROFILE):
            return None
        return next((p for p in list_profiles() if p.name == value), None)

    def _apply_selected_profile(self) -> None:
        profile = self._selected_profile()
        url = self.query_one("#site-url", Input)
        user = self.query_one("#username", Input)
        pw = self.query_one("#app-password", Input)
        if profile is None:
            return
        url.value = profile.base_url
        user.value = profile.username
        stored = get_credentials(profile)
        pw.value = stored or ""

    @on(Button.Pressed, "#connect")
    @on(Input.Submitted)
    def _submit(self, _: object) -> None:
        base_url = self.query_one("#site-url", Input).value.strip()
        username = self.query_one("#username", Input).value.strip()
        app_password = self.query_one("#app-password", Input).value.strip()
        if not (base_url and username and app_password):
            self._set_status("Site URL, username, and password are all required.", error=True)
            return
        if base_url.startswith("http://"):
            # HTTP Basic sends the Application Password in (reversible) base64; refuse to
            # transmit it over an unencrypted channel.
            self._set_status(
                "Refusing to send credentials over plaintext http://. Use https://.",
                error=True,
            )
            return
        if not base_url.startswith("https://"):
            base_url = "https://" + base_url
        profile = SiteProfile(name=base_url, base_url=base_url, username=username)
        self._set_status("Connecting…")
        self._connect(profile, app_password)

    @work(exclusive=True)
    async def _connect(self, profile: SiteProfile, app_password: str) -> None:
        client = WordPressClient(profile, app_password)
        try:
            await client.verify()
        except ApiError as err:
            await client.aclose()
            self._set_status(f"Could not connect: {err}", error=True)
            return
        # Persist for next time (name the profile after the host for now).
        save_profile(profile, app_password)
        self.post_message(self.Connected(client, profile))

    def _set_status(self, text: str, *, error: bool = False) -> None:
        status = self.query_one("#connect-status", Static)
        status.update(text)
        status.set_class(error, "error")

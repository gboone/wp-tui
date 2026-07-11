"""PostSettingsScreen: edit a post/page's core built-in settings.

Pushed over the editor (Ctrl+E) and popped on escape. It mutates the shared
:class:`PostSettings` object in place, so the editor picks up the edits and saves them
with the post. Fields are type-conditional: categories/tags for posts, parent/template/
menu-order for pages.
"""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Select, Static

from wptui.api import PostSettings
from wptui.widgets.term_picker import TermPicker

_STATUS_OPTIONS = [
    ("Draft", "draft"),
    ("Published", "publish"),
    ("Pending review", "pending"),
    ("Private", "private"),
]
_STATUS_VALUES = {value for _label, value in _STATUS_OPTIONS}


class PostSettingsScreen(Screen[None]):
    """A form over one post/page's editable settings."""

    BINDINGS = [("escape", "close", "Done")]

    def __init__(self, settings: PostSettings) -> None:
        super().__init__()
        self._settings = settings

    def compose(self) -> ComposeResult:
        s = self._settings
        is_page = s.post_type == "page"
        yield Header()
        with VerticalScroll(id="settings-form"):
            yield Static(f"{s.post_type.title()} settings", classes="settings-title")

            yield Static("Status", classes="settings-label")
            status = s.status if s.status in _STATUS_VALUES else "draft"
            yield Select(_STATUS_OPTIONS, value=status, allow_blank=False, id="set-status")

            yield Static("Password (optional — protects the post)", classes="settings-label")
            yield Input(value=s.password, password=True, id="set-password")

            yield Static("Slug", classes="settings-label")
            yield Input(value=s.slug, placeholder="(auto from title)", id="set-slug")

            yield Static("Excerpt", classes="settings-label")
            yield Input(value=s.excerpt_raw, id="set-excerpt")

            yield Static("Publish date (ISO 8601, optional)", classes="settings-label")
            yield Input(value=s.date, placeholder="2026-07-11T09:00:00", id="set-date")

            if is_page:
                yield Static("Parent page ID (0 = none)", classes="settings-label")
                yield Input(value=str(s.parent), id="set-parent")
                yield Static("Template", classes="settings-label")
                yield Input(value=s.template, placeholder="(default)", id="set-template")
                yield Static("Menu order", classes="settings-label")
                yield Input(value=str(s.menu_order), id="set-menu-order")
            else:
                yield Static(f"Categories: {len(s.categories)} selected", id="set-categories-label", classes="settings-label")
                yield Button("Edit categories", id="set-categories")
                yield Static(f"Tags: {len(s.tags)} selected", id="set-tags-label", classes="settings-label")
                yield Button("Edit tags", id="set-tags")

            yield Static(self._featured_label(), id="set-featured-label", classes="settings-label")
            yield Button("Set featured image", id="set-featured")
        yield Footer()

    def _featured_label(self) -> str:
        fid = self._settings.featured_media
        return f"Featured image: {'#' + str(fid) if fid else 'none'}"

    @on(Button.Pressed, "#set-categories")
    def _edit_categories(self) -> None:
        self.app.push_screen(
            TermPicker("categories", self._settings.categories), self._categories_chosen
        )

    @on(Button.Pressed, "#set-tags")
    def _edit_tags(self) -> None:
        self.app.push_screen(TermPicker("tags", self._settings.tags), self._tags_chosen)

    def _categories_chosen(self, ids: list[int] | None) -> None:
        if ids is not None:
            self._settings.categories = ids
            self.query_one("#set-categories-label", Static).update(
                f"Categories: {len(ids)} selected"
            )

    def _tags_chosen(self, ids: list[int] | None) -> None:
        if ids is not None:
            self._settings.tags = ids
            self.query_one("#set-tags-label", Static).update(f"Tags: {len(ids)} selected")

    def action_close(self) -> None:
        self._commit()
        self.app.pop_screen()

    def _commit(self) -> None:
        """Write the current field values back into the shared settings object."""
        s = self._settings
        s.status = self.query_one("#set-status", Select).value or s.status  # type: ignore[assignment]
        s.password = self.query_one("#set-password", Input).value
        s.slug = self.query_one("#set-slug", Input).value.strip()
        s.excerpt_raw = self.query_one("#set-excerpt", Input).value
        s.date = self.query_one("#set-date", Input).value.strip()
        if s.post_type == "page":
            s.parent = _as_int(self.query_one("#set-parent", Input).value)
            s.template = self.query_one("#set-template", Input).value.strip()
            s.menu_order = _as_int(self.query_one("#set-menu-order", Input).value)


def _as_int(value: str) -> int:
    try:
        return int(value.strip() or 0)
    except ValueError:
        return 0

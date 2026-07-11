"""A ``TextArea`` that live-styles markdown-style inline markers.

Textual's bundled tree-sitter markdown grammar highlights block structure only — it
does not tag inline ``*emphasis*`` / ``**strong**``. So instead of relying on a
language, this widget computes its own highlight map straight from the headless inline
engine (:func:`wptui.inline.highlight_spans`), the same code that decides how the text
serializes to WordPress HTML. Formatted text renders bold/italic/code/underlined and the
markers stay visible but dimmed — the "fallback" live-styling editor from the plan.
"""

from __future__ import annotations

from rich.style import Style
from textual import events
from textual.message import Message
from textual.widgets import TextArea
from textual.widgets.text_area import TextAreaTheme

from wptui.inline import highlight_spans
from wptui.keys import Mode, VimState, resolve


def _vim_key(event: events.Key) -> str:
    """Normalize a key event into the token the resolver expects.

    Printable characters (case-sensitive, so ``G`` differs from ``g``) come through as
    themselves; named keys like ``escape``/``enter``/``backspace`` use ``event.key``.
    """
    char = event.character
    if char is not None and len(char) == 1 and char.isprintable():
        return char
    return event.key


def _looks_like_url(text: str) -> bool:
    """A single http(s) token — the trigger for paste-over-selection link wrapping."""
    return (
        text.startswith(("http://", "https://"))
        and len(text.split()) == 1
        and "\n" not in text
    )

_THEME_NAME = "wptui-inline"

# Highlight-name -> style. Names match those emitted by ``highlight_spans``.
_SYNTAX_STYLES: dict[str, Style] = {
    "bold": Style(bold=True),
    "italic": Style(italic=True),
    "code": Style(color="cyan"),
    "link": Style(underline=True, color="blue"),
    "marker": Style(dim=True),
}


def _inline_theme() -> TextAreaTheme:
    """A theme based on a built-in one, overriding only the inline syntax styles."""
    base = TextAreaTheme.get_builtin_theme("vscode_dark")
    assert base is not None
    return TextAreaTheme(
        name=_THEME_NAME,
        base_style=base.base_style,
        gutter_style=base.gutter_style,
        cursor_style=base.cursor_style,
        cursor_line_style=base.cursor_line_style,
        selection_style=base.selection_style,
        syntax_styles=dict(_SYNTAX_STYLES),
    )


class InlineMarkdownArea(TextArea):
    """A single-block editor that live-styles inline markdown markers.

    Version-fragile: this overrides Textual internals — ``_build_highlight_map`` (and the
    ``_highlights`` / ``_line_cache`` it populates), ``_on_key``, ``_on_paste``, and
    ``_replace_via_keyboard`` — which are not public API. Verified against Textual 8.2.8;
    the dependency is capped ``<9`` in pyproject. Re-check these seams on any Textual
    minor/major bump.
    """

    class VimCommand(Message):
        """Bubbled to the editor screen when a ``:`` command runs (e.g. ``:w``)."""

        def __init__(self, name: str) -> None:
            self.name = name
            super().__init__()

    def __init__(self, text: str, **kwargs) -> None:
        super().__init__(text, **kwargs)
        self.register_theme(_inline_theme())
        self.theme = _THEME_NAME
        self.show_line_numbers = False
        self._vim = VimState()

    @property
    def _vim_enabled(self) -> bool:
        return bool(getattr(self.app, "vim_mode", False))

    def refresh_vim(self) -> None:
        """React to a global Vim-mode toggle: reset to NORMAL and show the indicator."""
        self._vim = VimState()
        self._update_vim_indicator()

    def _update_vim_indicator(self) -> None:
        if self._vim_enabled:
            self.border_title = self._vim.mode.label
            self.add_class("vim")
        else:
            self.border_title = ""
            self.remove_class("vim")

    async def _on_key(self, event: events.Key) -> None:
        if not self._vim_enabled:
            await super()._on_key(event)
            return
        if self._vim.mode is Mode.INSERT:
            if event.key == "escape":
                event.prevent_default()
                event.stop()
                self._vim.mode = Mode.NORMAL
                self._update_vim_indicator()
                return
            await super()._on_key(event)
            return
        # NORMAL / VISUAL / COMMAND: intercept every key.
        event.prevent_default()
        event.stop()
        visual = self._vim.mode is Mode.VISUAL
        for action in resolve(self._vim, _vim_key(event)):
            self._dispatch_vim(action, select=visual)
        self._update_vim_indicator()

    def _dispatch_vim(self, action: str, *, select: bool) -> None:
        motions = {
            "left": self.action_cursor_left,
            "right": self.action_cursor_right,
            "up": self.action_cursor_up,
            "down": self.action_cursor_down,
            "word_forward": self.action_cursor_word_right,
            "word_backward": self.action_cursor_word_left,
            "line_start": self.action_cursor_line_start,
            "line_end": self.action_cursor_line_end,
        }
        if action in motions:
            motions[action](select=select)
        elif action == "doc_start":
            self.move_cursor((0, 0), select=select)
        elif action == "doc_end":
            self.move_cursor(self.document.end, select=select)
        elif action == "delete_char":
            self.action_delete_right()
        elif action == "delete_line":
            self.action_delete_line()
        elif action == "delete_selection":
            self.action_delete_right()
        elif action == "insert_after":
            self.action_cursor_right()
        elif action == "insert_line_start":
            self.action_cursor_line_start()
        elif action == "insert_line_end":
            self.action_cursor_line_end()
        elif action == "open_below":
            self.action_cursor_line_end()
            self.insert("\n")
        elif action == "open_above":
            self.action_cursor_line_start()
            self.insert("\n")
            self.action_cursor_up()
        elif action in ("save", "quit"):
            self.post_message(self.VimCommand(action))
        # insert_before / to_visual / to_normal / noop: no caret change needed.

    async def _on_paste(self, event: events.Paste) -> None:
        """Pasting a URL over a selection wraps it as a markdown link."""
        selected = self.selected_text
        if not self.read_only and selected and _looks_like_url(event.text.strip()):
            event.stop()
            event.prevent_default()
            replacement = f"[{selected}]({event.text.strip()})"
            result = self._replace_via_keyboard(replacement, *self.selection)
            if result is not None:
                self.move_cursor(result.end_location)
            return
        await super()._on_paste(event)

    def _build_highlight_map(self) -> None:
        """Compute highlights from the inline engine instead of tree-sitter.

        ``TextArea`` stores highlights as ``{line: [(start_byte, end_byte, name)]}`` with
        byte columns within each line, so codepoint span offsets are mapped per line.
        """
        self._line_cache.clear()
        highlights = self._highlights
        highlights.clear()

        text = self.text
        lines = text.split("\n")
        line_starts: list[int] = []
        offset = 0
        for line in lines:
            line_starts.append(offset)
            offset += len(line) + 1  # +1 for the newline separator

        for span_start, span_end, name in highlight_spans(text):
            for line_index, line_start in enumerate(line_starts):
                line = lines[line_index]
                line_end = line_start + len(line)
                start = max(span_start, line_start)
                end = min(span_end, line_end)
                if start >= end:
                    continue
                col_start = start - line_start
                col_end = end - line_start
                byte_start = len(line[:col_start].encode("utf-8"))
                byte_end = len(line[:col_end].encode("utf-8"))
                highlights[line_index].append((byte_start, byte_end, name))

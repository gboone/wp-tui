"""Resolve a keypress in the current Vim mode into semantic editor actions.

``resolve(state, key)`` mutates ``state`` (mode / pending operator / command buffer) and
returns a list of action-name strings the editor widget knows how to dispatch. Motions in
VISUAL mode are the same names — the widget extends the selection instead of moving. The
whole module is pure Python: no widget, no ``textual`` import.
"""

from __future__ import annotations

from wptui.keys.modes import Mode, VimState

# NORMAL/VISUAL single-key motions (shared; VISUAL turns them into selection extensions).
_MOTIONS: dict[str, str] = {
    "h": "left",
    "j": "down",
    "k": "up",
    "l": "right",
    "w": "word_forward",
    "b": "word_backward",
    "0": "line_start",
    "$": "line_end",
    "G": "doc_end",
}

# NORMAL keys that switch into INSERT, paired with how the caret is first positioned.
_INSERT_ENTRIES: dict[str, str] = {
    "i": "insert_before",
    "a": "insert_after",
    "I": "insert_line_start",
    "A": "insert_line_end",
    "o": "open_below",
    "O": "open_above",
}

_COMMANDS: dict[str, list[str]] = {
    "w": ["save"],
    "q": ["quit"],
    "wq": ["save", "quit"],
    "x": ["save", "quit"],
}


def resolve(state: VimState, key: str) -> list[str]:
    """Map ``key`` to actions for ``state.mode``, updating ``state`` in place."""
    if state.mode is Mode.COMMAND:
        return _resolve_command(state, key)
    if state.mode is Mode.VISUAL:
        return _resolve_visual(state, key)
    return _resolve_normal(state, key)


def _resolve_normal(state: VimState, key: str) -> list[str]:
    if state.pending:
        return _resolve_pending(state, key)

    if key in _MOTIONS:
        return [_MOTIONS[key]]
    if key in _INSERT_ENTRIES:
        action = _INSERT_ENTRIES[key]
        state.mode = Mode.INSERT
        return [action]
    if key == "x":
        return ["delete_char"]
    if key == "v":
        state.mode = Mode.VISUAL
        return ["to_visual"]
    if key in ("d", "g"):
        state.pending = key
        return []
    if key == ":":
        state.mode = Mode.COMMAND
        state.command = ""
        return []
    return ["noop"]


def _resolve_pending(state: VimState, key: str) -> list[str]:
    pending, state.pending = state.pending, ""
    if pending == "d" and key == "d":
        return ["delete_line"]
    if pending == "g" and key == "g":
        return ["doc_start"]
    return ["noop"]


def _resolve_visual(state: VimState, key: str) -> list[str]:
    if key == "escape":
        state.mode = Mode.NORMAL
        return ["to_normal"]
    if key in ("d", "x"):
        state.mode = Mode.NORMAL
        return ["delete_selection"]
    if key in _MOTIONS:
        return [_MOTIONS[key]]
    return ["noop"]


def _resolve_command(state: VimState, key: str) -> list[str]:
    if key == "escape":
        state.mode = Mode.NORMAL
        state.command = ""
        return ["to_normal"]
    if key == "enter":
        command = state.command
        state.mode = Mode.NORMAL
        state.command = ""
        return list(_COMMANDS.get(command, ["noop"]))
    if key == "backspace":
        state.command = state.command[:-1]
        return []
    if len(key) == 1 and key.isprintable():
        state.command += key
        return []
    return []

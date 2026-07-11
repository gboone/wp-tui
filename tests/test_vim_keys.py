"""Headless tests for the Vim keymap resolver (no textual import)."""

from __future__ import annotations

from wptui.keys import Mode, VimState, resolve


def test_normal_motions():
    s = VimState()
    assert resolve(s, "h") == ["left"]
    assert resolve(s, "j") == ["down"]
    assert resolve(s, "$") == ["line_end"]
    assert resolve(s, "G") == ["doc_end"]
    assert s.mode is Mode.NORMAL


def test_gg_goes_to_document_start():
    s = VimState()
    assert resolve(s, "g") == []  # pending
    assert s.pending == "g"
    assert resolve(s, "g") == ["doc_start"]
    assert s.pending == ""


def test_dd_deletes_line():
    s = VimState()
    assert resolve(s, "d") == []
    assert resolve(s, "d") == ["delete_line"]


def test_pending_operator_cancels_on_mismatch():
    s = VimState()
    resolve(s, "d")
    assert resolve(s, "j") == ["noop"]
    assert s.pending == ""


def test_insert_entries_switch_mode():
    for key, action in [("i", "insert_before"), ("a", "insert_after"), ("o", "open_below")]:
        s = VimState()
        assert resolve(s, key) == [action]
        assert s.mode is Mode.INSERT


def test_visual_mode_motions_and_delete():
    s = VimState()
    assert resolve(s, "v") == ["to_visual"]
    assert s.mode is Mode.VISUAL
    assert resolve(s, "l") == ["right"]  # extends selection in the widget
    assert resolve(s, "d") == ["delete_selection"]
    assert s.mode is Mode.NORMAL


def test_visual_escape_returns_to_normal():
    s = VimState(mode=Mode.VISUAL)
    assert resolve(s, "escape") == ["to_normal"]
    assert s.mode is Mode.NORMAL


def test_command_line_save_and_quit():
    s = VimState()
    assert resolve(s, ":") == []
    assert s.mode is Mode.COMMAND
    resolve(s, "w")
    resolve(s, "q")
    assert s.command == "wq"
    assert resolve(s, "enter") == ["save", "quit"]
    assert s.mode is Mode.NORMAL
    assert s.command == ""


def test_command_line_backspace_and_escape():
    s = VimState(mode=Mode.COMMAND, command="wq")
    resolve(s, "backspace")
    assert s.command == "w"
    assert resolve(s, "enter") == ["save"]

    s2 = VimState(mode=Mode.COMMAND, command="w")
    assert resolve(s2, "escape") == ["to_normal"]
    assert s2.mode is Mode.NORMAL
    assert s2.command == ""


def test_unknown_command_is_noop():
    s = VimState(mode=Mode.COMMAND, command="zzz")
    assert resolve(s, "enter") == ["noop"]
    assert s.mode is Mode.NORMAL

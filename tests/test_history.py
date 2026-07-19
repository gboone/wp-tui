"""Tests for DocumentHistory (U1)."""

from __future__ import annotations

from wptui.history import DocumentHistory


def test_undo_and_redo_walk_the_stack():
    h = DocumentHistory("A")
    h.record("B")
    h.record("C")
    assert h.undo() == "B"
    assert h.undo() == "A"
    assert h.redo() == "B"
    assert h.redo() == "C"


def test_record_unchanged_is_a_noop():
    h = DocumentHistory("A")
    h.record("A")  # same as current
    assert h.undo() is None  # nothing pushed


def test_new_record_after_undo_clears_redo():
    h = DocumentHistory("A")
    h.record("B")
    assert h.undo() == "A"
    h.record("C")  # a fresh edit
    assert h.redo() is None  # redo future cleared
    assert h.current == "C"


def test_undo_at_oldest_and_redo_at_newest_are_none():
    h = DocumentHistory("A")
    assert h.undo() is None
    h.record("B")
    assert h.redo() is None  # nothing undone yet
    h.undo()
    h.redo()
    assert h.redo() is None  # already at newest


def test_depth_cap_drops_oldest_but_keeps_recent():
    h = DocumentHistory("s0", max_depth=3)
    for i in range(1, 6):  # record s1..s5
        h.record(f"s{i}")
    # only the 3 most recent prior states are retained
    assert h.undo() == "s4"
    assert h.undo() == "s3"
    assert h.undo() == "s2"
    assert h.undo() is None  # s0, s1 dropped


def test_history_is_headless():
    import subprocess
    import sys

    code = "import wptui.history, sys; assert 'textual' not in sys.modules"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

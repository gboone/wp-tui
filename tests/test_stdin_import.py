"""Tests for piped-stdin capture and terminal reattachment (U1)."""

from __future__ import annotations

import io
import os

import pytest

from wptui.stdin_import import (
    NoControllingTerminalError,
    read_piped_input,
    reattach_controlling_terminal,
)


class _FakeStdin(io.StringIO):
    """A stdin stand-in whose isatty() is controllable, unlike a real StringIO."""

    def __init__(self, content: str, *, isatty: bool):
        super().__init__(content)
        self._isatty = isatty

    def isatty(self) -> bool:
        return self._isatty


def test_read_piped_input_returns_none_for_tty(monkeypatch):
    monkeypatch.setattr("sys.stdin", _FakeStdin("", isatty=True))
    assert read_piped_input() is None


def test_read_piped_input_returns_full_content_for_pipe(monkeypatch):
    content = "# Title\n\nSome body text with unicode: café ✅\n"
    monkeypatch.setattr("sys.stdin", _FakeStdin(content, isatty=False))
    assert read_piped_input() == content


@pytest.mark.parametrize("content", ["", "   ", "\n\n\t \n"])
def test_read_piped_input_distinguishes_empty_pipe_from_no_pipe(monkeypatch, content):
    # Piped but empty/whitespace-only must return the (possibly empty) string, not None --
    # None means "nothing was piped at all".
    monkeypatch.setattr("sys.stdin", _FakeStdin(content, isatty=False))
    result = read_piped_input()
    assert result is not None
    assert result == content


def test_reattach_controlling_terminal_success(monkeypatch):
    calls = {}

    def fake_ctermid():
        return "/dev/tty"

    def fake_open(path, flags):
        calls["open"] = (path, flags)
        return 42

    def fake_dup2(fd, target):
        calls["dup2"] = (fd, target)

    def fake_close(fd):
        calls["close"] = fd

    monkeypatch.setattr(os, "ctermid", fake_ctermid, raising=False)
    monkeypatch.setattr(os, "open", fake_open)
    monkeypatch.setattr(os, "dup2", fake_dup2)
    monkeypatch.setattr(os, "close", fake_close)

    reattach_controlling_terminal()

    assert calls["open"] == ("/dev/tty", os.O_RDWR)
    assert calls["dup2"] == (42, 0)
    assert calls["close"] == 42


def test_reattach_controlling_terminal_closes_only_when_not_fd_zero(monkeypatch):
    # If os.open somehow already returned fd 0 (unlikely but possible right after a real
    # dup2 in some environments), don't close fd 0 out from under ourselves.
    monkeypatch.setattr(os, "ctermid", lambda: "/dev/tty", raising=False)
    monkeypatch.setattr(os, "open", lambda path, flags: 0)
    monkeypatch.setattr(os, "dup2", lambda fd, target: None)
    close_calls = []
    monkeypatch.setattr(os, "close", lambda fd: close_calls.append(fd))

    reattach_controlling_terminal()

    assert close_calls == []


def test_reattach_controlling_terminal_raises_dedicated_error_on_oserror(monkeypatch):
    monkeypatch.setattr(os, "ctermid", lambda: "/dev/tty", raising=False)

    def raise_oserror(path, flags):
        raise OSError(6, "Device not configured")  # ENXIO, no controlling terminal

    monkeypatch.setattr(os, "open", raise_oserror)

    with pytest.raises(NoControllingTerminalError) as exc_info:
        reattach_controlling_terminal()

    assert exc_info.value.__cause__ is not None
    assert isinstance(exc_info.value.__cause__, OSError)


def test_reattach_controlling_terminal_raises_when_ctermid_missing(monkeypatch):
    # Simulates a platform (e.g. Windows) that has no os.ctermid() at all -- must raise
    # the same dedicated error type, not an unhandled AttributeError.
    monkeypatch.delattr(os, "ctermid", raising=False)

    with pytest.raises(NoControllingTerminalError) as exc_info:
        reattach_controlling_terminal()

    assert "platform" in str(exc_info.value).lower() or "windows" in str(exc_info.value).lower() or "ctermid" in str(exc_info.value).lower()

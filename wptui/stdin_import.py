"""Capture piped stdin and reattach the process's input to the controlling terminal.

Headless (no ``textual`` import) so this is unit-testable without a real terminal,
mirroring the style of ``wptui/paths.py``. Textual's installed driver reads
``sys.__stdin__.fileno()`` directly, so once stdin has been consumed as a pipe, the
process's file descriptor 0 must be re-pointed at the controlling terminal via
``os.dup2`` before the app is constructed -- reassigning the Python-level ``sys.stdin``
name would have no effect on what the driver actually reads.
"""

from __future__ import annotations

import os
import sys


class NoControllingTerminalError(RuntimeError):
    """Raised when the process's input can't be reattached to a controlling terminal."""


def read_piped_input() -> str | None:
    """Return the full piped stdin content, or ``None`` if stdin is a tty (nothing piped)."""
    if sys.stdin.isatty():
        return None
    return sys.stdin.read()


def reattach_controlling_terminal() -> None:
    """Point file descriptor 0 at the controlling terminal so keyboard input works again.

    Raises ``NoControllingTerminalError`` if there is no controlling terminal to reattach
    to (including on platforms like Windows that have no ``os.ctermid()`` at all).
    """
    try:
        ctermid = os.ctermid
    except AttributeError as exc:
        raise NoControllingTerminalError(
            "No controlling terminal support on this platform (os.ctermid is unavailable, "
            f"e.g. on {sys.platform})"
        ) from exc

    try:
        tty_fd = os.open(ctermid(), os.O_RDWR)
    except OSError as exc:
        raise NoControllingTerminalError(
            "No controlling terminal available to reattach input to"
        ) from exc

    try:
        os.dup2(tty_fd, 0)
    finally:
        if tty_fd != 0:
            os.close(tty_fd)

"""Headless modal (Vim) keymap layer.

Pure key-to-semantic-action resolution, decoupled from any widget so it is unit-testable
without a terminal. The editor widget owns a :class:`VimState` and dispatches the returned
action names onto its ``TextArea``.
"""

from __future__ import annotations

from wptui.keys.modes import Mode, VimState
from wptui.keys.vim import resolve

__all__ = ["Mode", "VimState", "resolve"]

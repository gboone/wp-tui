"""Vim editing modes and the mutable state a single editor tracks."""

from __future__ import annotations

import enum
from dataclasses import dataclass


class Mode(enum.Enum):
    NORMAL = "normal"
    INSERT = "insert"
    VISUAL = "visual"
    COMMAND = "command"

    @property
    def label(self) -> str:
        return f"-- {self.name} --"


@dataclass
class VimState:
    """Per-editor modal state: current mode, a pending operator, and the command buffer."""

    mode: Mode = Mode.NORMAL
    pending: str = ""  # first key of a two-key sequence (e.g. "d" of "dd", "g" of "gg")
    command: str = ""  # accumulated ``:`` command-line text

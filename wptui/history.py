"""Document-level undo/redo over serialized-document snapshots.

A snapshot is the serialized block-grammar string of the whole document. Restoring is done by
re-parsing (by the caller), so history is decoupled from live block-object identity and is
lossless by construction. Standard semantics: recording a new snapshot invalidates the redo
future. Headless — no ``textual`` import.
"""

from __future__ import annotations

_DEFAULT_MAX_DEPTH = 200


class DocumentHistory:
    """Undo/redo stacks over whole-document snapshot strings."""

    def __init__(self, initial: str, max_depth: int = _DEFAULT_MAX_DEPTH) -> None:
        self._current = initial
        self._undo: list[str] = []
        self._redo: list[str] = []
        self._max = max_depth

    @property
    def current(self) -> str:
        return self._current

    def record(self, snapshot: str) -> None:
        """Record a new snapshot. No-op if unchanged; a real change clears the redo future."""
        if snapshot == self._current:
            return
        self._undo.append(self._current)
        if len(self._undo) > self._max:
            self._undo.pop(0)  # bound memory — drop the oldest
        self._current = snapshot
        self._redo.clear()

    def undo(self) -> str | None:
        """Step back to the previous snapshot, or ``None`` at the oldest state."""
        if not self._undo:
            return None
        self._redo.append(self._current)
        self._current = self._undo.pop()
        return self._current

    def redo(self) -> str | None:
        """Re-apply an undone snapshot, or ``None`` when there is nothing to redo."""
        if not self._redo:
            return None
        self._undo.append(self._current)
        self._current = self._redo.pop()
        return self._current

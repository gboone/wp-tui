"""The inline span model.

An :class:`InlineDocument` is a flat, normalized list of :class:`Run` objects. Each
run is a maximal span of text sharing the same set of marks (bold/italic/code) and the
same link target. A flat run-list — not a tree — is unambiguous for the v1 mark set and
serializes to minimal well-nested HTML. Markdown markers and WordPress HTML are just two
serializations of this one model.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field, replace


class Mark(enum.Enum):
    """An inline character-level format that can stack with others on a run."""

    BOLD = "bold"
    ITALIC = "italic"
    CODE = "code"


@dataclass(frozen=True)
class Link:
    """A hyperlink target applied to a run of text."""

    url: str


@dataclass(frozen=True)
class Run:
    """A maximal span of text sharing one style (marks + link).

    A ``raw`` run carries markup the engine does not model (e.g. ``<br>``, ``<sup>``).
    Its ``text`` is verbatim HTML that is re-emitted unescaped on serialization and
    shown as-is in the markdown editor, so unknown inline formatting is never dropped.
    """

    text: str
    marks: frozenset[Mark] = frozenset()
    link: Link | None = None
    raw: bool = False

    def style_key(self) -> tuple[bool, frozenset[Mark], Link | None]:
        """The comparable style identity used to merge adjacent runs."""
        return (self.raw, self.marks, self.link)


@dataclass
class InlineDocument:
    """A normalized flat sequence of styled runs."""

    runs: list[Run] = field(default_factory=list)

    @classmethod
    def from_runs(cls, runs: list[Run]) -> "InlineDocument":
        """Build a document from raw runs, normalizing them."""
        doc = cls(list(runs))
        doc.normalize()
        return doc

    @classmethod
    def plain(cls, text: str) -> "InlineDocument":
        """A document with a single unstyled run (empty if ``text`` is empty)."""
        return cls([Run(text)] if text else [])

    @property
    def text(self) -> str:
        """The concatenated plain text of every run."""
        return "".join(run.text for run in self.runs)

    def normalize(self) -> None:
        """Drop empty runs and merge adjacent runs that share a style."""
        merged: list[Run] = []
        for run in self.runs:
            if not run.text:
                continue
            if merged and merged[-1].style_key() == run.style_key():
                merged[-1] = replace(merged[-1], text=merged[-1].text + run.text)
            else:
                merged.append(run)
        self.runs = merged

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, InlineDocument):
            return NotImplemented
        return self.runs == other.runs

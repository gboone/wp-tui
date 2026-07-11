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


def mark_extents(runs: list[Run]) -> dict[Mark, tuple[int, int]]:
    """First/last run index each mark spans, so wider marks can nest outermost."""
    extents: dict[Mark, tuple[int, int]] = {}
    for index, run in enumerate(runs):
        for mark in run.marks:
            first, _ = extents.get(mark, (index, index))
            extents[mark] = (first, index)
    return extents


def ordered_marks(run: Run, extents: dict[Mark, tuple[int, int]]) -> list[Mark]:
    """A run's marks ordered outermost-first: widest span outer, CODE always innermost.

    Ordering by span (not a fixed BOLD/ITALIC precedence) is what lets both serializers
    nest correctly — e.g. italic spanning a bold sub-span emits with italic outside — so
    HTML and markdown both re-parse to the same document.
    """

    def sort_key(mark: Mark) -> tuple:
        if mark is Mark.CODE:
            return (1, 0, 0, 0)  # innermost; its content is literal
        first, last = extents[mark]
        return (0, first, -last, 0 if mark is Mark.BOLD else 1)

    return sorted(run.marks, key=sort_key)

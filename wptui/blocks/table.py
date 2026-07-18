"""Headless table-cell model for ``core/table`` editing.

A WordPress table is inline HTML (``<figure class="wp-block-table"><table>…</table></figure>``)
with no child blocks. To edit a cell's text without disturbing the table's structure, this
model parses the cell grid out of the block's ``inner_html`` with the stdlib
:mod:`html.parser` (never BeautifulSoup/lxml, which reflow HTML), recording each ``<td>``/``<th>``
cell's **content span**. Serialization rebuilds the HTML verbatim except for edited cells —
so rows/columns, ``thead``/``tbody``/``tfoot``, attributes, ``colspan``/``rowspan`` and the
``figcaption`` are preserved byte-for-byte by construction.

This module MUST NOT import ``textual``.
"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser

from wptui.inline import html_to_document


@dataclass
class _Cell:
    tag: str  # "td" or "th"
    start: int  # content start offset in the source html (just after the opening tag)
    end: int  # content end offset (the offset of the closing tag)


def _line_starts(text: str) -> list[int]:
    starts = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            starts.append(i + 1)
    return starts


class _TableParser(HTMLParser):
    """Records the content span of each top-level ``<td>``/``<th>``, grouped by ``<tr>``."""

    def __init__(self, html: str) -> None:
        super().__init__(convert_charrefs=False)
        self._html = html
        self._line_starts = _line_starts(html)
        self.rows: list[list[_Cell]] = []
        self._table_depth = 0
        self._open: _Cell | None = None
        self.nested = False  # a table nested inside a cell — v1 leaves such tables opaque
        self.malformed = False  # a self-closing <td/>/<th/> — bail to opaque

    def handle_startendtag(self, tag: str, attrs) -> None:
        # Self-closing <td/>/<th/> (invalid HTML WP never emits) would yield an inverted span;
        # flag the table so it stays opaque rather than corrupting on serialize.
        if self._table_depth == 1 and tag in ("td", "th"):
            self.malformed = True

    def _offset(self) -> int:
        line, col = self.getpos()
        return self._line_starts[line - 1] + col

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "table":
            self._table_depth += 1
            if self._table_depth > 1:
                self.nested = True
            return
        if self._table_depth != 1:
            return
        if tag == "tr":
            self.rows.append([])
        elif tag in ("td", "th") and self._open is None and self.rows:
            content_start = self._offset() + len(self.get_starttag_text() or "")
            self._open = _Cell(tag, content_start, content_start)

    def handle_endtag(self, tag: str) -> None:
        if tag == "table":
            self._table_depth -= 1
            return
        if self._table_depth != 1:
            return
        if tag in ("td", "th") and self._open is not None:
            self._open.end = self._offset()
            self.rows[-1].append(self._open)
            self._open = None


class TableModel:
    """A parsed table's cell grid with edit-and-splice serialization."""

    def __init__(self, html: str, rows: list[list[_Cell]], editable: bool) -> None:
        self._html = html
        self._rows = rows
        self.editable = editable
        self._edits: dict[tuple[int, int], str] = {}

    @property
    def shape(self) -> tuple[int, int]:
        """(row count, max column count)."""
        return len(self._rows), max((len(r) for r in self._rows), default=0)

    def row_lengths(self) -> list[int]:
        return [len(r) for r in self._rows]

    def cell(self, row: int, col: int) -> str:
        """The cell's current content (edited value if set, else the parsed HTML)."""
        if (row, col) in self._edits:
            return self._edits[(row, col)]
        c = self._rows[row][col]
        return self._html[c.start : c.end]

    def cell_tag(self, row: int, col: int) -> str:
        return self._rows[row][col].tag

    def set_cell(self, row: int, col: int, content: str) -> None:
        self._edits[(row, col)] = content

    def dirty(self) -> bool:
        """Whether any set cell differs from its original parsed content."""
        return any(
            new != self._html[self._rows[r][c].start : self._rows[r][c].end]
            for (r, c), new in self._edits.items()
        )

    def serialize(self) -> str:
        """Rebuild the html: verbatim everywhere except each edited cell's content span."""
        flat = sorted(
            (cell.start, cell.end, r, c)
            for r, row in enumerate(self._rows)
            for c, cell in enumerate(row)
        )
        parts: list[str] = []
        pos = 0
        for start, end, r, c in flat:
            parts.append(self._html[pos:start])
            parts.append(self._edits.get((r, c), self._html[start:end]))
            pos = end
        parts.append(self._html[pos:])
        return "".join(parts)


def _has_unmodeled_markup(content: str) -> bool:
    """Whether a cell holds inline markup the engine can't round-trip (``<br>``, ``<img>``,
    a ``<span>``…). Editing such a cell would double-escape the markup into literal text, so
    a table containing one is left opaque (preserved, not editable)."""
    return any(run.raw for run in html_to_document(content).runs)


def parse_table(html: str) -> TableModel:
    """Parse a table block's ``inner_html`` into a :class:`TableModel`.

    The table is editable only when it is safe to edit any cell losslessly: not nested, not
    malformed, has cells, all spans well-formed, and no cell carries unmodeled markup.
    """
    parser = _TableParser(html)
    parser.feed(html)
    cells = [cell for row in parser.rows for cell in row]
    editable = (
        not parser.nested
        and not parser.malformed
        and bool(cells)
        and all(cell.end >= cell.start for cell in cells)
        and not any(_has_unmodeled_markup(html[cell.start : cell.end]) for cell in cells)
    )
    return TableModel(html, parser.rows, editable)

"""Parse WordPress inner-HTML into an :class:`InlineDocument`.

Uses the stdlib :mod:`html.parser` (never BeautifulSoup/lxml, which reflow HTML and
threaten the block round-trip). Recognizes the v1 inline formats — ``<strong>``/``<b>``,
``<em>``/``<i>``, ``<code>``, ``<a href>`` — and decodes entities in text. Any other
inline markup is preserved verbatim as a ``raw`` run so nothing is silently dropped.
"""

from __future__ import annotations

from html.parser import HTMLParser

from wptui.inline.model import InlineDocument, Link, Mark, Run

# Tag name -> the mark it toggles on.
_MARK_TAGS: dict[str, Mark] = {
    "strong": Mark.BOLD,
    "b": Mark.BOLD,
    "em": Mark.ITALIC,
    "i": Mark.ITALIC,
    "code": Mark.CODE,
}


class _InlineHTMLParser(HTMLParser):
    """Accumulates styled runs from an inline-HTML fragment."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.runs: list[Run] = []
        self._marks: list[Mark] = []  # active marks as a stack (may contain duplicates)
        self._link: Link | None = None

    # -- current style ----------------------------------------------------

    def _emit(self, text: str, *, raw: bool = False) -> None:
        if not text:
            return
        if raw:
            self.runs.append(Run(text, raw=True))
        else:
            self.runs.append(Run(text, frozenset(self._marks), self._link))

    # -- parser callbacks -------------------------------------------------

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _MARK_TAGS:
            self._marks.append(_MARK_TAGS[tag])
        elif tag == "a":
            href = dict(attrs).get("href") or ""
            self._link = Link(href)
        else:
            self._emit(self.get_starttag_text() or "", raw=True)

    def handle_endtag(self, tag: str) -> None:
        if tag in _MARK_TAGS:
            mark = _MARK_TAGS[tag]
            # Remove the most recent matching mark from the stack.
            for i in range(len(self._marks) - 1, -1, -1):
                if self._marks[i] is mark:
                    del self._marks[i]
                    break
        elif tag == "a":
            self._link = None
        else:
            self._emit(f"</{tag}>", raw=True)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # Void/self-closing inline element (e.g. <br/>): keep verbatim.
        self._emit(self.get_starttag_text() or "", raw=True)

    def handle_data(self, data: str) -> None:
        self._emit(data)


def html_to_document(inner_html: str) -> InlineDocument:
    """Convert a WordPress inner-HTML fragment into a normalized document."""
    parser = _InlineHTMLParser()
    parser.feed(inner_html)
    parser.close()
    return InlineDocument.from_runs(parser.runs)

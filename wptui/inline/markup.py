"""Convert between markdown-style markers and the inline span model.

The markers the user types are the *display* serialization of an
:class:`InlineDocument`; WordPress HTML is the *storage* serialization. This module is
the bridge for the markers:

* ``markdown_to_document`` parses ``*em*``, ``**strong**``, `` `code` ``, ``[text](url)``.
* ``document_to_markdown`` renders a document back to those markers, escaping literal
  marker characters in plain text so the result re-parses to the same document.

Parsing is intentionally forgiving: an unterminated marker is treated as literal text.
"""

from __future__ import annotations

from wptui.inline.model import (
    InlineDocument,
    Link,
    Mark,
    Run,
    mark_extents,
    ordered_marks,
)

# Characters that carry markup meaning and must be backslash-escaped in plain text.
_ESCAPABLE = set("\\`*[]")


# --------------------------------------------------------------------------- parse


def markdown_to_document(text: str) -> InlineDocument:
    """Parse markdown-style markers into a normalized document."""
    return InlineDocument.from_runs(_parse_inline(text, frozenset(), None))


def _parse_inline(s: str, marks: frozenset[Mark], link: Link | None) -> list[Run]:
    runs: list[Run] = []
    buf: list[str] = []
    i = 0

    def flush() -> None:
        if buf:
            runs.append(Run("".join(buf), marks, link))
            buf.clear()

    while i < len(s):
        c = s[i]

        if c == "\\" and i + 1 < len(s) and s[i + 1] in _ESCAPABLE:
            buf.append(s[i + 1])
            i += 2
            continue

        if c == "`":
            close = s.find("`", i + 1)
            if close != -1:
                flush()
                runs.append(Run(s[i + 1 : close], marks | {Mark.CODE}, link))
                i = close + 1
                continue

        elif c == "[" and link is None:
            matched = _match_link(s, i)
            if matched is not None:
                label, url, end = matched
                flush()
                runs.extend(_parse_inline(label, marks, Link(url)))
                i = end
                continue

        elif c == "*":
            if s.startswith("***", i):
                close = _find_close(s, i + 3, "***")
                if close != -1:
                    flush()
                    runs.extend(
                        _parse_inline(
                            s[i + 3 : close], marks | {Mark.BOLD, Mark.ITALIC}, link
                        )
                    )
                    i = close + 3
                    continue
            elif s.startswith("**", i):
                close = _find_close(s, i + 2, "**")
                if close != -1:
                    flush()
                    runs.extend(_parse_inline(s[i + 2 : close], marks | {Mark.BOLD}, link))
                    i = close + 2
                    continue
            else:
                close = _find_italic_close(s, i + 1)
                if close != -1:
                    flush()
                    runs.extend(_parse_inline(s[i + 1 : close], marks | {Mark.ITALIC}, link))
                    i = close + 1
                    continue

        buf.append(c)
        i += 1

    flush()
    return runs


def _find_close(s: str, start: int, marker: str) -> int:
    """Index of the next unescaped ``marker`` at/after ``start``, or -1."""
    i = start
    while i < len(s):
        if s[i] == "\\":
            i += 2
            continue
        if s.startswith(marker, i):
            return i
        i += 1
    return -1


def _find_italic_close(s: str, start: int) -> int:
    """Index of the closing single ``*``, skipping over any nested ``**…**`` span."""
    i = start
    while i < len(s):
        if s[i] == "\\":
            i += 2
            continue
        if s.startswith("**", i):
            nested = s.find("**", i + 2)
            i = i + 2 if nested == -1 else nested + 2
            continue
        if s[i] == "*":
            return i
        i += 1
    return -1


def _match_link(s: str, start: int) -> tuple[str, str, int] | None:
    """Match ``[label](url)`` beginning at ``start``; return (label, url, end) or None."""
    depth = 0
    j = start
    while j < len(s):
        ch = s[j]
        if ch == "\\":
            j += 2
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                break
        j += 1
    if j >= len(s) or s[j] != "]" or j + 1 >= len(s) or s[j + 1] != "(":
        return None
    close = s.find(")", j + 2)
    if close == -1:
        return None
    return s[start + 1 : j], s[j + 2 : close], close + 1


# ----------------------------------------------------------------------- serialize


def highlight_spans(text: str) -> list[tuple[int, int, str]]:
    """Style spans over *raw* markdown ``text`` for live rendering in the editor.

    Returns ``(start, end, name)`` triples in codepoint offsets, where ``name`` is one
    of ``"bold"``, ``"italic"``, ``"code"``, ``"link"`` (content) or ``"marker"`` (the
    dimmed ``*``/`` ` ``/``[]()`` delimiters). Nested formats yield overlapping spans;
    the editor applies them in order so later (marker) spans dim the delimiters on top.
    """
    spans: list[tuple[int, int, str]] = []
    _scan_spans(text, 0, spans)
    return spans


def _scan_spans(s: str, base: int, spans: list[tuple[int, int, str]]) -> None:
    i = 0
    while i < len(s):
        c = s[i]

        if c == "\\" and i + 1 < len(s) and s[i + 1] in _ESCAPABLE:
            spans.append((base + i, base + i + 1, "marker"))
            i += 2
            continue

        if c == "`":
            close = s.find("`", i + 1)
            if close != -1:
                spans.append((base + i, base + i + 1, "marker"))
                spans.append((base + i + 1, base + close, "code"))
                spans.append((base + close, base + close + 1, "marker"))
                i = close + 1
                continue

        elif c == "[":
            matched = _match_link(s, i)
            if matched is not None:
                label, url, end = matched
                label_end = i + 1 + len(label)  # position of ']'
                spans.append((base + i, base + i + 1, "marker"))  # '['
                spans.append((base + i + 1, base + label_end, "link"))
                _scan_spans(label, base + i + 1, spans)
                spans.append((base + label_end, base + label_end + 2, "marker"))  # ']('
                spans.append((base + label_end + 2, base + end - 1, "marker"))  # url
                spans.append((base + end - 1, base + end, "marker"))  # ')'
                i = end
                continue

        elif c == "*":
            if s.startswith("***", i):
                close = _find_close(s, i + 3, "***")
                if close != -1:
                    spans.append((base + i, base + i + 3, "marker"))
                    spans.append((base + i + 3, base + close, "bold"))
                    spans.append((base + i + 3, base + close, "italic"))
                    _scan_spans(s[i + 3 : close], base + i + 3, spans)
                    spans.append((base + close, base + close + 3, "marker"))
                    i = close + 3
                    continue
            elif s.startswith("**", i):
                close = _find_close(s, i + 2, "**")
                if close != -1:
                    spans.append((base + i, base + i + 2, "marker"))
                    spans.append((base + i + 2, base + close, "bold"))
                    _scan_spans(s[i + 2 : close], base + i + 2, spans)
                    spans.append((base + close, base + close + 2, "marker"))
                    i = close + 2
                    continue
            else:
                close = _find_italic_close(s, i + 1)
                if close != -1:
                    spans.append((base + i, base + i + 1, "marker"))
                    spans.append((base + i + 1, base + close, "italic"))
                    _scan_spans(s[i + 1 : close], base + i + 1, spans)
                    spans.append((base + close, base + close + 1, "marker"))
                    i = close + 1
                    continue

        i += 1


_MD_OPEN: dict[Mark, str] = {Mark.BOLD: "**", Mark.ITALIC: "*", Mark.CODE: "`"}


def _md_tokens(run: Run, extents: dict[Mark, tuple[int, int]]) -> list[object]:
    """Ordered open-marker tokens for a run: link, then marks widest-extent-first.

    Ordering marks by span width (widest outermost) makes nesting correct:
    ``<em>a <strong>b</strong> c</em>`` emits ``*a **b** c*`` (not an ambiguous
    ``****``), and a single bold+italic run emits ``***x***``.
    """
    tokens: list[object] = []
    if run.link is not None:
        tokens.append(run.link)
    tokens.extend(ordered_marks(run, extents))
    return tokens


def _md_open(token: object) -> str:
    return "[" if isinstance(token, Link) else _MD_OPEN[token]  # type: ignore[index]


def _md_close(token: object) -> str:
    if isinstance(token, Link):
        return f"]({token.url})"
    return _MD_OPEN[token]  # type: ignore[index]


def document_to_markdown(doc: InlineDocument) -> str:
    """Render ``doc`` to markdown-style marker text.

    Markers are shared across adjacent runs that carry them (via an open-marker stack),
    so a mark spanning several runs emits one marker pair rather than one per run, and
    marks nest by span width so the result re-parses to the same document.
    """
    out: list[str] = []
    stack: list[object] = []
    extents = mark_extents(doc.runs)

    for run in doc.runs:
        wanted: list[object] = [] if run.raw else _md_tokens(run, extents)

        common = 0
        while common < len(stack) and common < len(wanted) and stack[common] == wanted[common]:
            common += 1
        while len(stack) > common:
            out.append(_md_close(stack.pop()))
        for token in wanted[common:]:
            out.append(_md_open(token))
            stack.append(token)

        if run.raw or Mark.CODE in run.marks:
            out.append(run.text)  # raw markup / code-span content is literal
        else:
            out.append(_escape_md(run.text))

    while stack:
        out.append(_md_close(stack.pop()))

    return "".join(out)


def _escape_md(text: str) -> str:
    out: list[str] = []
    for ch in text:
        if ch in _ESCAPABLE:
            out.append("\\")
        out.append(ch)
    return "".join(out)

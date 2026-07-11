"""Serialize an :class:`InlineDocument` back to minimal, well-nested WordPress HTML.

Tags are kept open across adjacent runs that share them (via a small open-tag stack),
so ``bold("a b")`` emits one ``<strong>`` rather than one per run. Marks nest by span
width (link outermost, then wider marks, code innermost) so output is deterministic and
byte-stable across a document -> HTML -> document round-trip.
"""

from __future__ import annotations

from html import escape

from wptui.inline.model import InlineDocument, Link, Mark, Run, mark_extents, ordered_marks

_MARK_TAG: dict[Mark, str] = {Mark.BOLD: "strong", Mark.ITALIC: "em", Mark.CODE: "code"}


def _tokens(run: Run, extents) -> list[object]:
    """The ordered open-tag tokens a run needs: link (outer) then marks widest-first."""
    tokens: list[object] = []
    if run.link is not None:
        tokens.append(run.link)
    tokens.extend(ordered_marks(run, extents))
    return tokens


def _open(token: object) -> str:
    if isinstance(token, Link):
        return f'<a href="{escape(token.url, quote=True)}">'
    return f"<{_MARK_TAG[token]}>"  # type: ignore[index]


def _close(token: object) -> str:
    if isinstance(token, Link):
        return "</a>"
    return f"</{_MARK_TAG[token]}>"  # type: ignore[index]


def document_to_html(doc: InlineDocument) -> str:
    """Render ``doc`` to a WordPress inner-HTML fragment."""
    out: list[str] = []
    stack: list[object] = []
    extents = mark_extents(doc.runs)

    for run in doc.runs:
        wanted: list[object] = [] if run.raw else _tokens(run, extents)

        # Keep the shared prefix of currently-open tags; close the rest (inner-first).
        common = 0
        while common < len(stack) and common < len(wanted) and stack[common] == wanted[common]:
            common += 1
        while len(stack) > common:
            out.append(_close(stack.pop()))

        # Open whatever this run still needs.
        for token in wanted[common:]:
            out.append(_open(token))
            stack.append(token)

        out.append(run.text if run.raw else escape(run.text, quote=False))

    while stack:
        out.append(_close(stack.pop()))

    return "".join(out)

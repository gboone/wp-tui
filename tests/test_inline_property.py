"""Property tests for inline parse/serialize invariants."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from wptui.inline import (
    InlineDocument,
    Link,
    Mark,
    document_to_html,
    document_to_markdown,
    html_to_document,
    markdown_to_document,
)
from wptui.inline.model import Run

# Text that stresses HTML escaping and markdown markers.
_TEXT_ALPHABET = "ab <>&*[]`\\ "
_URL_ALPHABET = "abc/:.?=&-_"

_text = st.text(_TEXT_ALPHABET, min_size=1, max_size=6)
_marks = st.sets(st.sampled_from(list(Mark)))
_link = st.one_of(
    st.none(),
    st.builds(Link, st.text(_URL_ALPHABET, min_size=0, max_size=6)),
)


@st.composite
def _runs(draw):
    marks = frozenset(draw(_marks))
    text = draw(_text)
    if Mark.CODE in marks:
        text = text.replace("`", "")  # code spans cannot hold a backtick in v1
        if not text:
            text = "c"
    return Run(text, marks, draw(_link))


@given(st.lists(_runs(), min_size=0, max_size=6))
def test_html_roundtrip_preserves_document(runs):
    """The storage round-trip that actually protects WP content: doc -> HTML -> doc."""
    doc = InlineDocument.from_runs(runs)
    assert html_to_document(document_to_html(doc)) == doc


# ---- Markdown fixed-point over well-formed, space-separated markdown -----------

_word = st.text("abcXYZ", min_size=1, max_size=5)
_url = st.text(_URL_ALPHABET, min_size=1, max_size=6)


@st.composite
def _markdown(draw):
    def segment():
        word = draw(_word)
        kind = draw(st.sampled_from(["plain", "b", "i", "code", "link"]))
        if kind == "plain":
            return word
        if kind == "b":
            return f"**{word}**"
        if kind == "i":
            return f"*{word}*"
        if kind == "code":
            return f"`{word}`"
        return f"[{word}]({draw(_url)})"

    n = draw(st.integers(min_value=0, max_value=5))
    return " ".join(segment() for _ in range(n))


@given(_markdown())
def test_markdown_is_a_fixed_point(md):
    """Parsing then re-serializing well-formed markdown is stable."""
    doc = markdown_to_document(md)
    once = document_to_markdown(doc)
    # Re-serializing what we produced must reproduce itself exactly.
    assert document_to_markdown(markdown_to_document(once)) == once

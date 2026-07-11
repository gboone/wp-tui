"""Headless tests for the inline-formatting engine (no textual import)."""

from __future__ import annotations

import pytest

from wptui.inline import (
    InlineDocument,
    Link,
    Mark,
    document_to_html,
    document_to_markdown,
    highlight_spans,
    html_to_document,
    markdown_to_document,
)
from wptui.inline.model import Run


# --------------------------------------------------------------------------- HTML


def test_html_parse_basic_marks():
    doc = html_to_document("Hi <strong>bold</strong> and <em>em</em> and <code>c</code>.")
    assert doc.text == "Hi bold and em and c."
    assert doc.runs == [
        Run("Hi ", frozenset()),
        Run("bold", frozenset({Mark.BOLD})),
        Run(" and ", frozenset()),
        Run("em", frozenset({Mark.ITALIC})),
        Run(" and ", frozenset()),
        Run("c", frozenset({Mark.CODE})),
        Run(".", frozenset()),
    ]


def test_html_parse_link():
    doc = html_to_document('see <a href="https://x.io">the site</a> now')
    assert doc.runs[1] == Run("the site", frozenset(), Link("https://x.io"))


def test_html_parse_nested_marks():
    doc = html_to_document("<strong>bold <em>both</em></strong>")
    assert doc.runs == [
        Run("bold ", frozenset({Mark.BOLD})),
        Run("both", frozenset({Mark.BOLD, Mark.ITALIC})),
    ]


def test_html_serialize_shares_tags_across_runs():
    doc = InlineDocument.from_runs(
        [
            Run("bold ", frozenset({Mark.BOLD})),
            Run("both", frozenset({Mark.BOLD, Mark.ITALIC})),
        ]
    )
    assert document_to_html(doc) == "<strong>bold <em>both</em></strong>"


def test_html_serialize_escapes_text_and_url():
    doc = InlineDocument.from_runs([Run("a < b & c", frozenset())])
    assert document_to_html(doc) == "a &lt; b &amp; c"
    linked = InlineDocument.from_runs([Run("x", frozenset(), Link('h?a=1&b="2"'))])
    assert document_to_html(linked) == '<a href="h?a=1&amp;b=&quot;2&quot;">x</a>'


def test_html_roundtrip_stable():
    html = 'A <strong>b</strong> <em>c</em> <a href="https://x">L</a> <code>k</code>.'
    doc = html_to_document(html)
    assert document_to_html(doc) == html


def test_unknown_inline_tag_preserved_as_raw():
    doc = html_to_document("line<br>break <sup>2</sup>")
    assert document_to_html(doc) == "line<br>break <sup>2</sup>"
    # Raw runs survive markdown round-tripping too.
    assert document_to_markdown(doc) == "line<br>break <sup>2</sup>"


# ----------------------------------------------------------------------- markdown


def test_markdown_parse_bold_italic_code():
    doc = markdown_to_document("a **b** c *d* e `f`")
    assert doc.runs == [
        Run("a ", frozenset()),
        Run("b", frozenset({Mark.BOLD})),
        Run(" c ", frozenset()),
        Run("d", frozenset({Mark.ITALIC})),
        Run(" e ", frozenset()),
        Run("f", frozenset({Mark.CODE})),
    ]


def test_markdown_parse_link():
    doc = markdown_to_document("see [the site](https://x.io) now")
    assert doc.runs[1] == Run("the site", frozenset(), Link("https://x.io"))


def test_markdown_parse_link_with_bold_label():
    doc = markdown_to_document("[**bold link**](https://x.io)")
    assert doc.runs == [Run("bold link", frozenset({Mark.BOLD}), Link("https://x.io"))]


def test_markdown_bold_to_wp_html():
    """The Phase 3 milestone: **bold** -> <strong>."""
    doc = markdown_to_document("**bold**")
    assert document_to_html(doc) == "<strong>bold</strong>"


def test_markdown_unterminated_marker_is_literal():
    doc = markdown_to_document("a * b and [x](y")
    assert doc.text == "a * b and [x](y"
    assert all(run.marks == frozenset() and run.link is None for run in doc.runs)


def test_markdown_escape_literal_markers():
    doc = markdown_to_document(r"literal \* and \` and \[")
    assert doc.text == "literal * and ` and ["
    assert document_to_markdown(doc) == r"literal \* and \` and \["


def test_markdown_roundtrip_idempotent():
    for md in [
        "plain text",
        "a **b** c",
        "*i* and **b** and `code`",
        "[link](https://example.com/path)",
        "[**bold**](https://x)",
        r"escape \* star",
        "**a *b* c**",  # bold-outer nesting round-trips exactly
    ]:
        doc = markdown_to_document(md)
        assert document_to_markdown(doc) == md, md


def test_markdown_shares_marker_across_adjacent_runs():
    """A mark spanning several runs emits one marker pair, not one per run."""
    doc = InlineDocument.from_runs(
        [
            Run("a ", frozenset({Mark.BOLD})),
            Run("b", frozenset({Mark.BOLD, Mark.ITALIC})),
            Run(" c", frozenset({Mark.BOLD})),
        ]
    )
    assert document_to_markdown(doc) == "**a *b* c**"


# --------------------------------------------------------------------- highlights


def _named(text, spans, name):
    return [text[s:e] for s, e, n in spans if n == name]


def test_highlight_spans_bold():
    text = "a **b** c"
    spans = highlight_spans(text)
    assert _named(text, spans, "bold") == ["b"]
    assert _named(text, spans, "marker") == ["**", "**"]


def test_highlight_spans_all_formats():
    text = "*i* `c` [L](u)"
    spans = highlight_spans(text)
    assert _named(text, spans, "italic") == ["i"]
    assert _named(text, spans, "code") == ["c"]
    assert _named(text, spans, "link") == ["L"]
    # markers cover the italic '*'s, the code backticks, and the link punctuation/url.
    assert "**" not in _named(text, spans, "marker")
    assert "](" in _named(text, spans, "marker")


def test_highlight_spans_nested():
    text = "**a *b* c**"
    spans = highlight_spans(text)
    assert _named(text, spans, "bold") == ["a *b* c"]
    assert _named(text, spans, "italic") == ["b"]
    # Highlighting agrees with parsing on the same span (canonical bold-outer nesting).
    assert document_to_markdown(markdown_to_document(text)) == text


def test_full_bridge_markdown_to_wp_html_to_markdown():
    md = "Intro **strong** then *em* then `code` then [link](https://x.io)."
    doc = markdown_to_document(md)
    html = document_to_html(doc)
    assert html == (
        "Intro <strong>strong</strong> then <em>em</em> then "
        '<code>code</code> then <a href="https://x.io">link</a>.'
    )
    assert document_to_markdown(html_to_document(html)) == md

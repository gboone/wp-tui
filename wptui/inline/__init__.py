"""Headless inline-formatting engine.

A flat span model (``Run``/``Mark``/``Link``) with bidirectional conversion to:

* WordPress inner-HTML formats (``<em>``/``<strong>``/``<code>``/``<a>``), and
* the markdown-style markers the user types (``*em*``, ``**strong**``, `` `code` ``,
  ``[text](url)``).

This package MUST NOT import ``textual``: it is a pure library so inline-conversion
correctness is testable in CI without a terminal.
"""

from __future__ import annotations

from wptui.inline.html_parse import html_to_document
from wptui.inline.html_serialize import document_to_html
from wptui.inline.markup import (
    document_to_markdown,
    highlight_spans,
    markdown_to_document,
)
from wptui.inline.model import InlineDocument, Link, Mark, Run


def markdown_to_html(markdown: str) -> str:
    """Convert user-facing markdown text to WordPress inner-HTML."""
    return document_to_html(markdown_to_document(markdown))


def html_to_markdown(html: str) -> str:
    """Convert WordPress inner-HTML to the markdown text the editor displays."""
    return document_to_markdown(html_to_document(html))


__all__ = [
    "InlineDocument",
    "Link",
    "Mark",
    "Run",
    "html_to_document",
    "document_to_html",
    "markdown_to_document",
    "document_to_markdown",
    "markdown_to_html",
    "html_to_markdown",
    "highlight_spans",
]

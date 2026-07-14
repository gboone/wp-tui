"""Convert a markdown document into WordPress block-comment HTML plus a title.

Parses the input with ``markdown-it-py`` into a :class:`~markdown_it.tree.SyntaxTreeNode`
tree, walks its top-level (block-level) children, and renders each one to the exact
block-comment HTML text WordPress itself produces (paragraph, heading with a ``level``
attribute, list with nested list-item children, quote wrapping a nested paragraph,
code) — then hands the concatenated text to :func:`wptui.blocks.parse` so this module
inherits the parser's existing nesting/interleaving correctness rather than building the
block tree directly.

Each leaf's inline content is walked node-by-node (not taken as a single raw string):
``image`` children are dropped entirely and the remaining text/emphasis/code-span/link
children are reassembled into a markdown-style string, then converted via
``document_to_html(markdown_to_document(text))`` (:mod:`wptui.inline`) — the same call
the hand-typed editing path already makes. This is what keeps a dropped image from
surfacing as a stray literal link: handing an image-containing leaf's whole raw text to
``wptui.inline`` unmodified would have its hand-rolled parser read ``!`` as literal text
followed by an ordinary ``[alt](url)`` link.

A leading, single, top-level level-1 heading is stripped and returned as a plain-text
title (formatting fully discarded — the title lands in a plain ``Input`` widget, never
the HTML-embedding path). Any other heading — a second top-level H1, or one nested
inside a blockquote/list — is never a title candidate, because only the tree's very
first top-level child is ever inspected for this.

This module MUST NOT import ``textual``: it is a pure library, consumed headlessly by
tests and by the app-wiring unit that owns the piped-stdin flow.
"""

from __future__ import annotations

import re
from html import escape

from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode

from wptui.blocks.factory import BLOCK_SEPARATOR
from wptui.blocks.grammar import parse
from wptui.blocks.model import Block
from wptui.inline import document_to_html, markdown_to_document
from wptui.inline.markup import _ESCAPABLE, _escape_md as _escape_plain, _fence_code

_md = MarkdownIt("commonmark")


def convert_markdown(markdown_text: str) -> tuple[str, list[Block]]:
    """Convert ``markdown_text`` into ``(title, blocks)``.

    ``title`` is plain text extracted from a qualifying leading H1 (``""`` if none).
    ``blocks`` is the result of feeding the rendered block-comment HTML through
    :func:`wptui.blocks.parse` — freshly parsed, so every block starts ``dirty=False``
    and re-serializes byte-for-byte via :func:`wptui.blocks.serialize`.

    Any exception raised while parsing or rendering propagates to the caller.
    """
    tokens = _md.parse(markdown_text)
    tree = SyntaxTreeNode(tokens)
    source_lines = markdown_text.splitlines()

    children = list(tree.children)
    title = ""
    if children and _is_title_candidate(children[0]):
        heading = children.pop(0)
        title = _heading_plain_text(heading)

    rendered = [_render_block(node, source_lines) for node in children]
    html_text = BLOCK_SEPARATOR.join(rendered)
    return title, parse(html_text)


def _is_title_candidate(node: SyntaxTreeNode) -> bool:
    """A heading is a title candidate only when it is level 1 (h1)."""
    return node.type == "heading" and node.tag == "h1"


def _heading_plain_text(node: SyntaxTreeNode) -> str:
    inline_node = node.children[0] if node.children else None
    if inline_node is None:
        return ""
    return _plain_text(inline_node.children).strip()


# --------------------------------------------------------------------- plain text


def _plain_text(children: list[SyntaxTreeNode]) -> str:
    """Render inline children to plain text: all formatting and images discarded.

    Used only for title extraction — the title is a plain ``Input`` field, not an HTML
    renderer, so it must never see markdown markers or HTML tags.
    """
    parts: list[str] = []
    for child in children:
        if child.type == "image":
            continue
        if child.type in ("text", "code_inline"):
            parts.append(child.content)
        elif child.type in ("softbreak", "hardbreak"):
            parts.append(" ")
        elif child.children:
            parts.append(_plain_text(child.children))
    return "".join(parts)


# ------------------------------------------------------------------- block render


def _render_block(node: SyntaxTreeNode, source_lines: list[str]) -> str:
    if node.type == "heading":
        return _render_heading(node)
    if node.type == "paragraph":
        return _render_paragraph(node)
    if node.type == "blockquote":
        return _render_quote(node, source_lines)
    if node.type in ("bullet_list", "ordered_list"):
        return _render_list(node, source_lines)
    if node.type in ("fence", "code_block"):
        return _render_code(node)
    return _render_fallback(node, source_lines)


def _render_heading(node: SyntaxTreeNode) -> str:
    level = int(node.tag[1:])
    body = _leaf_html(node)
    return (
        f'<!-- wp:heading {{"level":{level}}} -->\n'
        f'<h{level} class="wp-block-heading">{body}</h{level}>\n'
        "<!-- /wp:heading -->"
    )


def _render_paragraph(node: SyntaxTreeNode) -> str:
    body = _leaf_html(node)
    return f"<!-- wp:paragraph -->\n<p>{body}</p>\n<!-- /wp:paragraph -->"


def _render_quote(node: SyntaxTreeNode, source_lines: list[str]) -> str:
    inner = BLOCK_SEPARATOR.join(_render_block(c, source_lines) for c in node.children)
    return (
        "<!-- wp:quote -->\n"
        f'<blockquote class="wp-block-quote">{inner}</blockquote>\n'
        "<!-- /wp:quote -->"
    )


def _render_code(node: SyntaxTreeNode) -> str:
    code_text = node.content
    if code_text.endswith("\n"):
        code_text = code_text[:-1]
    escaped = escape(code_text, quote=False)
    return (
        "<!-- wp:code -->\n"
        f"<pre class=\"wp-block-code\"><code>{escaped}</code></pre>\n"
        "<!-- /wp:code -->"
    )


def _render_list(node: SyntaxTreeNode, source_lines: list[str]) -> str:
    ordered = node.type == "ordered_list"
    tag = "ol" if ordered else "ul"
    attrs = ' {"ordered":true}' if ordered else ""
    items = BLOCK_SEPARATOR.join(_render_list_item(item, source_lines) for item in node.children)
    return (
        f"<!-- wp:list{attrs} -->\n"
        f'<{tag} class="wp-block-list">{items}</{tag}>\n'
        "<!-- /wp:list -->"
    )


def _render_list_item(node: SyntaxTreeNode, source_lines: list[str]) -> str:
    # WordPress renders a tight list item's own text directly inside <li> (no nested
    # wp:paragraph/<p>), then splices a nested sub-list block in before the closing
    # </li> when the item contains one.
    body_parts: list[str] = []
    nested_parts: list[str] = []
    for child in node.children:
        if child.type in ("bullet_list", "ordered_list"):
            nested_parts.append(_render_block(child, source_lines))
        elif child.type == "paragraph":
            body_parts.append(_leaf_html(child))
        else:
            nested_parts.append(_render_block(child, source_lines))
    body = "".join(body_parts)
    nested = "".join(nested_parts)
    return f"<!-- wp:list-item -->\n<li>{body}{nested}</li>\n<!-- /wp:list-item -->"


def _render_fallback(node: SyntaxTreeNode, source_lines: list[str]) -> str:
    """Any block-level construct with no explicit mapping becomes a plain paragraph
    of its raw source text (R7) — raw HTML blocks, thematic breaks, GFM table syntax
    the base CommonMark parser doesn't recognize (it already falls through as a
    `paragraph` node handled above, so this path is only unmapped node *types*)."""
    text = node.content
    if not text and node.map:
        start, end = node.map
        text = "\n".join(source_lines[start:end])
    text = text.rstrip("\n")
    body = document_to_html(markdown_to_document(_escape_plain(text)))
    return f"<!-- wp:paragraph -->\n<p>{body}</p>\n<!-- /wp:paragraph -->"


# ------------------------------------------------------------------ inline render


def _leaf_html(node: SyntaxTreeNode) -> str:
    """Render a block node's inline content through the existing inline converter."""
    inline_node = node.children[0] if node.children else None
    if inline_node is None:
        return ""
    text = _reassemble(inline_node.children)
    return document_to_html(markdown_to_document(text))


def _reassemble(children: list[SyntaxTreeNode]) -> str:
    """Reassemble inline children into markdown-style text for wptui.inline to parse.

    ``image`` children are skipped entirely (R6) rather than left in place — leaving
    them would have wptui.inline's parser read ``!`` as literal text followed by an
    ordinary ``[alt](url)`` link, producing a stray clickable link.
    """
    had_image = any(child.type == "image" for child in children)
    text = "".join(_render_inline_node(child) for child in children)
    if had_image:
        # A dropped image leaves no placeholder, so whitespace that used to flank it
        # collapses into a run (or, at an edge, a stray leading/trailing space) --
        # clean that artifact up without touching genuine content.
        text = re.sub(r" {2,}", " ", text).strip()
    return text


def _render_inline_node(node: SyntaxTreeNode) -> str:
    if node.type == "image":
        return ""
    if node.type == "text":
        return _escape_plain(node.content)
    if node.type == "code_inline":
        return _fence_code(node.content)
    if node.type in ("softbreak",):
        return " "
    if node.type == "hardbreak":
        return " "
    if node.type == "link":
        url = node.attrs.get("href") or ""
        label = _reassemble(node.children)
        return f"[{label}]({url})"
    if node.type in ("em", "strong"):
        return _render_emphasis(node)
    if node.children:
        return _reassemble(node.children)
    return _escape_plain(node.content or "")


def _render_emphasis(node: SyntaxTreeNode) -> str:
    inner = _reassemble(node.children)
    markup = node.markup or ""
    if markup.startswith("_"):
        # CommonMark underscore emphasis: wptui.inline's parser doesn't recognize
        # `_em_`/`__strong__` (only `*`/`**`/`***`, matching hand-typed content), so it
        # must pass through as literal underscored text, not be upgraded to real
        # formatting just because markdown-it recognized it as emphasis (R5).
        return f"{markup}{inner}{markup}"
    wrapper = "*" if node.type == "em" else "**"
    return f"{wrapper}{inner}{wrapper}"



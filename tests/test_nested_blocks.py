"""Headless tests: editing a nested child dirties ancestors and re-serializes correctly."""

from __future__ import annotations

from wptui.blocks import parse, propagate_dirty, serialize
from wptui.blocks.text import get_editable_body, set_editable_body

LIST_DOC = (
    "<!-- wp:list -->\n<ul>"
    "<!-- wp:list-item --><li>one</li><!-- /wp:list-item -->\n"
    "<!-- wp:list-item --><li>two</li><!-- /wp:list-item -->"
    "</ul>\n<!-- /wp:list -->"
)

QUOTE_DOC = (
    "<!-- wp:quote -->\n"
    '<blockquote class="wp-block-quote">'
    "<!-- wp:paragraph --><p>Quoted line.</p><!-- /wp:paragraph -->"
    "<cite>Someone</cite></blockquote>\n"
    "<!-- /wp:quote -->"
)


def test_list_roundtrips_clean():
    assert serialize(parse(LIST_DOC)) == LIST_DOC


def test_editing_list_item_rebuilds_only_the_list():
    blocks = parse(LIST_DOC)
    wp_list = blocks[0]
    item_one = wp_list.inner_blocks[0]
    assert get_editable_body(item_one) == "one"

    set_editable_body(item_one, "uno")
    # Before propagation the parent is still clean and would drop the edit.
    assert wp_list.dirty is False
    propagate_dirty(blocks)
    assert wp_list.dirty is True

    out = serialize(blocks)
    assert "<li>uno</li>" in out
    # The untouched sibling and the <ul> wrapper survive verbatim.
    assert "<!-- wp:list-item --><li>two</li><!-- /wp:list-item -->" in out
    assert out.startswith("<!-- wp:list -->\n<ul>")
    assert out.endswith("</ul>\n<!-- /wp:list -->")


def test_quote_roundtrips_and_edits_inner_paragraph():
    assert serialize(parse(QUOTE_DOC)) == QUOTE_DOC

    blocks = parse(QUOTE_DOC)
    quote = blocks[0]
    paragraph = quote.inner_blocks[0]
    assert get_editable_body(paragraph) == "Quoted line."

    set_editable_body(paragraph, "Edited quote.")
    propagate_dirty(blocks)

    out = serialize(blocks)
    assert "<p>Edited quote.</p>" in out
    # The <cite> and blockquote wrapper are preserved (they are not blocks).
    assert "<cite>Someone</cite>" in out
    assert '<blockquote class="wp-block-quote">' in out

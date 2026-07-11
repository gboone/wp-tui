"""Round-trip and structural tests for the block grammar library."""

from __future__ import annotations

from pathlib import Path

import pytest

from wptui.blocks import Block, parse, serialize, serialize_block

FIXTURE_DIR = Path(__file__).parent / "fixtures"
FIXTURES = sorted(FIXTURE_DIR.glob("*.html"))


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.name)
def test_roundtrip_is_byte_identical(path: Path) -> None:
    """serialize(parse(x)) == x, byte-for-byte, when nothing is edited."""
    original = path.read_text(encoding="utf-8")
    assert serialize(parse(original)) == original


# -- targeted structural cases ---------------------------------------------

SIMPLE_PARAGRAPH = "<!-- wp:paragraph -->\n<p>Hi.</p>\n<!-- /wp:paragraph -->"


def test_parses_top_level_paragraph() -> None:
    blocks = [b for b in parse(SIMPLE_PARAGRAPH) if not b.is_freeform]
    assert len(blocks) == 1
    para = blocks[0]
    assert para.block_name == "core/paragraph"
    assert para.inner_html == "\n<p>Hi.</p>\n"
    assert para.is_editable


def test_core_namespace_is_normalized_but_serialized_short() -> None:
    (para,) = [b for b in parse(SIMPLE_PARAGRAPH) if not b.is_freeform]
    assert para.block_name == "core/paragraph"  # normalized full name
    para.dirty = True  # force a rebuild instead of verbatim re-emit
    assert serialize_block(para) == SIMPLE_PARAGRAPH  # delimiter stays short


def test_attributes_parsed() -> None:
    src = '<!-- wp:heading {"level":3} -->\n<h3>X</h3>\n<!-- /wp:heading -->'
    (heading,) = [b for b in parse(src) if not b.is_freeform]
    assert heading.attributes == {"level": 3}


def test_nested_attributes_do_not_break_parsing() -> None:
    src = (
        '<!-- wp:acme/w {"config":{"nested":{"deep":true},"n":3}} -->\n'
        "<div>hi</div>\n"
        "<!-- /wp:acme/w -->"
    )
    (block,) = [b for b in parse(src) if not b.is_freeform]
    assert block.block_name == "acme/w"
    assert block.attributes == {"config": {"nested": {"deep": True}, "n": 3}}


def test_void_block() -> None:
    src = '<!-- wp:spacer {"height":"40px"} /-->'
    (block,) = [b for b in parse(src) if not b.is_freeform]
    assert block.block_name == "core/spacer"
    assert block.inner_html == ""
    assert block.original_raw == src


def test_nested_blocks_attached_to_parent() -> None:
    src = (
        "<!-- wp:quote -->\n<blockquote><!-- wp:paragraph -->\n"
        "<p>Inner.</p>\n<!-- /wp:paragraph --></blockquote>\n<!-- /wp:quote -->"
    )
    (quote,) = [b for b in parse(src) if not b.is_freeform]
    assert quote.block_name == "core/quote"
    assert len(quote.inner_blocks) == 1
    assert quote.inner_blocks[0].block_name == "core/paragraph"
    # inner_content interleaves html chunks and a None placeholder for the child.
    assert None in quote.inner_content


def test_editing_one_block_leaves_siblings_byte_identical() -> None:
    """Only the edited block's bytes change on save; opaque siblings are verbatim."""
    src = (
        "<!-- wp:paragraph -->\n<p>Edit me.</p>\n<!-- /wp:paragraph -->\n\n"
        '<!-- wp:table -->\n<figure class="wp-block-table"><table><tbody>'
        "<tr><td>keep</td></tr></tbody></table></figure>\n<!-- /wp:table -->"
    )
    blocks = parse(src)
    # Edit the paragraph by rebuilding its inner html.
    para = next(b for b in blocks if b.block_name == "core/paragraph")
    para.inner_html = "\n<p>Edited!</p>\n"
    para.inner_content = ["\n<p>Edited!</p>\n"]
    para.mark_dirty()

    out = serialize(blocks)
    assert "<p>Edited!</p>" in out
    assert "<p>Edit me.</p>" not in out
    # The opaque table block is untouched, byte-for-byte.
    assert (
        '<!-- wp:table -->\n<figure class="wp-block-table"><table><tbody>'
        "<tr><td>keep</td></tr></tbody></table></figure>\n<!-- /wp:table -->" in out
    )


def test_freeform_content_preserved() -> None:
    src = "<p>Just classic HTML, no blocks.</p>\n"
    blocks = parse(src)
    assert all(b.is_freeform for b in blocks)
    assert serialize(blocks) == src


def test_empty_document() -> None:
    assert parse("") == []
    assert serialize([]) == ""

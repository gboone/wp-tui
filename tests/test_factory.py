"""Tests for the block factories used by the slash-command block-type switcher (U1)."""

from __future__ import annotations

from wptui.blocks import parse, serialize
from wptui.blocks.factory import (
    new_code_block,
    new_heading_block,
    new_list_block,
    new_paragraph_block,
    new_preformatted_block,
    new_quote_block,
    new_separator_block,
    set_heading_level,
)
from wptui.blocks.text import set_editable_body
from wptui.blocks.model import EDITABLE_BLOCKS
from wptui.blocks.text import get_editable_body


def _roundtrips(block) -> bool:
    """A minted block survives a parse -> serialize -> parse -> serialize cycle."""
    once = serialize([block])
    return serialize(parse(once)) == once


# --------------------------------------------------------------------- exact bytes


def test_heading_h2_omits_level_attribute():
    out = serialize([new_heading_block(2)])
    assert out == (
        '<!-- wp:heading -->\n<h2 class="wp-block-heading"></h2>\n<!-- /wp:heading -->'
    )
    assert _roundtrips(new_heading_block(2))


def test_heading_h3_includes_level_attribute():
    out = serialize([new_heading_block(3)])
    assert out == (
        '<!-- wp:heading {"level":3} -->\n'
        '<h3 class="wp-block-heading"></h3>\n<!-- /wp:heading -->'
    )
    assert _roundtrips(new_heading_block(3))


def test_bulleted_list_uses_ul_and_one_empty_item():
    out = serialize([new_list_block(ordered=False)])
    assert out == (
        '<!-- wp:list -->\n<ul class="wp-block-list">'
        "<!-- wp:list-item -->\n<li></li>\n<!-- /wp:list-item -->"
        "</ul>\n<!-- /wp:list -->"
    )
    assert _roundtrips(new_list_block(ordered=False))


def test_numbered_list_uses_ol_and_ordered_attribute():
    out = serialize([new_list_block(ordered=True)])
    assert out.startswith('<!-- wp:list {"ordered":true} -->\n<ol class="wp-block-list">')
    assert out.endswith("</ol>\n<!-- /wp:list -->")
    assert _roundtrips(new_list_block(ordered=True))


def test_quote_wraps_one_empty_paragraph():
    out = serialize([new_quote_block()])
    assert out == (
        '<!-- wp:quote -->\n<blockquote class="wp-block-quote">'
        "<!-- wp:paragraph -->\n<p></p>\n<!-- /wp:paragraph -->"
        "</blockquote>\n<!-- /wp:quote -->"
    )
    assert _roundtrips(new_quote_block())


def test_code_block_shape():
    out = serialize([new_code_block()])
    assert out == (
        '<!-- wp:code -->\n<pre class="wp-block-code"><code></code></pre>\n<!-- /wp:code -->'
    )
    assert _roundtrips(new_code_block())


def test_preformatted_block_shape():
    out = serialize([new_preformatted_block()])
    assert out == (
        '<!-- wp:preformatted -->\n<pre class="wp-block-preformatted"></pre>\n'
        "<!-- /wp:preformatted -->"
    )
    assert _roundtrips(new_preformatted_block())


def test_separator_block_shape():
    out = serialize([new_separator_block()])
    assert out == (
        '<!-- wp:separator -->\n<hr class="wp-block-separator has-alpha-channel-opacity"/>\n'
        "<!-- /wp:separator -->"
    )
    assert _roundtrips(new_separator_block())


# --------------------------------------------------------------- structural guards


def test_every_factory_targets_an_editable_block():
    for block in (
        new_paragraph_block(),
        new_heading_block(2),
        new_list_block(),
        new_quote_block(),
        new_code_block(),
        new_preformatted_block(),
        new_separator_block(),
    ):
        assert block.block_name in EDITABLE_BLOCKS


def test_leaf_blocks_expose_an_empty_editable_body():
    # These convert to a single-wrapper editor the user types straight into.
    for block in (new_paragraph_block(), new_heading_block(2), new_preformatted_block()):
        assert get_editable_body(block) == ""


def test_list_and_quote_expose_one_editable_child():
    for container in (new_list_block(), new_quote_block()):
        assert len(container.inner_blocks) == 1
        assert get_editable_body(container.inner_blocks[0]) == ""


def test_set_heading_level_h2_to_h3_adds_wrapper_and_attribute():
    block = new_heading_block(2)
    set_editable_body(block, "Title")
    set_heading_level(block, 3)
    out = serialize([block])
    assert '<!-- wp:heading {"level":3} -->' in out
    assert '<h3 class="wp-block-heading">Title</h3>' in out
    assert _roundtrips(block)


def test_set_heading_level_h3_to_h2_drops_attribute():
    block = new_heading_block(3)
    set_editable_body(block, "Title")
    set_heading_level(block, 2)
    out = serialize([block])
    assert "level" not in out and '<h2 class="wp-block-heading">Title</h2>' in out


def test_set_heading_level_preserves_inline_formatting():
    block = new_heading_block(2)
    set_editable_body(block, "a <strong>bold</strong> word")
    set_heading_level(block, 4)
    assert "<strong>bold</strong>" in serialize([block])


def test_set_heading_level_preserves_other_wrapper_attributes():
    # A heading loaded from WordPress with an anchor id must keep it when the level changes.
    block = parse('<!-- wp:heading -->\n<h2 class="wp-block-heading" id="intro">Hi</h2>\n<!-- /wp:heading -->')[0]
    set_heading_level(block, 3)
    out = serialize([block])
    assert '<h3 class="wp-block-heading" id="intro">Hi</h3>' in out


def test_set_heading_level_matches_factory_bytes():
    changed = new_heading_block(2)
    set_heading_level(changed, 5)
    assert serialize([changed]) == serialize([new_heading_block(5)])


def test_code_block_editable_body_is_the_code_wrapper():
    # Documented quirk: core/code nests <code> inside <pre>, and the wrapper split keys
    # off the outer <pre>, so a fresh code block's editable body is "<code></code>",
    # not "". This matches how existing code blocks loaded from WordPress behave.
    assert get_editable_body(new_code_block()) == "<code></code>"

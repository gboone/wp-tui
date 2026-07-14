"""Headless tests: converting a markdown document into WordPress blocks + a title."""

from __future__ import annotations

from wptui.blocks import serialize
from wptui.blocks.markdown_import import convert_markdown


def _serialize(blocks) -> str:
    return serialize(blocks)


def _named(blocks) -> list:
    """Top-level real blocks, dropping the freeform blank-line separators between them."""
    return [b for b in blocks if not b.is_freeform]


def _names(blocks) -> list[str | None]:
    return [b.block_name for b in _named(blocks)]


# --------------------------------------------------------------------- kitchen sink


KITCHEN_SINK_MD = """\
# My Post Title

A paragraph with **bold**, *italic*, `code`, and a [link](https://example.com).

- First item
  - Nested item
- Second item

> A quoted paragraph.

```python
print("hi")
```
"""


def test_kitchen_sink_converts_expected_shapes_and_extracts_title():
    title, blocks = convert_markdown(KITCHEN_SINK_MD)

    assert title == "My Post Title"
    assert _names(blocks) == [
        "core/paragraph",
        "core/list",
        "core/quote",
        "core/code",
    ]

    paragraph, listing, quote, code = _named(blocks)

    out = _serialize([paragraph])
    assert "<strong>bold</strong>" in out
    assert "<em>italic</em>" in out
    assert "<code>code</code>" in out
    assert '<a href="https://example.com">link</a>' in out

    assert listing.block_name == "core/list"
    assert [c.block_name for c in listing.inner_blocks] == ["core/list-item", "core/list-item"]
    first_item, second_item = listing.inner_blocks
    assert "First item" in _serialize([first_item])
    nested_list = first_item.inner_blocks[0]
    assert nested_list.block_name == "core/list"
    assert nested_list.inner_blocks[0].block_name == "core/list-item"
    assert "Nested item" in _serialize([nested_list])
    assert "Second item" in _serialize([second_item])

    assert quote.block_name == "core/quote"
    assert quote.inner_blocks[0].block_name == "core/paragraph"
    assert "A quoted paragraph." in _serialize([quote])

    assert code.block_name == "core/code"
    assert '<pre class="wp-block-code"><code>print("hi")</code></pre>' in _serialize([code])


# ------------------------------------------------------------------- inline round-trip


def test_inline_formatting_converts_through_existing_inline_converter():
    title, blocks = convert_markdown("Some *italic*, **bold**, ***both***, and `code`.")
    assert title == ""
    (para,) = blocks
    out = _serialize([para])
    assert "<em>italic</em>" in out
    assert "<strong>bold</strong>" in out
    assert "<strong><em>both</em></strong>" in out or "<em><strong>both</strong></em>" in out
    assert "<code>code</code>" in out


def test_link_label_containing_escaped_bracket_survives_the_reassemble_round_trip():
    # Reassembled link text is re-parsed by wptui.inline's hand-rolled parser, which
    # needs every markup-significant character -- including ']' -- backslash-escaped
    # or it misreads the label as ending early.
    title, blocks = convert_markdown("See [a\\]b](https://example.com) link.")
    (para,) = blocks
    out = _serialize([para])
    assert '<a href="https://example.com">a]b</a>' in out


# ------------------------------------------------------------------------------ title


def test_no_leading_h1_leaves_title_blank_and_keeps_first_block():
    title, blocks = convert_markdown("Just a paragraph, no heading.")
    assert title == ""
    assert len(blocks) == 1
    assert blocks[0].block_name == "core/paragraph"
    assert "Just a paragraph, no heading." in _serialize(blocks)


def test_leading_h1_with_inline_formatting_extracts_plain_text_title():
    title, blocks = convert_markdown("# My **Bold** Title\n\nBody text.")
    assert title == "My Bold Title"
    assert "*" not in title
    assert "<" not in title
    assert _names(blocks) == ["core/paragraph"]


def test_two_consecutive_top_level_h1s_only_first_becomes_title():
    md = "# First Title\n\n# Second Heading\n\nBody paragraph.\n"
    title, blocks = convert_markdown(md)
    assert title == "First Title"
    assert _names(blocks) == ["core/heading", "core/paragraph"]
    heading = _named(blocks)[0]
    assert heading.attributes == {"level": 1}
    assert "Second Heading" in _serialize([heading])


def test_h1_nested_in_blockquote_is_never_a_title_candidate():
    md = "> # Nested H1\n> quoted text\n\nBody paragraph.\n"
    title, blocks = convert_markdown(md)
    assert title == ""
    assert _names(blocks) == ["core/quote", "core/paragraph"]
    quote = _named(blocks)[0]
    nested_heading = quote.inner_blocks[0]
    assert nested_heading.block_name == "core/heading"
    assert nested_heading.attributes == {"level": 1}
    assert "Nested H1" in _serialize([nested_heading])


def test_h1_nested_in_list_is_never_a_title_candidate():
    md = "- # Nested H1\n- second item\n\nBody paragraph.\n"
    title, blocks = convert_markdown(md)
    assert title == ""
    assert _names(blocks) == ["core/list", "core/paragraph"]
    first_item = _named(blocks)[0].inner_blocks[0]
    assert first_item.inner_blocks[0].block_name == "core/heading"


def test_empty_or_whitespace_only_input_converts_to_zero_blocks_without_raising():
    title, blocks = convert_markdown("")
    assert title == ""
    assert blocks == []

    title, blocks = convert_markdown("   \n\n   \n")
    assert title == ""
    assert blocks == []


# ------------------------------------------------------------------------------ images


def test_image_alongside_text_is_dropped_with_no_stray_link():
    md = "Look at this ![a cute cat](https://example.com/cat.png) photo, isn't it nice?"
    title, blocks = convert_markdown(md)
    (para,) = blocks
    out = _serialize([para])

    assert "<a " not in out
    assert "href" not in out
    assert "example.com/cat.png" not in out
    assert "![" not in out
    assert "isn't it nice?" in out
    assert "Look at this" in out
    assert para.block_name == "core/paragraph"


def test_dropped_image_does_not_leave_a_stray_double_space():
    title, blocks = convert_markdown(
        "Look at this ![a cute cat](https://example.com/cat.png) photo."
    )
    (para,) = blocks
    out = _serialize([para])
    assert "this  photo" not in out
    assert "this photo" in out


def test_leading_dropped_image_does_not_leave_a_stray_leading_space():
    title, blocks = convert_markdown("![alt](https://example.com/cat.png) leading text.")
    (para,) = blocks
    out = _serialize([para])
    assert "<p> leading" not in out
    assert "<p>leading text." in out


def test_image_only_paragraph_converts_cleanly_with_no_broken_reference():
    title, blocks = convert_markdown("![alt text](https://example.com/only.png)")
    (para,) = blocks
    out = _serialize([para])
    assert "<a " not in out
    assert "href" not in out
    assert "example.com/only.png" not in out
    assert "alt text" not in out  # alt text itself is discarded, not surfaced as a link label


# ------------------------------------------------------------------- underscore emphasis


def test_underscore_emphasis_passes_through_literally():
    title, blocks = convert_markdown("This is _em_ and __strong__ text.")
    (para,) = blocks
    out = _serialize([para])
    assert "_em_" in out
    assert "__strong__" in out
    assert "<em>" not in out
    assert "<strong>" not in out


# --------------------------------------------------------------------- unmapped/plain


def test_plain_prose_with_no_markdown_syntax_becomes_paragraph_blocks():
    # Simulates plain text copied out of a Google Doc: no markdown syntax survives,
    # so nothing should be interpreted as heading/list/bold structure.
    md = "Just some plain prose.\n\nAnother plain paragraph, still no markup."
    title, blocks = convert_markdown(md)
    assert title == ""
    assert _names(blocks) == ["core/paragraph", "core/paragraph"]
    out = _serialize(blocks)
    assert "<strong>" not in out
    assert "<em>" not in out
    assert "<h" not in out
    assert "<ul" not in out


def test_unmapped_thematic_break_falls_back_to_paragraph():
    md = "Above.\n\n---\n\nBelow."
    title, blocks = convert_markdown(md)
    assert _names(blocks) == ["core/paragraph", "core/paragraph", "core/paragraph"]
    assert "---" in _serialize([_named(blocks)[1]])


def test_unmapped_raw_html_block_falls_back_to_paragraph_with_raw_text():
    md = "Before.\n\n<div>raw html</div>\n\nAfter."
    title, blocks = convert_markdown(md)
    assert _names(blocks) == ["core/paragraph", "core/paragraph", "core/paragraph"]
    html_block = _named(blocks)[1]
    out = _serialize([html_block])
    # Rendered as literal, escaped text -- never as real embedded HTML.
    assert "&lt;div&gt;raw html&lt;/div&gt;" in out
    assert "<div>" not in out


# --------------------------------------------------------------------------- round-trip


def test_round_trip_is_byte_identical_through_serialize():
    """Freshly parsed blocks are dirty=False, so serialize(parse(x)) == x applies here
    too: the generated block-comment text must round-trip byte-for-byte."""
    md = (
        "# Title With **Bold**\n\n"
        "A paragraph with *italic*, **bold**, `code`, and a [link](https://x.example).\n\n"
        "- Item one\n"
        "  - Nested item\n"
        "- Item two\n\n"
        "> A quoted paragraph.\n\n"
        "```python\n"
        'print("hi")\n'
        "```\n\n"
        "---\n\n"
        "Trailing paragraph with an image ![alt](https://x.example/img.png) inside.\n"
    )
    _, blocks = convert_markdown(md)
    generated_text = serialize(blocks)
    # Re-parsing and re-serializing the already-generated text must reproduce it
    # byte-for-byte, since nothing in a freshly-parsed tree is dirty.
    from wptui.blocks import parse

    assert serialize(parse(generated_text)) == generated_text

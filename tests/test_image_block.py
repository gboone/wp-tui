"""Headless tests for image-block accessors and round-trip."""

from __future__ import annotations

from wptui.blocks import parse, serialize
from wptui.blocks.image import get_image_parts, set_image_parts

IMAGE_DOC = (
    '<!-- wp:image {"id":12,"sizeSlug":"large"} -->\n'
    '<figure class="wp-block-image size-large">'
    '<img src="https://x/p.jpg" alt="A cat" class="wp-image-12"/>'
    '<figcaption class="wp-element-caption">My cat</figcaption>'
    "</figure>\n<!-- /wp:image -->"
)

NO_CAPTION_DOC = (
    "<!-- wp:image -->\n"
    '<figure class="wp-block-image"><img src="https://x/a.png" alt=""/></figure>\n'
    "<!-- /wp:image -->"
)


def test_image_roundtrips_clean():
    assert serialize(parse(IMAGE_DOC)) == IMAGE_DOC


def test_read_image_parts():
    block = parse(IMAGE_DOC)[0]
    parts = get_image_parts(block)
    assert parts is not None
    assert parts.src == "https://x/p.jpg"
    assert parts.alt == "A cat"
    assert parts.caption_html == "My cat"


def test_edit_preserves_classes_and_id():
    block = parse(IMAGE_DOC)[0]
    set_image_parts(block, src="https://x/dog.jpg", alt="A dog", caption_html="My dog")
    out = serialize([block])
    assert 'src="https://x/dog.jpg"' in out
    assert 'alt="A dog"' in out
    assert "<figcaption class=\"wp-element-caption\">My dog</figcaption>" in out
    # Untouched bits survive: the wp-image-12 class, the block id, the figure class.
    assert 'class="wp-image-12"' in out
    assert '<!-- wp:image {"id":12,"sizeSlug":"large"} -->' in out
    assert 'class="wp-block-image size-large"' in out


def test_attribute_values_are_escaped():
    block = parse(IMAGE_DOC)[0]
    set_image_parts(block, src="https://x/a.jpg?x=1&y=2", alt='He said "hi"', caption_html="c")
    out = serialize([block])
    assert "x=1&amp;y=2" in out
    assert 'alt="He said &quot;hi&quot;"' in out


def test_add_caption_where_none_existed():
    block = parse(NO_CAPTION_DOC)[0]
    assert get_image_parts(block).caption_html == ""
    set_image_parts(block, src="https://x/a.png", alt="alt", caption_html="new cap")
    out = serialize([block])
    assert '<figcaption class="wp-element-caption">new cap</figcaption></figure>' in out


def test_clear_caption_removes_figcaption():
    block = parse(IMAGE_DOC)[0]
    set_image_parts(block, src="https://x/p.jpg", alt="A cat", caption_html="")
    out = serialize([block])
    assert "figcaption" not in out
    assert "<img" in out

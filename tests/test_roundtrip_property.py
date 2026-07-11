"""Property-based round-trip test: random block documents must survive intact."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from wptui.blocks import parse, serialize

# A pool of representative serialized blocks (including nested + void + third-party).
BLOCK_SNIPPETS = [
    "<!-- wp:paragraph -->\n<p>Text.</p>\n<!-- /wp:paragraph -->",
    '<!-- wp:heading {"level":2} -->\n<h2>H</h2>\n<!-- /wp:heading -->',
    '<!-- wp:image {"id":9} -->\n<figure><img src="x.jpg"/></figure>\n<!-- /wp:image -->',
    '<!-- wp:spacer {"height":"10px"} /-->',
    "<!-- wp:separator -->\n<hr/>\n<!-- /wp:separator -->",
    "<!-- wp:quote -->\n<blockquote><!-- wp:paragraph -->\n<p>Q</p>\n"
    "<!-- /wp:paragraph --></blockquote>\n<!-- /wp:quote -->",
    '<!-- wp:acme/w {"a":{"b":[1,2]},"c":true} -->\n<div>x}y</div>\n<!-- /wp:acme/w -->',
    "<p>freeform html chunk</p>",
]

WHITESPACE = st.sampled_from(["", "\n", "\n\n", " ", "\n\n\n"])


@st.composite
def documents(draw) -> str:
    """Assemble a document from random snippets joined by random whitespace."""
    n = draw(st.integers(min_value=0, max_value=8))
    parts: list[str] = []
    for _ in range(n):
        parts.append(draw(WHITESPACE))
        parts.append(draw(st.sampled_from(BLOCK_SNIPPETS)))
    parts.append(draw(WHITESPACE))
    return "".join(parts)


@settings(max_examples=400)
@given(documents())
def test_roundtrip_random_documents(doc: str) -> None:
    assert serialize(parse(doc)) == doc

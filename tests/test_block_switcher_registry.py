"""Tests for the headless block-type registry and matcher (U2)."""

from __future__ import annotations

from wptui.blocks.model import EDITABLE_BLOCKS
from wptui.blocks.switcher import REGISTRY, match


def _labels(entries) -> list[str]:
    return [e.label for e in entries]


def test_empty_query_returns_full_registry_in_order():
    assert match("") == list(REGISTRY)
    assert _labels(match("   ")) == [e.label for e in REGISTRY]


def test_bulleted_list_matches_name_and_aliases():
    for query in ("bul", "bulleted", "bulleted list", "ul", "bullets"):
        assert _labels(match(query)) == ["Bulleted list"], query


def test_list_query_returns_both_lists_in_registry_order():
    assert _labels(match("list")) == ["Bulleted list", "Numbered list"]


def test_matching_is_case_insensitive():
    assert match("BULLETED") == match("bulleted")


def test_no_match_returns_empty():
    assert match("nonsense-xyz") == []


def test_h3_query_returns_only_heading_3():
    from wptui.blocks import serialize

    entries = match("h3")
    assert _labels(entries) == ["Heading 3"]
    assert '<h3 class="wp-block-heading">' in serialize([entries[0].factory()])


def test_heading_query_returns_all_six_with_h2_first_h1_last():
    # H2 leads so a bare "heading" + Enter (top match) inserts H2, not H1.
    assert _labels(match("heading")) == ["Heading 2", "Heading 3", "Heading 4", "Heading 5", "Heading 6", "Heading 1"]


def test_each_heading_entry_builds_its_level():
    from wptui.blocks import serialize

    for n in range(1, 7):
        entry = match(f"h{n}")[0]
        assert f"<h{n} " in serialize([entry.factory()])


def test_alias_matching_is_prefix_not_substring():
    # Aliases match by prefix so a short query can't hit mid-word: "der" must not match
    # inside "ordered list", and "ule" must not match inside "horizontal rule".
    assert match("der") == []
    assert match("ule") == []


def test_every_factory_produces_an_editable_block():
    for entry in REGISTRY:
        assert entry.factory().block_name in EDITABLE_BLOCKS


def test_registry_module_is_headless():
    # The headless-library rule: importing wptui.blocks.switcher must not pull in textual.
    # Check in a fresh interpreter so the outer test session's imports don't mask it.
    import subprocess
    import sys

    code = "import wptui.blocks.switcher, sys; assert 'textual' not in sys.modules"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

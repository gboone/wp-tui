"""Tests for headless container child-mutation helpers (U1)."""

from __future__ import annotations

from wptui.blocks import parse, serialize
from wptui.blocks.containers import child_factory_for, set_container_children
from wptui.blocks.factory import new_list_block, new_list_item, new_paragraph_block, new_quote_block
from wptui.blocks.text import set_editable_body


def _roundtrips(block) -> bool:
    once = serialize([block])
    return serialize(parse(once)) == once


def test_two_item_list_serializes_both_and_roundtrips():
    lst = new_list_block()
    a, b = new_list_item(), new_list_item()
    set_editable_body(a, "one")
    set_editable_body(b, "two")
    set_container_children(lst, [a, b])
    out = serialize([lst])
    assert out.count("<!-- wp:list-item -->") == 2
    assert "<li>one</li>" in out and "<li>two</li>" in out
    assert _roundtrips(lst)


def test_add_third_child_keeps_order():
    lst = new_list_block()
    items = [new_list_item() for _ in range(3)]
    for i, item in enumerate(items):
        set_editable_body(item, str(i))
    set_container_children(lst, items)
    out = serialize([lst])
    assert out.index("<li>0</li>") < out.index("<li>1</li>") < out.index("<li>2</li>")


def test_remove_middle_child():
    lst = new_list_block()
    a, b, c = (new_list_item() for _ in range(3))
    for item, t in ((a, "a"), (b, "b"), (c, "c")):
        set_editable_body(item, t)
    set_container_children(lst, [a, b, c])
    set_container_children(lst, [a, c])  # drop the middle
    out = serialize([lst])
    assert "<li>a</li>" in out and "<li>c</li>" in out and "<li>b</li>" not in out
    assert _roundtrips(lst)


def test_ordered_list_wrapper_preserved():
    lst = new_list_block(ordered=True)
    set_container_children(lst, [new_list_item(), new_list_item()])
    out = serialize([lst])
    assert '<ol class="wp-block-list">' in out and out.count("<!-- wp:list-item -->") == 2


def test_quote_wrapper_preserved_and_child_is_paragraph():
    quote = new_quote_block()
    p1, p2 = new_paragraph_block(), new_paragraph_block()
    set_editable_body(p1, "a")
    set_editable_body(p2, "b")
    set_container_children(quote, [p1, p2])
    out = serialize([quote])
    assert '<blockquote class="wp-block-quote">' in out
    assert out.count("<!-- wp:paragraph -->") == 2
    assert _roundtrips(quote)


def test_child_factory_for_matches_container_type():
    assert child_factory_for(new_list_block())().block_name == "core/list-item"
    assert child_factory_for(new_quote_block())().block_name == "core/paragraph"


def test_single_child_matches_factory_bytes():
    # set_container_children with one item reproduces exactly what new_list_block emits.
    lst = new_list_block()
    rebuilt = new_list_block()
    set_container_children(rebuilt, [new_list_item()])
    assert serialize([rebuilt]) == serialize([lst])


def test_containers_module_is_headless():
    import subprocess
    import sys

    code = "import wptui.blocks.containers, sys; assert 'textual' not in sys.modules"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

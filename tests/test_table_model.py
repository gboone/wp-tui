"""Tests for the headless table cell model (U1)."""

from __future__ import annotations

TWO_BY_TWO = (
    '<figure class="wp-block-table"><table><tbody>'
    "<tr><td>A</td><td>B</td></tr>"
    "<tr><td>C</td><td>D</td></tr>"
    "</tbody></table></figure>"
)

WITH_SECTIONS = (
    '<figure class="wp-block-table"><table>'
    "<thead><tr><th>H1</th><th>H2</th></tr></thead>"
    "<tbody><tr><td>a</td><td>b</td></tr></tbody>"
    "<tfoot><tr><td>f1</td><td>f2</td></tr></tfoot>"
    "</table><figcaption>My caption</figcaption></figure>"
)

WITH_SPANS = (
    '<figure class="wp-block-table"><table><tbody>'
    '<tr><td colspan="2">wide</td></tr>'
    '<tr><td class="has-text-align-center">x</td><td>y</td></tr>'
    "</tbody></table></figure>"
)

WITH_FORMATTING = (
    '<figure class="wp-block-table"><table><tbody>'
    '<tr><td>plain</td><td>a <strong>bold</strong> and <a href="https://x">link</a></td></tr>'
    "</tbody></table></figure>"
)


def _model(html):
    from wptui.blocks.table import parse_table

    return parse_table(html)


def test_parses_grid_and_roundtrips_verbatim():
    m = _model(TWO_BY_TWO)
    assert m.shape == (2, 2)
    assert [[m.cell(r, c) for c in range(2)] for r in range(2)] == [["A", "B"], ["C", "D"]]
    assert m.serialize() == TWO_BY_TWO


def test_edit_one_cell_changes_only_that_cell():
    m = _model(TWO_BY_TWO)
    m.set_cell(0, 1, "<strong>X</strong>")
    out = m.serialize()
    assert out == (
        '<figure class="wp-block-table"><table><tbody>'
        "<tr><td>A</td><td><strong>X</strong></td></tr>"
        "<tr><td>C</td><td>D</td></tr>"
        "</tbody></table></figure>"
    )


def test_thead_tbody_tfoot_and_caption_preserved():
    m = _model(WITH_SECTIONS)
    assert m.shape == (3, 2)
    assert m.cell(0, 0) == "H1" and m.cell_tag(0, 0) == "th"
    assert m.cell(2, 1) == "f2"
    m.set_cell(1, 0, "edited")
    out = m.serialize()
    assert "<figcaption>My caption</figcaption>" in out
    assert "<thead>" in out and "<tfoot>" in out and "<th>H1</th>" in out
    assert "<td>edited</td>" in out


def test_colspan_and_alignment_attributes_survive_an_edit():
    m = _model(WITH_SPANS)
    m.set_cell(1, 1, "z")  # edit an unrelated cell
    out = m.serialize()
    assert '<td colspan="2">wide</td>' in out
    assert '<td class="has-text-align-center">x</td>' in out
    assert "<td>z</td>" in out


def test_formatted_cell_content_is_read_as_html_and_preserved():
    m = _model(WITH_FORMATTING)
    assert m.cell(0, 1) == 'a <strong>bold</strong> and <a href="https://x">link</a>'
    m.set_cell(0, 0, "changed")  # edit the plain cell
    assert m.serialize() == WITH_FORMATTING.replace("<td>plain</td>", "<td>changed</td>")


def test_empty_cell_is_addressable():
    html = '<figure class="wp-block-table"><table><tbody><tr><td></td></tr></tbody></table></figure>'
    m = _model(html)
    assert m.cell(0, 0) == ""
    m.set_cell(0, 0, "now filled")
    assert "<td>now filled</td>" in m.serialize()


def test_dirty_tracks_real_changes_only():
    m = _model(TWO_BY_TWO)
    assert not m.dirty()
    m.set_cell(0, 0, "A")  # same as original
    assert not m.dirty()
    m.set_cell(0, 0, "changed")
    assert m.dirty()


def test_nested_table_is_marked_not_editable():
    html = (
        '<figure class="wp-block-table"><table><tbody><tr><td>'
        "<table><tbody><tr><td>inner</td></tr></tbody></table>"
        "</td></tr></tbody></table></figure>"
    )
    m = _model(html)
    assert m.editable is False


def test_table_model_is_headless():
    import subprocess
    import sys

    code = "import wptui.blocks.table, sys; assert 'textual' not in sys.modules"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

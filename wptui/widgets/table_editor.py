"""TableEditor: an editable grid of cell editors for a ``core/table`` block.

Parses the block's ``inner_html`` into a headless :class:`~wptui.blocks.table.TableModel`,
renders one :class:`~wptui.widgets.inline_area.InlineMarkdownArea` per cell (seeded as
markdown), and on ``commit()`` splices any changed cells back into the block's ``inner_html``.
Mirrors :class:`~wptui.widgets.text_block.TextBlockEditor`'s commit contract so the canvas
``sync()`` loop drives it like any other editor.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from wptui.blocks.model import Block
from wptui.blocks.table import parse_table
from wptui.inline import html_to_markdown, markdown_to_html
from wptui.widgets.inline_area import InlineMarkdownArea


class TableEditor(Vertical):
    """A labeled grid of per-cell editors bound to one ``core/table`` block."""

    DEFAULT_CSS = """
    TableEditor { height: auto; }
    TableEditor .table-row { height: auto; }
    TableEditor .table-cell { width: 20; height: auto; margin-right: 1; }
    TableEditor .table-cell.header { text-style: bold; }
    """

    def __init__(self, block: Block) -> None:
        super().__init__()
        self.block = block
        self._model = parse_table(block.inner_html)
        self._seed: dict[tuple[int, int], str] = {}

    def compose(self) -> ComposeResult:
        yield Static("table", classes="block-label")
        for row, length in enumerate(self._model.row_lengths()):
            with Horizontal(classes="table-row"):
                for col in range(length):
                    markdown = html_to_markdown(self._model.cell(row, col))
                    self._seed[(row, col)] = markdown
                    classes = "table-cell header" if self._model.cell_tag(row, col) == "th" else "table-cell"
                    yield InlineMarkdownArea(markdown, id=f"cell-{row}-{col}", classes=classes)

    def commit(self) -> None:
        """Write changed cells back into the block's ``inner_html`` (dirty) if any changed."""
        for (row, col), seed in self._seed.items():
            area = self.query_one(f"#cell-{row}-{col}", InlineMarkdownArea)
            if area.text != seed:  # only touch genuinely-edited cells — keep the rest byte-identical
                self._model.set_cell(row, col, markdown_to_html(area.text))
        if self._model.dirty():
            html = self._model.serialize()
            self.block.inner_html = html
            self.block.inner_content = [html]
            self.block.mark_dirty()

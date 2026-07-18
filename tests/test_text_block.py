"""Tests for TextBlockEditor label rendering (U4)."""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Static

from wptui.blocks.factory import new_heading_block, new_paragraph_block
from wptui.widgets.text_block import TextBlockEditor


class Harness(App):
    def __init__(self, block) -> None:
        super().__init__()
        self._block = block

    def compose(self) -> ComposeResult:
        yield TextBlockEditor(self._block)


async def _label(app) -> str:
    return str(app.query_one(".block-label", Static).render())


@pytest.mark.asyncio
async def test_h2_heading_labels_as_heading_2():
    app = Harness(new_heading_block(2))  # no level attribute -> defaults to 2
    async with app.run_test() as pilot:
        await pilot.pause()
        assert await _label(app) == "heading 2"


@pytest.mark.asyncio
async def test_h4_heading_labels_as_heading_4():
    app = Harness(new_heading_block(4))
    async with app.run_test() as pilot:
        await pilot.pause()
        assert await _label(app) == "heading 4"


@pytest.mark.asyncio
async def test_paragraph_label_unchanged():
    app = Harness(new_paragraph_block())
    async with app.run_test() as pilot:
        await pilot.pause()
        assert await _label(app) == "paragraph"

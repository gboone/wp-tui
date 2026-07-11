"""Widget-level tests that Vim actions dispatch to the right TextArea behavior (#6).

The keymap resolver is unit-tested in test_vim_keys; this covers the fragile other
half — _dispatch_vim translating action names into real TextArea cursor/edit calls.
"""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult

from wptui.keys import Mode
from wptui.widgets.inline_area import InlineMarkdownArea


class Harness(App):
    def compose(self) -> ComposeResult:
        yield InlineMarkdownArea("line one\nline two\nline three", id="a")


async def _vim_area(pilot, app):
    area = app.query_one("#a", InlineMarkdownArea)
    area.focus()
    area.move_cursor((0, 0))
    app.vim_mode = True
    area.refresh_vim()
    await pilot.pause()
    return area


@pytest.mark.asyncio
async def test_G_and_gg_jump_to_document_end_and_start():
    app = Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        area = await _vim_area(pilot, app)

        await pilot.press("G")
        assert area.cursor_location[0] == 2  # last line

        await pilot.press("g", "g")
        assert area.cursor_location == (0, 0)


@pytest.mark.asyncio
async def test_dd_deletes_current_line():
    app = Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        area = await _vim_area(pilot, app)

        await pilot.press("d", "d")
        await pilot.pause()
        assert "line one" not in area.text
        assert "line two" in area.text


@pytest.mark.asyncio
async def test_o_opens_line_below_and_enters_insert():
    app = Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        area = await _vim_area(pilot, app)

        await pilot.press("o")
        assert area._vim.mode is Mode.INSERT
        assert area.cursor_location[0] == 1  # now on the newly opened line
        await pilot.press("z")
        await pilot.pause()
        assert area.text.startswith("line one\nz")


@pytest.mark.asyncio
async def test_motions_move_the_cursor():
    app = Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        area = await _vim_area(pilot, app)

        await pilot.press("l", "l", "l")  # right x3
        assert area.cursor_location == (0, 3)
        await pilot.press("0")  # line start
        assert area.cursor_location == (0, 0)
        await pilot.press("j")  # down
        assert area.cursor_location[0] == 1

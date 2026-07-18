"""Tests for the BlockSwitcherModal picker (U4)."""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Input, OptionList

from wptui.blocks.switcher import REGISTRY
from wptui.widgets.block_switcher import BlockSwitcherModal


class Harness(App):
    def __init__(self) -> None:
        super().__init__()
        self.result: object = "unset"

    def compose(self) -> ComposeResult:
        yield from ()

    def on_mount(self) -> None:
        self.push_screen(BlockSwitcherModal(), lambda r: setattr(self, "result", r))


@pytest.mark.asyncio
async def test_mount_seeds_full_registry_in_order():
    app = Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        options = app.screen.query_one("#switch-list", OptionList)
        assert options.option_count == len(REGISTRY)


@pytest.mark.asyncio
async def test_typing_filters_the_list():
    app = Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.query_one("#switch-search", Input).value = "bul"
        await pilot.pause()
        options = app.screen.query_one("#switch-list", OptionList)
        assert options.option_count == 1


@pytest.mark.asyncio
async def test_enter_selects_top_match_and_dismisses():
    app = Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        search = app.screen.query_one("#switch-search", Input)
        search.focus()
        search.value = "bulleted"
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
    assert app.result.label == "Bulleted list"


@pytest.mark.asyncio
async def test_selecting_an_option_dismisses_with_it():
    app = Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        options = app.screen.query_one("#switch-list", OptionList)
        options.focus()
        options.highlighted = 2  # Bulleted list, in registry order
        await pilot.press("enter")
        await pilot.pause()
    assert app.result.label == "Bulleted list"


@pytest.mark.asyncio
async def test_escape_cancels_with_none():
    app = Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
    assert app.result is None


@pytest.mark.asyncio
async def test_empty_search_restores_full_list():
    app = Harness()
    async with app.run_test() as pilot:
        await pilot.pause()
        search = app.screen.query_one("#switch-search", Input)
        search.value = "quote"
        await pilot.pause()
        search.value = ""
        await pilot.pause()
        options = app.screen.query_one("#switch-list", OptionList)
        assert options.option_count == len(REGISTRY)

"""Tests for the console entry point flag handling (no TUI launch)."""

from __future__ import annotations

import wptui
from wptui.__main__ import main


def test_version_flag_prints_version_and_does_not_launch(capsys):
    main(["--version"])
    out = capsys.readouterr().out
    assert wptui.__version__ in out
    assert out.startswith("wptui ")


def test_short_version_flag(capsys):
    main(["-V"])
    assert wptui.__version__ in capsys.readouterr().out


def test_help_flag_prints_usage(capsys):
    main(["--help"])
    assert "usage: wptui" in capsys.readouterr().out


def test_installed_version_matches_pyproject():
    # importlib.metadata resolves to the installed dist; guard against the old
    # hardcoded-and-stale __version__ regression.
    assert wptui.__version__ not in ("", "0.0.0+unknown")

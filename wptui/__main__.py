"""Console entry point: ``python -m wptui`` / ``wptui``."""

from __future__ import annotations

import sys

from wptui import __version__

_USAGE = "usage: wptui [--version] [--help]\n\nLaunch the wp-tui terminal UI for editing WordPress posts."


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    if "--version" in args or "-V" in args:
        print(f"wptui {__version__}")
        return
    if "--help" in args or "-h" in args:
        print(_USAGE)
        return
    # Import the app lazily so --version/--help stay fast and need no terminal.
    from wptui.app import WPTuiApp

    WPTuiApp().run()


if __name__ == "__main__":
    main()

"""Console entry point: ``python -m wptui`` / ``wptui``."""

from __future__ import annotations

import sys

from wptui.app import WPTuiApp
from wptui.blocks.markdown_import import convert_markdown
from wptui.stdin_import import (
    NoControllingTerminalError,
    read_piped_input,
    reattach_controlling_terminal,
)


def main() -> None:
    # Read (and, if present, convert) any piped stdin before WPTuiApp is ever
    # constructed. Any failure in this step -- a read/decode error, or an unexpected
    # exception from markdown conversion -- is a hard failure (R16): report it clearly
    # and exit nonzero rather than let a raw traceback (or a half-built app) surface.
    pending_import: tuple[str, list] | None = None
    try:
        piped = read_piped_input()
        if piped is not None:
            pending_import = convert_markdown(piped)
    except Exception as exc:
        print(f"wptui: failed to read/convert piped input: {exc}", file=sys.stderr)
        sys.exit(1)

    if pending_import is not None:
        # Only the piped path ever consumed stdin, so only it needs to reattach the
        # process's input to the controlling terminal before the app can read keys again.
        try:
            reattach_controlling_terminal()
        except NoControllingTerminalError as exc:
            print(f"wptui: {exc}", file=sys.stderr)
            sys.exit(1)

    app = WPTuiApp()
    if pending_import is not None:
        app.pending_import = pending_import
    app.run()


if __name__ == "__main__":
    main()

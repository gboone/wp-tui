"""Console entry point: ``python -m wptui`` / ``wptui``."""

from __future__ import annotations

from wptui.app import WPTuiApp


def main() -> None:
    WPTuiApp().run()


if __name__ == "__main__":
    main()

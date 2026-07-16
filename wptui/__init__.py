"""wp-tui: a terminal UI for editing WordPress posts."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("wptui")
except PackageNotFoundError:  # source tree without install metadata
    __version__ = "0.0.0+unknown"

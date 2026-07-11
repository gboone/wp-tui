"""Headless WordPress block-grammar library.

This package parses and serializes the block grammar losslessly. It MUST NOT import
``textual`` — it is a pure library so round-trip correctness is testable without a
terminal.
"""

from wptui.blocks.grammar import parse
from wptui.blocks.model import Block
from wptui.blocks.serialize import propagate_dirty, serialize, serialize_block

__all__ = ["parse", "serialize", "serialize_block", "propagate_dirty", "Block"]

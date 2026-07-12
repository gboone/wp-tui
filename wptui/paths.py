"""Normalize filesystem paths supplied via the terminal (typed, pasted, drag-dropped).

Headless (no ``textual`` import) so the terminal-escaping rules are unit-testable without
a terminal. Terminals deliver a dragged/pasted path in several shapes — wrapped in quotes,
with shell-escaped spaces, as a ``file://`` URI, with ``~`` — and this turns any of them
into a plain path string. Existence is the caller's concern; this only cleans the string.
"""

from __future__ import annotations

import os
import re
from urllib.parse import unquote, urlparse

# Shell metacharacters a drag/paste may backslash-escape. Deliberately does NOT include
# letters/digits, so a Windows-style ``C:\Users`` path is left intact.
_SHELL_ESCAPE_RE = re.compile(r"\\([ ()\[\]{}'\"&!$`\\;<>|*?~#])")


def normalize_dropped_path(raw: str) -> str:
    """Turn a terminal-supplied path string into a usable path (not required to exist)."""
    s = raw.strip()
    if not s:
        return ""

    quoted = False
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        s = s[1:-1]
        quoted = True

    if s.startswith("file://"):
        # file:///home/u/a%20b.png -> /home/u/a b.png (drop host, percent-decode)
        s = unquote(urlparse(s).path)
    elif not quoted:
        # Only unescape when unquoted; a quoted path's contents are already literal.
        s = _SHELL_ESCAPE_RE.sub(r"\1", s)

    return os.path.expanduser(s)


def looks_like_path(raw: str) -> bool:
    """Heuristic: does ``raw`` look like a filesystem path (vs. pasted prose)?"""
    p = normalize_dropped_path(raw)
    if not p:
        return False
    if p.startswith(("/", "~", "./", "../")):
        return True
    return os.path.exists(p)

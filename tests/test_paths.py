"""Tests for terminal filepath normalization (U3)."""

from __future__ import annotations

import os

import pytest

from wptui.paths import looks_like_path, normalize_dropped_path


@pytest.mark.parametrize(
    "raw,expected",
    [
        ('"/home/u/a b.png"', "/home/u/a b.png"),          # double-quoted
        ("'/home/u/a b.png'", "/home/u/a b.png"),          # single-quoted
        ("/home/u/a\\ b.png", "/home/u/a b.png"),          # backslash-escaped space
        ("file:///home/u/a%20b.png", "/home/u/a b.png"),   # file URI, percent-decoded
        ("  /home/u/x.png\n", "/home/u/x.png"),            # trailing paste whitespace
        ("/home/u/plain.png", "/home/u/plain.png"),        # already clean, unchanged
        ("", ""),                                          # empty
    ],
)
def test_normalize(raw, expected):
    assert normalize_dropped_path(raw) == expected


def test_tilde_expands_to_home():
    result = normalize_dropped_path("~/Pictures/x.png")
    assert result == os.path.join(os.path.expanduser("~"), "Pictures/x.png")
    assert "~" not in result


def test_backslash_escapes_only_metachars_not_letters():
    # A Windows-ish path's backslashes before letters are preserved.
    assert normalize_dropped_path("C:\\Users\\me\\pic.png") == "C:\\Users\\me\\pic.png"
    # But an escaped paren/ampersand is unescaped.
    assert normalize_dropped_path("/a/b\\ \\(1\\).png") == "/a/b (1).png"


def test_normalize_is_idempotent():
    for raw in ['"/home/u/a b.png"', "/home/u/a\\ b.png", "file:///x/y%20z.png", "~/z.png"]:
        once = normalize_dropped_path(raw)
        assert normalize_dropped_path(once) == once


def test_looks_like_path():
    assert looks_like_path("/home/u/x.png")
    assert looks_like_path("~/x.png")
    assert looks_like_path('"/home/u/a b.png"')
    assert not looks_like_path("just some pasted words")
    assert not looks_like_path("")

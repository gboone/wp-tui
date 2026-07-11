"""Tests for profile persistence: TOML round-trip, escaping, perms, keyring wrappers."""

from __future__ import annotations

import stat
import sys

import pytest

import wptui.config as config
from wptui.config import SiteProfile


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    """Point config at a temp dir and an in-memory keyring."""
    monkeypatch.setattr(config, "_CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "_CONFIG_FILE", tmp_path / "profiles.toml")

    store: dict[tuple[str, str], str] = {}
    monkeypatch.setattr(
        config.keyring, "set_password", lambda svc, key, pw: store.__setitem__((svc, key), pw)
    )
    monkeypatch.setattr(config.keyring, "get_password", lambda svc, key: store.get((svc, key)))
    monkeypatch.setattr(config.keyring, "delete_password", lambda svc, key: store.pop((svc, key)))
    return store


def test_save_list_get_roundtrip(isolated_config):
    profile = SiteProfile(name="blog", base_url="https://example.com/", username="editor")
    config.save_profile(profile, "app pass word")

    listed = config.list_profiles()
    assert len(listed) == 1
    got = config.get_profile("blog")
    assert got is not None
    assert got.base_url == "https://example.com"  # trailing slash stripped on save
    assert got.username == "editor"
    assert config.get_credentials(got) == "app pass word"


def test_profile_name_needing_quotes_and_escapes_roundtrips(isolated_config):
    # A name that is not a bare TOML key and a username with a control character.
    tricky = SiteProfile(name='my "main" site', base_url="https://x.io", username="a\tb")
    config.save_profile(tricky, "pw")
    got = config.get_profile('my "main" site')
    assert got is not None
    assert got.username == "a\tb"  # survives TOML escaping + re-parse


def test_api_root_strips_trailing_slash():
    p = SiteProfile(name="n", base_url="https://x.io/", username="u")
    assert p.api_root == "https://x.io/wp-json/wp/v2"


def test_get_credentials_returns_none_on_keyring_error(isolated_config, monkeypatch):
    def boom(svc, key):
        raise config.keyring.errors.KeyringError("locked")

    monkeypatch.setattr(config.keyring, "get_password", boom)
    p = SiteProfile(name="n", base_url="https://x.io", username="u")
    assert config.get_credentials(p) is None


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")
def test_config_file_is_owner_only(isolated_config):
    config.save_profile(SiteProfile("n", "https://x.io", "u"), "pw")
    mode = stat.S_IMODE(config._CONFIG_FILE.stat().st_mode)
    assert mode == 0o600

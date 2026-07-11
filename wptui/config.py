"""Site profiles and credential storage.

Non-secret profile data (site URL, username, label) is stored in a TOML file under
the user config directory. The Application Password itself is stored in the OS secret
store via ``keyring`` and never written to disk in plaintext.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

import keyring
import keyring.errors
from platformdirs import user_config_dir

APP_NAME = "wptui"
KEYRING_SERVICE = "wptui"

_CONFIG_DIR = Path(user_config_dir(APP_NAME))
_CONFIG_FILE = _CONFIG_DIR / "profiles.toml"


@dataclass(frozen=True)
class SiteProfile:
    """A connection to one WordPress site (without the secret)."""

    name: str
    """Stable identifier / label for the profile, e.g. ``"blog"``."""
    base_url: str
    """Site root URL, e.g. ``https://example.com`` (no trailing ``/wp-json``)."""
    username: str
    """WordPress username the Application Password belongs to."""

    @property
    def api_root(self) -> str:
        """The REST API v2 root, e.g. ``https://example.com/wp-json/wp/v2``."""
        return f"{self.base_url.rstrip('/')}/wp-json/wp/v2"

    @property
    def _keyring_key(self) -> str:
        # One secret per (profile, user) pair.
        return f"{self.name}\x1f{self.username}\x1f{self.base_url.rstrip('/')}"


def _read_raw() -> dict:
    if not _CONFIG_FILE.exists():
        return {}
    with _CONFIG_FILE.open("rb") as fh:
        return tomllib.load(fh)


def _write_raw(data: dict) -> None:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _CONFIG_DIR.chmod(0o700)  # profile dir: owner-only
    except OSError:
        pass
    lines: list[str] = []
    for name, entry in data.get("profiles", {}).items():
        lines.append(f"[profiles.{_toml_key(name)}]")
        for key in ("base_url", "username"):
            lines.append(f'{key} = "{_toml_escape(entry[key])}"')
        lines.append("")
    _CONFIG_FILE.write_text("\n".join(lines), encoding="utf-8")
    try:
        _CONFIG_FILE.chmod(0o600)  # discloses the WordPress username; keep it owner-only
    except OSError:
        pass


# TOML basic-string escapes for the control characters json/tomllib will otherwise
# choke on when the file is read back.
_TOML_ESCAPES = {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\r": "\\r", "\t": "\\t"}


def _toml_key(name: str) -> str:
    # Bare key if it's a simple identifier, else a quoted key.
    if name and all(c.isalnum() or c in "-_" for c in name):
        return name
    return f'"{_toml_escape(name)}"'


def _toml_escape(value: str) -> str:
    out: list[str] = []
    for ch in value:
        if ch in _TOML_ESCAPES:
            out.append(_TOML_ESCAPES[ch])
        elif ord(ch) < 0x20:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    return "".join(out)


def list_profiles() -> list[SiteProfile]:
    """Return all saved profiles (without secrets), sorted by name."""
    raw = _read_raw()
    profiles = [
        SiteProfile(name=name, base_url=entry["base_url"], username=entry["username"])
        for name, entry in raw.get("profiles", {}).items()
    ]
    return sorted(profiles, key=lambda p: p.name)


def get_profile(name: str) -> SiteProfile | None:
    """Return one saved profile by name, or ``None`` if absent."""
    return next((p for p in list_profiles() if p.name == name), None)


def save_profile(profile: SiteProfile, app_password: str) -> None:
    """Persist a profile and store its Application Password in the OS keychain."""
    raw = _read_raw()
    raw.setdefault("profiles", {})[profile.name] = {
        "base_url": profile.base_url.rstrip("/"),
        "username": profile.username,
    }
    _write_raw(raw)
    keyring.set_password(KEYRING_SERVICE, profile._keyring_key, app_password)


def get_credentials(profile: SiteProfile) -> str | None:
    """Return the stored Application Password for a profile, or ``None``."""
    try:
        return keyring.get_password(KEYRING_SERVICE, profile._keyring_key)
    except keyring.errors.KeyringError:
        return None


def delete_profile(profile: SiteProfile) -> None:
    """Remove a profile and its stored secret."""
    raw = _read_raw()
    raw.get("profiles", {}).pop(profile.name, None)
    _write_raw(raw)
    try:
        keyring.delete_password(KEYRING_SERVICE, profile._keyring_key)
    except keyring.errors.KeyringError:
        pass

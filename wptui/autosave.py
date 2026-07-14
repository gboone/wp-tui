"""Local autosave: crash-safe snapshots of the in-editor buffer.

Snapshots are JSON files under the user *state* dir (or ``$WPTUI_STATE_DIR`` when set, which
tests use), keyed by a caller-supplied string. They exist so a crash, dropped connection, or
accidental quit never loses unsaved editor work; the editor clears a snapshot once the post
is safely saved to the server. Headless (no ``textual`` import) so it is unit-testable.

Every write is best-effort — autosave must never itself break the editor — so read/write/clear
swallow filesystem errors and simply degrade to "no snapshot".
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from platformdirs import user_state_dir

from wptui.config import APP_NAME


def _draft_dir() -> Path:
    override = os.environ.get("WPTUI_STATE_DIR")
    base = Path(override) if override else Path(user_state_dir(APP_NAME))
    return base / "drafts"


def _key_to_path(key: str) -> Path:
    # Keys carry a site URL + ids; slugify to a safe, flat filename.
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", key) or "draft"
    return _draft_dir() / f"{safe}.json"


def write_snapshot(key: str, data: dict[str, Any]) -> None:
    """Persist a snapshot for ``key`` (best-effort; never raises into the caller)."""
    try:
        path = _key_to_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.parent.chmod(0o700)  # drafts hold post content/password: owner-only
        except OSError:
            pass
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps({**data, "key": key}), encoding="utf-8")
        tmp.replace(path)  # atomic swap so a crash mid-write can't corrupt the snapshot
    except OSError:
        pass


def read_snapshot(key: str) -> dict[str, Any] | None:
    try:
        data = json.loads(_key_to_path(key).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def clear_snapshot(key: str) -> None:
    try:
        _key_to_path(key).unlink()
    except OSError:
        pass


def list_snapshots() -> list[dict[str, Any]]:
    """Every stored snapshot, newest first by ``saved_at``."""
    out: list[dict[str, Any]] = []
    try:
        files = list(_draft_dir().glob("*.json"))
    except OSError:
        return out
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            out.append(data)
    out.sort(key=lambda s: s.get("saved_at", ""), reverse=True)
    return out

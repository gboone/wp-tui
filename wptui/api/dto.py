"""Data-transfer objects mirroring the raw REST API shapes we consume."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PostSummary:
    """A row in the post list."""

    id: int
    title: str
    status: str
    modified_gmt: str
    link: str

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "PostSummary":
        return cls(
            id=data["id"],
            title=_rendered(data.get("title")) or "(no title)",
            status=data.get("status", ""),
            modified_gmt=data.get("modified_gmt", ""),
            link=data.get("link", ""),
        )


@dataclass(frozen=True)
class PostDetail:
    """A single post opened for editing, carrying the raw block-grammar content."""

    id: int
    title_raw: str
    content_raw: str
    status: str
    modified_gmt: str
    link: str

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "PostDetail":
        return cls(
            id=data["id"],
            title_raw=_raw(data.get("title")),
            content_raw=_raw(data.get("content")),
            status=data.get("status", ""),
            modified_gmt=data.get("modified_gmt", ""),
            link=data.get("link", ""),
        )


def _rendered(field: dict[str, Any] | None) -> str:
    if not field:
        return ""
    return field.get("rendered", "") or ""


def _raw(field: dict[str, Any] | None) -> str:
    """Prefer ``raw`` (context=edit); fall back to ``rendered`` if absent."""
    if not field:
        return ""
    return field.get("raw", field.get("rendered", "")) or ""

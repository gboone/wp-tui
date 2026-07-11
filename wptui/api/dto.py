"""Data-transfer objects mirroring the raw REST API shapes we consume."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PostSummary:
    """A row in the post list."""

    id: int
    title: str
    status: str
    modified_gmt: str
    link: str
    post_type: str = "post"

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "PostSummary":
        return cls(
            id=data["id"],
            title=_rendered(data.get("title")) or "(no title)",
            status=data.get("status", ""),
            modified_gmt=data.get("modified_gmt", ""),
            link=data.get("link", ""),
            post_type=data.get("type", "post"),
        )


@dataclass(frozen=True)
class PostDetail:
    """A single post opened for editing, carrying raw content and editable settings."""

    id: int
    title_raw: str
    content_raw: str
    status: str
    modified_gmt: str
    link: str
    post_type: str = "post"
    slug: str = ""
    excerpt_raw: str = ""
    date: str = ""
    password: str = ""
    categories: tuple[int, ...] = ()
    tags: tuple[int, ...] = ()
    featured_media: int = 0
    parent: int = 0
    menu_order: int = 0
    template: str = ""

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "PostDetail":
        return cls(
            id=data["id"],
            title_raw=_raw(data.get("title")),
            content_raw=_raw(data.get("content")),
            status=data.get("status", ""),
            modified_gmt=data.get("modified_gmt", ""),
            link=data.get("link", ""),
            post_type=data.get("type", "post"),
            slug=data.get("slug", ""),
            excerpt_raw=_raw(data.get("excerpt")),
            date=data.get("date", ""),
            password=data.get("password", ""),
            categories=tuple(data.get("categories", []) or []),
            tags=tuple(data.get("tags", []) or []),
            featured_media=data.get("featured_media", 0) or 0,
            parent=data.get("parent", 0) or 0,
            menu_order=data.get("menu_order", 0) or 0,
            template=data.get("template", ""),
        )


@dataclass
class PostSettings:
    """The editor's in-memory, editable settings for one post/page.

    Seeded from a :class:`PostDetail` on load (so untouched fields round-trip), mutated by
    the settings screen, and serialized to a REST payload merged into the save request.
    ``to_payload`` emits only the keys valid for its ``post_type`` (categories/tags for
    posts; parent/menu_order/template for pages).
    """

    post_type: str = "post"
    status: str = "draft"
    slug: str = ""
    excerpt_raw: str = ""
    date: str = ""
    password: str = ""
    categories: list[int] = field(default_factory=list)
    tags: list[int] = field(default_factory=list)
    featured_media: int = 0
    parent: int = 0
    menu_order: int = 0
    template: str = ""

    @classmethod
    def from_detail(cls, detail: PostDetail) -> "PostSettings":
        return cls(
            post_type=detail.post_type or "post",
            status=detail.status or "draft",
            slug=detail.slug,
            excerpt_raw=detail.excerpt_raw,
            date=detail.date,
            password=detail.password,
            categories=list(detail.categories),
            tags=list(detail.tags),
            featured_media=detail.featured_media,
            parent=detail.parent,
            menu_order=detail.menu_order,
            template=detail.template,
        )

    def to_payload(self) -> dict[str, Any]:
        # Always send status, featured_media, and the type's id/list fields (all seeded
        # from load, so sending them back is idempotent and lets the user clear them).
        # String fields are sent only when non-empty so partial state can't wipe them.
        payload: dict[str, Any] = {"status": self.status, "featured_media": self.featured_media}
        if self.slug:
            payload["slug"] = self.slug
        if self.excerpt_raw:
            payload["excerpt"] = self.excerpt_raw
        if self.date:
            payload["date"] = self.date
        if self.password:
            payload["password"] = self.password
        if self.post_type == "page":
            payload["parent"] = self.parent
            payload["menu_order"] = self.menu_order
            if self.template:
                payload["template"] = self.template
        else:
            payload["categories"] = list(self.categories)
            payload["tags"] = list(self.tags)
        return payload


@dataclass(frozen=True)
class Term:
    """A taxonomy term (category or tag)."""

    id: int
    name: str
    taxonomy: str

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Term":
        return cls(
            id=data["id"],
            name=data.get("name", ""),
            taxonomy=data.get("taxonomy", ""),
        )


@dataclass(frozen=True)
class MediaItem:
    """An uploaded media library item."""

    id: int
    source_url: str
    alt: str = ""
    caption_raw: str = ""
    title_raw: str = ""
    mime: str = ""

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "MediaItem":
        return cls(
            id=data["id"],
            source_url=data.get("source_url", ""),
            alt=data.get("alt_text", ""),
            caption_raw=_raw(data.get("caption")),
            title_raw=_raw(data.get("title")),
            mime=data.get("mime_type", ""),
        )


def _rendered(field_value: dict[str, Any] | None) -> str:
    if not field_value:
        return ""
    return field_value.get("rendered", "") or ""


def _raw(field_value: dict[str, Any] | None) -> str:
    """Prefer ``raw`` (context=edit); fall back to ``rendered`` if absent."""
    if not field_value:
        return ""
    return field_value.get("raw", field_value.get("rendered", "")) or ""

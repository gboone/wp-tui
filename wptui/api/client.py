"""Async WordPress REST API client (self-hosted, Application Passwords)."""

from __future__ import annotations

import mimetypes
from collections.abc import Callable
from pathlib import Path
from types import TracebackType
from typing import Any

import httpx

from wptui.api.dto import MediaItem, PostDetail, PostSummary, PostSettings, Term
from wptui.api.errors import (
    AuthError,
    ConflictError,
    NetworkError,
    NotFoundError,
)
from wptui.config import SiteProfile

# Fields fetched for an editable post/page (context=edit gives the raw variants).
_POST_FIELDS = (
    "id,title,content,status,modified_gmt,link,type,slug,excerpt,date,"
    "password,categories,tags,featured_media,parent,menu_order,template"
)
_TYPE_PATH = {"post": "posts", "page": "pages"}


def _type_path(post_type: str) -> str:
    """REST collection segment for a post type (``post`` -> ``posts``)."""
    return _TYPE_PATH.get(post_type, "posts")


_IMAGE_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}


def _guess_mime(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in _IMAGE_MIME:
        return _IMAGE_MIME[ext]
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


class WordPressClient:
    """Thin async wrapper over ``/wp-json/wp/v2/`` using HTTP Basic auth.

    Use as an async context manager so the underlying httpx client is closed::

        async with WordPressClient(profile, app_password) as wp:
            posts = await wp.list_posts()
    """

    def __init__(
        self,
        profile: SiteProfile,
        app_password: str,
        *,
        timeout: float = 20.0,
    ) -> None:
        self._profile = profile
        # WordPress Application Passwords are shown with spaces for readability but
        # are validated with them stripped.
        self._client = httpx.AsyncClient(
            base_url=profile.api_root,
            auth=(profile.username, app_password.replace(" ", "")),
            timeout=timeout,
            headers={"Accept": "application/json"},
            follow_redirects=True,
        )

    async def __aenter__(self) -> "WordPressClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    # -- requests -----------------------------------------------------------

    async def _send(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Send a request, mapping transport failures to :class:`NetworkError` but NOT
        raising for an HTTP error status — the caller inspects the response itself. Used by
        :meth:`create_term` to read a ``term_exists`` 400 that carries the existing term id.
        """
        try:
            return await self._client.request(method, path, **kwargs)
        except httpx.HTTPError as err:  # connect/timeout/TLS/etc.
            raise NetworkError(str(err)) from err

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        response = await self._send(method, path, **kwargs)
        _raise_for_status(response)
        return response

    @staticmethod
    def _json(response: httpx.Response) -> Any:
        """Decode a JSON body, mapping a non-JSON 2xx to :class:`NetworkError`.

        A captive portal, security plugin, or reverse-proxy page can return HTTP 200
        with an HTML body; without this guard the raw ``JSONDecodeError`` would escape
        the async worker and crash the whole TUI.
        """
        try:
            return response.json()
        except ValueError as err:
            raise NetworkError(
                "The server returned a non-JSON response. Is this a WordPress REST API "
                "endpoint, and is the site reachable without a login/proxy page?"
            ) from err

    async def verify(self) -> dict[str, Any]:
        """Confirm credentials by fetching the authenticated user.

        Returns the ``/users/me`` payload. Raises :class:`AuthError` on 401/403.
        """
        response = await self._request("GET", "/users/me", params={"context": "edit"})
        data = self._json(response)
        if not isinstance(data, dict):
            raise NetworkError("Unexpected response shape from /users/me.")
        return data

    async def list_posts(
        self,
        *,
        status: str = "any",
        search: str | None = None,
        page: int = 1,
        per_page: int = 50,
    ) -> list[PostSummary]:
        params: dict[str, Any] = {
            "context": "edit",
            "status": status,
            "page": page,
            "per_page": per_page,
            "orderby": "modified",
            "order": "desc",
            "_fields": "id,title,status,modified_gmt,link,type",
        }
        if search:
            params["search"] = search
        response = await self._request("GET", "/posts", params=params)
        return _parse_list(self._json(response), PostSummary.from_json, "posts")

    async def get_post(self, post_id: int, post_type: str = "post") -> PostDetail:
        """Fetch one post/page with raw, editable content + settings (``context=edit``)."""
        params = {"context": "edit", "_fields": _POST_FIELDS}
        path = _type_path(post_type)
        response = await self._request("GET", f"/{path}/{post_id}", params=params)
        return _post_detail(self._json(response))

    async def create_post(
        self,
        post_type: str,
        *,
        title_raw: str = "",
        content_raw: str = "",
        settings: PostSettings | None = None,
    ) -> PostDetail:
        """Create a new post/page and return it. No conflict pre-check (nothing exists)."""
        payload: dict[str, Any] = {"title": title_raw, "content": content_raw}
        if settings is not None:
            payload.update(settings.to_payload())
        payload.setdefault("status", "draft")
        params = {"context": "edit", "_fields": _POST_FIELDS}
        path = _type_path(post_type)
        response = await self._request("POST", f"/{path}", params=params, json=payload)
        return _post_detail(self._json(response))

    async def update_post(
        self,
        post_id: int,
        *,
        content_raw: str | None = None,
        title_raw: str | None = None,
        settings: PostSettings | None = None,
        expected_modified_gmt: str | None = None,
    ) -> PostDetail:
        """Update a post/page's content, title, and/or settings.

        If ``expected_modified_gmt`` is given, re-check the server's current value
        first and raise :class:`ConflictError` if it changed (app-level lost-update
        guard — WordPress posts don't expose strong ETags).
        """
        post_type = settings.post_type if settings is not None else "post"
        if expected_modified_gmt is not None:
            current = await self.get_post(post_id, post_type)
            if current.modified_gmt != expected_modified_gmt:
                raise ConflictError(
                    "The post was modified on the server since you opened it.",
                    server_modified_gmt=current.modified_gmt,
                )

        payload: dict[str, Any] = {}
        if content_raw is not None:
            payload["content"] = content_raw
        if title_raw is not None:
            payload["title"] = title_raw
        if settings is not None:
            payload.update(settings.to_payload())

        params = {"context": "edit", "_fields": _POST_FIELDS}
        path = _type_path(post_type)
        response = await self._request(
            "POST", f"/{path}/{post_id}", params=params, json=payload
        )
        return _post_detail(self._json(response))

    # -- media --------------------------------------------------------------

    async def upload_media(
        self,
        file_path: str,
        *,
        title: str = "",
        alt: str = "",
        caption: str = "",
        description: str = "",
        timeout: float = 120.0,
    ) -> MediaItem:
        """Upload a local file to the media library in one multipart request.

        Uses an extended timeout since media POSTs can be large. Raises
        :class:`NetworkError` if the file can't be read or the server rejects it.
        """
        path = Path(file_path)
        try:
            data = path.read_bytes()
        except OSError as err:
            raise NetworkError(f"Cannot read file '{file_path}': {err}") from err
        files = {"file": (path.name, data, _guess_mime(path.name))}
        form: dict[str, str] = {}
        if title:
            form["title"] = title
        if alt:
            form["alt_text"] = alt
        if caption:
            form["caption"] = caption
        if description:
            form["description"] = description
        response = await self._request(
            "POST", "/media", files=files, data=form, timeout=timeout
        )
        return _media_item(self._json(response))

    async def get_media(self, media_id: int) -> MediaItem:
        """Fetch one media item (used to resolve a featured image for display)."""
        params = {"context": "edit", "_fields": "id,source_url,alt_text,caption,title,mime_type"}
        response = await self._request("GET", f"/media/{media_id}", params=params)
        return _media_item(self._json(response))

    async def list_media(
        self, search: str | None = None, *, per_page: int = 30
    ) -> list[MediaItem]:
        """List recent library images (newest first), optionally filtered by ``search``."""
        params: dict[str, Any] = {
            "context": "edit",
            "media_type": "image",
            "orderby": "date",
            "order": "desc",
            "per_page": per_page,
            "_fields": "id,source_url,alt_text,caption,title,mime_type",
        }
        if search:
            params["search"] = search
        response = await self._request("GET", "/media", params=params)
        return _parse_list(self._json(response), MediaItem.from_json, "media items")

    # -- taxonomy terms -----------------------------------------------------

    async def list_terms(
        self, taxonomy: str, search: str | None = None, *, per_page: int = 50
    ) -> list[Term]:
        """List terms for a taxonomy REST route (``categories`` or ``tags``)."""
        params: dict[str, Any] = {
            "context": "edit",
            "per_page": per_page,
            "_fields": "id,name,taxonomy",
            "orderby": "count",
            "order": "desc",
        }
        if search:
            params["search"] = search
        response = await self._request("GET", f"/{taxonomy}", params=params)
        return _parse_list(self._json(response), Term.from_json, "terms")

    async def create_term(self, taxonomy: str, name: str) -> Term:
        """Create a term, or return the existing one when the name already exists.

        The name is lowercased first so casing-only variants ("Apple" vs "apple") collapse to
        a single term. WordPress enforces term uniqueness by slug, so a duplicate name comes
        back as HTTP 400 ``term_exists`` carrying the existing ``term_id``; we resolve and
        return that term instead of raising, so an inline "add" of a name that already exists
        lands on the term the user meant rather than dead-ending on an error.
        """
        name = name.strip().lower()
        params = {"context": "edit", "_fields": "id,name,taxonomy"}
        response = await self._send(
            "POST", f"/{taxonomy}", params=params, json={"name": name}
        )
        if response.status_code == 400:
            term_id = _term_exists_id(response)
            if term_id is not None:
                return await self._get_term(taxonomy, term_id)
        _raise_for_status(response)
        data = self._json(response)
        if not isinstance(data, dict) or "id" not in data:
            raise NetworkError("Unexpected response creating a term.")
        return Term.from_json(data)

    async def _get_term(self, taxonomy: str, term_id: int) -> Term:
        """Fetch one term by id (resolves a ``term_exists`` collision to a real Term)."""
        params = {"context": "edit", "_fields": "id,name,taxonomy"}
        response = await self._request("GET", f"/{taxonomy}/{term_id}", params=params)
        data = self._json(response)
        if not isinstance(data, dict) or "id" not in data:
            raise NetworkError("Unexpected response fetching a term.")
        return Term.from_json(data)


def _parse_list(
    data: Any, from_json: Callable[[dict[str, Any]], Any], label: str
) -> list[Any]:
    """Coerce a JSON list body into DTOs, rejecting a non-list shape as a NetworkError.

    Shared by ``list_posts``/``list_media``/``list_terms`` so the list-shape guard and the
    skip-non-dict-entries rule stay identical across all three collection reads.
    """
    if not isinstance(data, list):
        raise NetworkError(f"Expected a list of {label} from the server.")
    return [from_json(item) for item in data if isinstance(item, dict)]


def _post_detail(data: Any) -> PostDetail:
    """Build a PostDetail, rejecting an unexpected body shape as a NetworkError."""
    if not isinstance(data, dict) or "id" not in data:
        raise NetworkError("Unexpected response shape for a post.")
    return PostDetail.from_json(data)


def _media_item(data: Any) -> MediaItem:
    """Build a MediaItem, rejecting an unexpected body shape as a NetworkError."""
    if not isinstance(data, dict) or "id" not in data:
        raise NetworkError("Unexpected response shape for a media item.")
    return MediaItem.from_json(data)


def _term_exists_id(response: httpx.Response) -> int | None:
    """Return the existing term id from a WordPress ``term_exists`` 400 body, else None.

    A duplicate-name POST returns ``{"code": "term_exists", "data": {"term_id": N}}``. WP has
    historically typed ``term_id`` as either an int or a numeric string, so accept both; a
    bool (an int subclass) is rejected so a stray ``true`` can't masquerade as id 1.
    """
    try:
        body = response.json()
    except ValueError:
        return None
    if not isinstance(body, dict) or body.get("code") != "term_exists":
        return None
    data = body.get("data")
    if not isinstance(data, dict):
        return None
    term_id = data.get("term_id")
    if isinstance(term_id, bool):
        return None
    if isinstance(term_id, int):
        return term_id
    if isinstance(term_id, str) and term_id.isdigit():
        return int(term_id)
    return None


def _raise_for_status(response: httpx.Response) -> None:
    if response.is_success:
        return
    code = response.status_code
    detail = _error_detail(response)
    if code in (401, 403):
        raise AuthError(detail or f"Authentication failed (HTTP {code}).")
    if code == 404:
        raise NotFoundError(detail or "Not found (HTTP 404).")
    raise NetworkError(detail or f"Request failed (HTTP {code}).")


def _error_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    if isinstance(body, dict):
        return str(body.get("message", "")) or ""
    return ""

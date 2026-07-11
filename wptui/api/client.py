"""Async WordPress REST API client (self-hosted, Application Passwords)."""

from __future__ import annotations

from types import TracebackType
from typing import Any

import httpx

from wptui.api.dto import PostDetail, PostSummary
from wptui.api.errors import (
    AuthError,
    ConflictError,
    NetworkError,
    NotFoundError,
)
from wptui.config import SiteProfile


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

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.HTTPError as err:  # connect/timeout/TLS/etc.
            raise NetworkError(str(err)) from err
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
            "_fields": "id,title,status,modified_gmt,link",
        }
        if search:
            params["search"] = search
        response = await self._request("GET", "/posts", params=params)
        data = self._json(response)
        if not isinstance(data, list):
            raise NetworkError("Expected a list of posts from the server.")
        return [PostSummary.from_json(item) for item in data if isinstance(item, dict)]

    async def get_post(self, post_id: int) -> PostDetail:
        """Fetch one post with raw, editable block content (``context=edit``)."""
        params = {
            "context": "edit",
            "_fields": "id,title,content,status,modified_gmt,link",
        }
        response = await self._request("GET", f"/posts/{post_id}", params=params)
        return _post_detail(self._json(response))

    async def update_post(
        self,
        post_id: int,
        *,
        content_raw: str | None = None,
        title_raw: str | None = None,
        expected_modified_gmt: str | None = None,
    ) -> PostDetail:
        """Update a post's raw content and/or title.

        If ``expected_modified_gmt`` is given, re-check the server's current value
        first and raise :class:`ConflictError` if it changed (app-level lost-update
        guard — WordPress posts don't expose strong ETags).
        """
        if expected_modified_gmt is not None:
            current = await self.get_post(post_id)
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

        params = {"context": "edit", "_fields": "id,title,content,status,modified_gmt,link"}
        response = await self._request(
            "POST", f"/posts/{post_id}", params=params, json=payload
        )
        return _post_detail(self._json(response))


def _post_detail(data: Any) -> PostDetail:
    """Build a PostDetail, rejecting an unexpected body shape as a NetworkError."""
    if not isinstance(data, dict) or "id" not in data:
        raise NetworkError("Unexpected response shape for a post.")
    return PostDetail.from_json(data)


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

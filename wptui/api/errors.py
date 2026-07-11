"""Typed exceptions surfaced from the API layer to the UI."""

from __future__ import annotations


class ApiError(Exception):
    """Base class for all API-layer errors."""


class NetworkError(ApiError):
    """Connection failed, timed out, or TLS/DNS error — the request never landed."""


class AuthError(ApiError):
    """Authentication or authorization failed (HTTP 401 / 403)."""


class NotFoundError(ApiError):
    """The requested resource does not exist (HTTP 404)."""


class ConflictError(ApiError):
    """The post changed on the server since we loaded it (lost-update guard)."""

    def __init__(self, message: str, *, server_modified_gmt: str | None = None) -> None:
        super().__init__(message)
        self.server_modified_gmt = server_modified_gmt

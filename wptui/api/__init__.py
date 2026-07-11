"""WordPress REST API client layer."""

from wptui.api.client import WordPressClient
from wptui.api.dto import MediaItem, PostDetail, PostSettings, PostSummary, Term
from wptui.api.errors import (
    ApiError,
    AuthError,
    ConflictError,
    NetworkError,
    NotFoundError,
)

__all__ = [
    "WordPressClient",
    "PostSummary",
    "PostDetail",
    "PostSettings",
    "Term",
    "MediaItem",
    "ApiError",
    "AuthError",
    "ConflictError",
    "NetworkError",
    "NotFoundError",
]

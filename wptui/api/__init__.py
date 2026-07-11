"""WordPress REST API client layer."""

from wptui.api.client import WordPressClient
from wptui.api.dto import PostDetail, PostSummary
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
    "ApiError",
    "AuthError",
    "ConflictError",
    "NetworkError",
    "NotFoundError",
]

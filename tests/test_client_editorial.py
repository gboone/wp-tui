"""Tests for editorial API surface: post/page create+update, media, and terms."""

from __future__ import annotations

import json

import httpx
import pytest

from wptui.api import MediaItem, PostSettings, Term
from wptui.api.client import WordPressClient
from wptui.api.errors import ApiError
from wptui.config import SiteProfile

POST_JSON = {
    "id": 7,
    "title": {"raw": "T"},
    "content": {"raw": "<p>x</p>"},
    "status": "draft",
    "modified_gmt": "2026-01-01T00:00:00",
    "link": "http://x/7",
    "type": "post",
}


def _client(handler, record=None):
    profile = SiteProfile(name="t", base_url="https://x.test", username="u")
    client = WordPressClient(profile, "pw pw")
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url=profile.api_root, auth=("u", "pwpw")
    )
    return client


def _body(request):
    return json.loads(request.content) if request.content else {}


# ------------------------------------------------------------------- create


async def test_create_post_targets_posts_and_returns_detail():
    seen = {}

    def handler(req):
        seen["url"] = str(req.url)
        seen["method"] = req.method
        return httpx.Response(201, json={**POST_JSON, "id": 42})

    client = _client(handler)
    detail = await client.create_post("post", title_raw="Hi", content_raw="<p>c</p>")
    assert seen["method"] == "POST"
    assert seen["url"].endswith("/wp/v2/posts?context=edit&_fields=" ) or "/wp/v2/posts" in seen["url"]
    assert detail.id == 42
    await client.aclose()


async def test_create_page_targets_pages_with_page_fields():
    captured = {}

    def handler(req):
        captured["url"] = str(req.url)
        captured["body"] = _body(req)
        return httpx.Response(201, json={**POST_JSON, "id": 9, "type": "page"})

    settings = PostSettings(post_type="page", status="draft", parent=3, menu_order=5, template="full-width.php")
    client = _client(handler)
    await client.create_post("page", title_raw="P", content_raw="", settings=settings)
    assert "/wp/v2/pages" in captured["url"]
    body = captured["body"]
    assert body["parent"] == 3 and body["menu_order"] == 5 and body["template"] == "full-width.php"
    # Page payloads must not carry post-only taxonomy keys.
    assert "categories" not in body and "tags" not in body
    await client.aclose()


# ------------------------------------------------------------------- update


async def test_update_post_merges_settings_and_content():
    captured = {}

    def handler(req):
        captured["url"] = str(req.url)
        captured["body"] = _body(req)
        return httpx.Response(200, json=POST_JSON)

    settings = PostSettings(post_type="post", status="publish", slug="my-slug", categories=[1, 2], tags=[5])
    client = _client(handler)
    await client.update_post(7, content_raw="<p>new</p>", title_raw="New", settings=settings)
    body = captured["body"]
    assert body["content"] == "<p>new</p>" and body["title"] == "New"
    assert body["status"] == "publish" and body["slug"] == "my-slug"
    assert body["categories"] == [1, 2] and body["tags"] == [5]
    assert "/wp/v2/posts/7" in captured["url"]
    await client.aclose()


async def test_get_post_requests_extended_fields_and_parses_settings():
    captured = {}

    def handler(req):
        captured["url"] = str(req.url)
        return httpx.Response(
            200,
            json={
                **POST_JSON,
                "slug": "s",
                "excerpt": {"raw": "ex"},
                "categories": [3, 4],
                "tags": [8],
                "featured_media": 11,
            },
        )

    client = _client(handler)
    detail = await client.get_post(7)
    assert "featured_media" in captured["url"] and "categories" in captured["url"]
    assert detail.slug == "s" and detail.excerpt_raw == "ex"
    assert detail.categories == (3, 4) and detail.tags == (8,) and detail.featured_media == 11
    settings = PostSettings.from_detail(detail)
    assert settings.categories == [3, 4] and settings.featured_media == 11
    await client.aclose()


async def test_malformed_create_response_raises_apierror():
    client = _client(lambda req: httpx.Response(200, json={"code": "rest_cannot_create"}))
    with pytest.raises(ApiError):
        await client.create_post("post", title_raw="x")
    await client.aclose()


# ------------------------------------------------------------- payload shaping


def test_settings_to_payload_omits_empty_strings_but_keeps_ids():
    s = PostSettings(post_type="post", status="draft", featured_media=0)
    payload = s.to_payload()
    assert payload["status"] == "draft"
    assert payload["featured_media"] == 0
    assert payload["categories"] == [] and payload["tags"] == []
    assert "slug" not in payload and "password" not in payload and "excerpt" not in payload

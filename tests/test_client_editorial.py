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


# ------------------------------------------------------------------- media (U2)

MEDIA_JSON = {
    "id": 31,
    "source_url": "https://x.test/wp-content/uploads/pic.png",
    "alt_text": "a pic",
    "caption": {"raw": "cap"},
    "title": {"raw": "pic"},
    "mime_type": "image/png",
}


async def test_upload_media_posts_multipart_with_metadata(tmp_path):
    f = tmp_path / "pic.png"
    f.write_bytes(b"\x89PNG\r\n\x1a\n fake bytes")
    captured = {}

    def handler(req):
        captured["method"] = req.method
        captured["url"] = str(req.url)
        captured["ctype"] = req.headers.get("content-type", "")
        captured["content"] = req.content
        return httpx.Response(201, json=MEDIA_JSON)

    client = _client(handler)
    media = await client.upload_media(str(f), title="pic", alt="a pic", caption="cap")
    assert captured["method"] == "POST" and "/wp/v2/media" in captured["url"]
    assert "multipart/form-data" in captured["ctype"]
    # The file bytes and the metadata fields are all in the multipart body.
    assert b"fake bytes" in captured["content"]
    assert b'name="alt_text"' in captured["content"] and b"a pic" in captured["content"]
    assert isinstance(media, MediaItem) and media.id == 31
    assert media.source_url.endswith("pic.png") and media.alt == "a pic"
    await client.aclose()


async def test_upload_media_missing_file_raises_before_request():
    called = {"n": 0}

    def handler(req):
        called["n"] += 1
        return httpx.Response(201, json=MEDIA_JSON)

    client = _client(handler)
    with pytest.raises(ApiError):
        await client.upload_media("/no/such/file.png")
    assert called["n"] == 0  # never hit the network
    await client.aclose()


async def test_non_json_media_response_raises():
    import tempfile

    client = _client(lambda req: httpx.Response(200, text="<html>nope</html>"))
    with tempfile.NamedTemporaryFile(suffix=".png") as tf:
        tf.write(b"x")
        tf.flush()
        with pytest.raises(ApiError):
            await client.upload_media(tf.name)
    await client.aclose()


def test_mime_guessing():
    from wptui.api.client import _guess_mime

    assert _guess_mime("a.PNG") == "image/png"
    assert _guess_mime("a.jpg") == "image/jpeg"
    assert _guess_mime("a.webp") == "image/webp"
    assert _guess_mime("a.unknownext") == "application/octet-stream"


# ------------------------------------------------------------------- terms (U2)


async def test_list_terms_searches_taxonomy_route():
    captured = {}

    def handler(req):
        captured["url"] = str(req.url)
        return httpx.Response(200, json=[{"id": 2, "name": "News", "taxonomy": "category"}])

    client = _client(handler)
    terms = await client.list_terms("tags", "new")
    assert "/wp/v2/tags" in captured["url"] and "search=new" in captured["url"]
    assert terms[0] == Term(2, "News", "category")
    await client.aclose()


async def test_create_term_posts_name_and_returns_term():
    captured = {}

    def handler(req):
        captured["url"] = str(req.url)
        captured["body"] = _body(req)
        return httpx.Response(201, json={"id": 99, "name": "Fresh", "taxonomy": "post_tag"})

    client = _client(handler)
    term = await client.create_term("tags", "Fresh")
    assert "/wp/v2/tags" in captured["url"] and captured["body"] == {"name": "Fresh"}
    assert term.id == 99 and term.name == "Fresh"
    await client.aclose()

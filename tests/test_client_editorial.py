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
    # Collection route (the "?" rules out /posts/{id}) with the edit context.
    assert "/wp/v2/posts?" in seen["url"] and "context=edit" in seen["url"]
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


async def test_get_existing_page_targets_pages_route():
    seen = {}

    def handler(req):
        seen["url"] = str(req.url)
        return httpx.Response(200, json={**POST_JSON, "id": 8, "type": "page"})

    client = _client(handler)
    detail = await client.get_post(8, "page")
    assert "/wp/v2/pages/8" in seen["url"] and detail.post_type == "page"
    await client.aclose()


async def test_update_existing_page_targets_pages_route():
    seen = {}

    def handler(req):
        seen["url"] = str(req.url)
        seen["body"] = _body(req)
        return httpx.Response(200, json={**POST_JSON, "id": 8, "type": "page"})

    settings = PostSettings(post_type="page", parent=2, menu_order=4, template="wide.php")
    client = _client(handler)
    # expected_modified_gmt=None -> no conflict pre-check GET; the single request is the update.
    await client.update_post(8, content_raw="<p>x</p>", title_raw="About", settings=settings)
    assert "/wp/v2/pages/8" in seen["url"]
    body = seen["body"]
    assert body["parent"] == 2 and body["template"] == "wide.php"
    assert "categories" not in body and "tags" not in body  # page payload, not post
    await client.aclose()
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


def test_settings_to_payload_sends_clearable_fields():
    # slug/excerpt/password are sent even when empty so the user can *clear* them
    # (removing a password must be able to lift protection). date is omitted when empty.
    s = PostSettings(post_type="post", status="draft", featured_media=0)
    payload = s.to_payload()
    assert payload["status"] == "draft"
    assert payload["featured_media"] == 0
    assert payload["categories"] == [] and payload["tags"] == []
    assert payload["slug"] == "" and payload["excerpt"] == "" and payload["password"] == ""
    assert "date" not in payload


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


async def test_list_media_lists_images_recent_first():
    captured = {}

    def handler(req):
        captured["url"] = str(req.url)
        return httpx.Response(200, json=[MEDIA_JSON, {**MEDIA_JSON, "id": 32}])

    client = _client(handler)
    items = await client.list_media()
    assert "/wp/v2/media" in captured["url"]
    assert "media_type=image" in captured["url"] and "orderby=date" in captured["url"]
    assert [m.id for m in items] == [31, 32]
    assert all(isinstance(m, MediaItem) for m in items)
    await client.aclose()


async def test_list_media_search_and_shape_guards():
    def handler(req):
        assert "search=cat" in str(req.url)
        # A list with a non-dict entry is tolerated (skipped), not crashed.
        return httpx.Response(200, json=[MEDIA_JSON, "junk"])

    client = _client(handler)
    items = await client.list_media("cat")
    assert [m.id for m in items] == [31]
    await client.aclose()


async def test_list_media_non_list_raises():
    client = _client(lambda req: httpx.Response(200, json={"code": "rest_error"}))
    with pytest.raises(ApiError):
        await client.list_media()
    await client.aclose()


async def test_create_term_lowercases_name_and_returns_term():
    captured = {}

    def handler(req):
        captured["url"] = str(req.url)
        captured["body"] = _body(req)
        return httpx.Response(201, json={"id": 99, "name": "fresh", "taxonomy": "post_tag"})

    client = _client(handler)
    term = await client.create_term("tags", "  Fresh  ")
    # The name is stripped + lowercased before it is sent, so casing-only variants collapse.
    assert "/wp/v2/tags" in captured["url"] and captured["body"] == {"name": "fresh"}
    assert term.id == 99 and term.name == "fresh"
    await client.aclose()


async def test_create_term_reuses_existing_on_term_exists():
    calls = []

    def handler(req):
        calls.append((req.method, str(req.url)))
        if req.method == "POST":
            # WordPress rejects a duplicate slug with 400 term_exists + the existing id.
            return httpx.Response(
                400,
                json={"code": "term_exists", "message": "exists",
                      "data": {"status": 400, "term_id": 42}},
            )
        return httpx.Response(200, json={"id": 42, "name": "apple", "taxonomy": "post_tag"})

    client = _client(handler)
    term = await client.create_term("tags", "Apple")  # different case than the stored "apple"
    assert term.id == 42 and term.name == "apple"
    # A duplicate name POSTs first, then resolves the existing term with a follow-up GET.
    assert calls[0][0] == "POST" and "/wp/v2/tags" in calls[0][1]
    assert calls[1][0] == "GET" and "/wp/v2/tags/42" in calls[1][1]
    await client.aclose()


async def test_create_term_handles_string_term_id():
    def handler(req):
        if req.method == "POST":
            return httpx.Response(
                400, json={"code": "term_exists", "data": {"term_id": "7"}}
            )
        return httpx.Response(200, json={"id": 7, "name": "news", "taxonomy": "category"})

    client = _client(handler)
    term = await client.create_term("categories", "News")
    assert term.id == 7
    await client.aclose()


async def test_create_term_non_term_exists_400_still_raises():
    def handler(req):
        return httpx.Response(400, json={"code": "rest_invalid_param", "message": "bad"})

    client = _client(handler)
    with pytest.raises(ApiError):
        await client.create_term("tags", "x")
    await client.aclose()

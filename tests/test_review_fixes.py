"""Regression tests for defects found in the code review (headless layer)."""

from __future__ import annotations

import pytest

from wptui.blocks import parse, propagate_dirty, serialize
from wptui.blocks.image import get_image_parts, set_image_parts
from wptui.blocks.model import Block
from wptui.inline import (
    document_to_html,
    document_to_markdown,
    html_to_document,
    markdown_to_document,
)


# --- #1: bold+italic markdown round-trip no longer drops/corrupts formatting ---


@pytest.mark.parametrize(
    "html",
    [
        "<strong><em>hi</em></strong>",
        "<em>a <strong>b</strong> c</em>",
        "<strong>a <em>b</em> c</strong>",
        "<em>x</em>",
        "<strong>y</strong>",
        'Intro <strong>bold</strong> and <em>em</em> then <code>k</code>.',
        '<a href="https://x.io"><strong>L</strong></a>',
    ],
)
def test_bold_italic_html_markdown_html_roundtrip(html):
    doc = html_to_document(html)
    # The path an edit actually takes: HTML -> markdown (shown) -> HTML (saved).
    back = document_to_html(markdown_to_document(document_to_markdown(doc)))
    assert back == html


def test_combined_mark_emits_triple_star():
    doc = html_to_document("<strong><em>hi</em></strong>")
    assert document_to_markdown(doc) == "***hi***"
    assert document_to_html(markdown_to_document("***hi***")) == "<strong><em>hi</em></strong>"


def test_italic_outer_no_longer_fuses_to_quad_star():
    doc = html_to_document("<em>a <strong>b</strong> c</em>")
    assert document_to_markdown(doc) == "*a **b** c*"


# --- #2: unterminated opener keeps the freeform text that preceded it ---------


def test_unterminated_opener_preserves_leading_freeform():
    doc = "hello <!-- wp:paragraph -->world"
    assert serialize(parse(doc)) == doc


def test_unterminated_opener_after_a_real_block():
    doc = "<!-- wp:paragraph -->\n<p>ok</p>\n<!-- /wp:paragraph -->\n\ntail <!-- wp:list -->rest"
    assert serialize(parse(doc)) == doc


# --- #7: dirty rebuild re-emits attribute bytes verbatim (no WP-encoding drift) ---


def test_dirty_container_preserves_untouched_attribute_bytes():
    # A cover (opaque) with an escaped URL, dirtied only because its child was edited.
    doc = (
        '<!-- wp:cover {"url":"https:\\/\\/site.com\\/bg.jpg","dimRatio":50} -->\n'
        "<div><!-- wp:paragraph --><p>hi</p><!-- /wp:paragraph --></div>\n"
        "<!-- /wp:cover -->"
    )
    blocks = parse(doc)
    cover = blocks[0]
    para = cover.inner_blocks[0]
    from wptui.blocks.text import set_editable_body

    set_editable_body(para, "edited")
    propagate_dirty(blocks)
    out = serialize(blocks)
    # The cover's URL keeps its exact WordPress escaping; only the paragraph changed.
    assert '{"url":"https:\\/\\/site.com\\/bg.jpg","dimRatio":50}' in out
    assert "<p>edited</p>" in out


def test_encode_attrs_escapes_comment_terminator():
    from wptui.blocks.serialize import _encode_attrs

    # Synthesized/edited attrs (no attributes_raw) must not let "--" break the delimiter.
    assert "--" not in _encode_attrs({"t": "a-->b"})
    assert "\\u002d\\u002d" in _encode_attrs({"t": "a--b"})


# --- #8 / #9: image attribute surgery is quote-agnostic and figure-safe --------


def test_single_quoted_img_attrs_read_and_write_cleanly():
    block = Block(block_name="core/image", inner_html="<figure><img src='a.jpg' alt='old'/></figure>")
    parts = get_image_parts(block)
    assert parts.src == "a.jpg" and parts.alt == "old"

    set_image_parts(block, src="a.jpg", alt="NEW", caption_html="")
    # No duplicate attributes injected; the value is updated in place.
    assert block.inner_html.count("alt=") == 1
    assert block.inner_html.count("src=") == 1
    assert "NEW" in block.inner_html


def test_caption_without_figure_wraps_in_one():
    block = Block(block_name="core/image", inner_html='<p><img src="a.jpg" alt=""/>x</p>')
    set_image_parts(block, src="a.jpg", alt="", caption_html="cap")
    assert "<figure><img" in block.inner_html
    assert '<figcaption class="wp-element-caption">cap</figcaption></figure>' in block.inner_html


# --- #3: a non-JSON 2xx body raises ApiError instead of crashing the worker ----


def _mock_client(handler):
    import httpx

    from wptui.api.client import WordPressClient
    from wptui.config import SiteProfile

    profile = SiteProfile(name="t", base_url="https://x.test", username="u")
    client = WordPressClient(profile, "pw pw")
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url=profile.api_root, auth=("u", "pwpw")
    )
    return client


async def test_non_json_response_raises_apierror():
    import httpx

    from wptui.api.errors import ApiError

    client = _mock_client(lambda req: httpx.Response(200, text="<html>login</html>"))
    with pytest.raises(ApiError):
        await client.list_posts()
    await client.aclose()


async def test_wrong_shape_response_raises_apierror():
    import httpx

    from wptui.api.errors import ApiError

    # 200 with an error object where a post is expected.
    client = _mock_client(lambda req: httpx.Response(200, json={"code": "rest_no_route"}))
    with pytest.raises(ApiError):
        await client.get_post(1)
    await client.aclose()


# --- #5: the conflict guard raises and issues no write when the post drifted ---


async def test_conflict_guard_blocks_write_on_stale_timestamp():
    import httpx

    from wptui.api.errors import ConflictError

    seen: list[str] = []

    def handler(request):
        seen.append(request.method)
        # The server's copy was modified after we loaded it.
        return httpx.Response(
            200,
            json={
                "id": 1,
                "title": {"raw": "T"},
                "content": {"raw": "x"},
                "status": "draft",
                "modified_gmt": "2026-02-02T00:00:00",
                "link": "http://x/1",
            },
        )

    client = _mock_client(handler)
    with pytest.raises(ConflictError) as exc:
        await client.update_post(1, content_raw="new", expected_modified_gmt="2026-01-01T00:00:00")
    assert exc.value.server_modified_gmt == "2026-02-02T00:00:00"
    assert "POST" not in seen  # the write must never be issued on conflict
    await client.aclose()


async def test_conflict_guard_allows_write_when_unchanged():
    import httpx

    def handler(request):
        return httpx.Response(
            200,
            json={
                "id": 1,
                "title": {"raw": "T"},
                "content": {"raw": "new"},
                "status": "draft",
                "modified_gmt": "2026-01-01T00:00:00",
                "link": "http://x/1",
            },
        )

    client = _mock_client(handler)
    detail = await client.update_post(
        1, content_raw="new", expected_modified_gmt="2026-01-01T00:00:00"
    )
    assert detail.content_raw == "new"
    await client.aclose()


# --- #4: the connect screen refuses to send credentials over http:// ----------


async def test_connect_refuses_plaintext_http(monkeypatch):
    import wptui.screens.connect as connect_mod
    from wptui.app import WPTuiApp

    connected: list = []
    monkeypatch.setattr(connect_mod, "list_profiles", lambda: [])
    monkeypatch.setattr(
        connect_mod, "WordPressClient", lambda *a, **k: connected.append(1) or object()
    )

    app = WPTuiApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.screen.query_one("#site-url").value = "http://example.com"
        app.screen.query_one("#username").value = "u"
        app.screen.query_one("#app-password").value = "pw pw"
        from wptui.screens.connect import ConnectScreen

        await pilot.click("#connect")
        await pilot.pause()
        # Credentials were never sent: no client constructed, still on the connect screen.
        assert connected == []
        assert isinstance(app.screen, ConnectScreen)


# --- HTTP status -> exception-type mapping (demoted test gap) ------------------


@pytest.mark.parametrize(
    "status,exc_name",
    [(401, "AuthError"), (403, "AuthError"), (404, "NotFoundError"), (500, "NetworkError")],
)
async def test_status_maps_to_exception_type(status, exc_name):
    import httpx

    import wptui.api.errors as errors

    client = _mock_client(lambda req: httpx.Response(status, json={"message": "nope"}))
    with pytest.raises(getattr(errors, exc_name)) as exc:
        await client.list_posts()
    assert "nope" in str(exc.value)  # server message surfaced
    await client.aclose()


# --- #16: dirtied empty opener/closer pair stays a pair (not void) -------------


def test_dirtied_empty_pair_does_not_become_void():
    block = parse("<!-- wp:x --><!-- /wp:x -->")[0]
    block.dirty = True
    assert serialize([block]) == "<!-- wp:x --><!-- /wp:x -->"


def test_parsed_void_block_stays_void_when_dirtied():
    block = parse('<!-- wp:spacer {"height":20} /-->')[0]
    block.dirty = True
    assert serialize([block]) == '<!-- wp:spacer {"height":20} /-->'


# --- #15: code span containing backticks round-trips -------------------------


@pytest.mark.parametrize(
    "html",
    ["<code>a`b</code>", "<code>``x``</code>", "<code>ends`</code>", "<strong><code>bc</code></strong>"],
)
def test_code_span_with_backticks_roundtrips(html):
    doc = html_to_document(html)
    back = document_to_html(markdown_to_document(document_to_markdown(doc)))
    assert back == html


# --- #14: a second save is ignored while one is in flight --------------------


async def test_reentrant_save_is_ignored():
    from wptui.app import WPTuiApp
    from wptui.screens.editor import EditorScreen

    class SlowClient:
        calls = 0

        async def get_post(self, pid):
            from wptui.api.dto import PostDetail

            return PostDetail(pid, "T", "<!-- wp:paragraph -->\n<p>x</p>\n<!-- /wp:paragraph -->",
                              "draft", "2026-01-01T00:00:00", "http://x/1")

        async def update_post(self, *a, **k):
            SlowClient.calls += 1
            from wptui.api.dto import PostDetail

            return PostDetail(1, "T", "", "draft", "2026-01-02T00:00:00", "http://x/1")

        async def aclose(self):
            pass

    from wptui.api.dto import PostSummary

    app = WPTuiApp()
    app.client = SlowClient()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(EditorScreen(PostSummary(1, "T", "draft", "2026-01-01T00:00:00", "http://x/1")))
        await pilot.pause()
        await pilot.pause()
        editor = app.screen
        editor._saving = True  # simulate a save already in flight
        editor._save()
        await pilot.pause()
        await pilot.pause()
        assert SlowClient.calls == 0  # the re-entrant save was ignored

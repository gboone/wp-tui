---
title: "feat: Post/page creation with editorial meta + image upload by filepath"
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan-bootstrap
created: 2026-07-11
type: feat
depth: deep
---

# feat: Post/page creation with editorial meta + image upload by filepath

## Summary

Extend wp-tui from an edit-only client into a full editorial tool. Two capabilities:

1. **Create new posts and pages** and edit the core built-in editorial settings for any
   post — status/visibility, slug, excerpt, publish date, categories & tags (posts), page
   parent/template/menu-order, and featured image — through a dedicated settings screen
   toggled by a keybinding.
2. **Upload an image from a local filepath**: the user adds an image block (or a featured
   image) by supplying a path — typed, pasted, or drag-dropped — is prompted for the
   optional media metadata (alt/caption/title/description), and the file is uploaded to
   the WordPress media library and referenced in the block, all in one flow.

Everything builds on the existing headless block engine (`wptui/blocks`, `wptui/inline`)
and the REST client (`wptui/api/client.py`). The lossless round-trip invariant is
preserved: new content is created via the block serializer, and image blocks are minted
from a factory so they serialize like any other block.

Product Contract preservation: this plan is solo-sourced (`ce-plan-bootstrap`); there is no
upstream brainstorm to preserve. Scope was confirmed with the user (see Scope Boundaries).

---

## Problem Frame

wp-tui today can only open and edit **existing** posts, and images can only reference
media already in the library (by URL). A real editorial workflow needs to create content
from scratch, set the metadata that determines how/where it publishes, and get local
images into the library without leaving the terminal. The REST API already exposes all of
this; the gap is entirely client-side: new API methods, three new screens/widgets, and a
filepath-normalization helper for terminal paste/drag semantics.

---

## Requirements

- **R1** — Create a new **post** or **page** from the post list and edit it in the block editor, saving as draft or publishing.
- **R2** — Edit core built-in settings for a post/page: status, visibility (public/private/password + password value), slug, excerpt, publish date.
- **R3** — Assign categories and tags to a post (multi-select; create a new tag/category inline).
- **R4** — Edit page-specific settings: parent page, template, menu order. Post-specific and page-specific fields show only for the relevant type.
- **R5** — Set a post/page **featured image**, reusing the filepath-upload flow (or referencing existing media).
- **R6** — All settings persist in the same save as the post content, and the existing conflict-detection guard still applies to edits.
- **R7** — Add an **image block** by supplying a local filepath; the file uploads to `/wp/v2/media` and the block references the returned media URL/id.
- **R8** — Before an uploaded image is inserted/saved, prompt for optional metadata (alt, caption, title, description); these are stored on the media item and reflected in the block.
- **R9** — Accept a filepath that is typed, pasted, or drag-dropped, and normalize terminal-supplied forms (surrounding quotes, backslash-escaped spaces, `file://` URIs, `~`, trailing newlines) before use.
- **R10** — Creating a new post issues no write until the first save (no orphan empty drafts), and skips the conflict pre-check (nothing to conflict with yet).

---

## Key Technical Decisions

- **KTD1 — Meta saved in the same request as content.** `EditorScreen` holds an in-memory `PostSettings`; the settings screen mutates it; `update_post`/`create_post` sends content, title, and all settings fields in one REST call. Keeps the conflict guard intact and avoids partial-save states. *Alternative rejected:* a separate "save settings" action — more round-trips, more conflict windows.
- **KTD2 — Create on first save, not on entry.** New-post editing tracks `post_id: int | None`; `None` means the first save POSTs to create (returning the id), later saves PUT. No orphan drafts if the user backs out; conflict pre-check is skipped while `post_id is None` (R10). *Alternative rejected:* create an empty draft on entry to get an id early — leaves litter and needs cleanup.
- **KTD3 — `post_type` threaded as data, endpoint chosen at the client edge.** `PostSummary`/`PostDetail`/`PostSettings` carry `post_type` (`"post"`/`"page"`); the client maps it to `/wp/v2/posts` vs `/wp/v2/pages`. The settings screen shows type-conditional fields. *Alternative rejected:* separate Post and Page classes — duplicates the editor for a mostly-shared surface.
- **KTD4 — Single multipart request for media upload.** `upload_media` sends `files={"file": (name, bytes, mime)}` plus `data={alt_text, caption, title, description}` to `/wp/v2/media` in one POST. *Alternative rejected:* POST binary then PUT metadata — two calls, a half-uploaded window.
- **KTD5 — One reusable upload modal.** `ImageUploadModal` (a `ModalScreen`) drives path → normalize → metadata prompt → upload → return `MediaItem`. Both inline image blocks and the featured-image field use it. Image blocks are minted via a `new_image_block(media)` factory so they serialize through the existing lossless path.
- **KTD6 — Filepath normalization is a headless util.** `wptui/paths.py` has no `textual` import, so terminal-escaping rules are unit-testable without a terminal (mirrors the `blocks`/`inline` headless rule). The Textual `Input` already coalesces bracketed paste into one value; we normalize that value on submit.
- **KTD7 — Separate settings screen (confirmed with user).** `PostSettingsScreen` is pushed over the editor by a keybinding and popped on escape; the shared `PostSettings` object carries edits back. Simpler focus/layout handling in Textual than a docked collapsible panel.
- **KTD8 — Upload uses a longer timeout than reads.** Media POSTs can be large; the upload path uses an extended per-request timeout rather than the client's default read timeout (see Risks).

---

## High-Level Technical Design

New client-side components and how they connect (existing components in plain text, new in **bold**):

```mermaid
graph TD
    PostList[PostListScreen] -- "n: new post/page" --> Editor[EditorScreen]
    PostList -- "enter: open existing" --> Editor
    Editor -- "ctrl+e" --> Settings[**PostSettingsScreen**]
    Editor -- "add image" --> Upload[**ImageUploadModal**]
    Settings -- "categories/tags" --> Terms[**TermPicker**]
    Settings -- "featured image" --> Upload
    Upload -- MediaItem --> Factory[**new_image_block / featured_media**]
    Editor -- "ctrl+s: create or update" --> Client[WordPressClient]
    Settings -. mutates .-> PS[**PostSettings (in editor)**]
    Client --> WP[(WordPress REST API)]
```

Image-upload sequence (R7–R9):

```mermaid
sequenceDiagram
    actor U as User
    participant M as ImageUploadModal
    participant P as paths.normalize_dropped_path
    participant C as WordPressClient
    participant WP as WP /wp/v2/media
    U->>M: paste/drag/type filepath
    M->>P: normalize(raw)
    P-->>M: clean absolute path
    M->>U: prompt alt/caption/title/description
    U-->>M: metadata (all optional)
    M->>C: upload_media(path, mime, metadata)
    C->>WP: POST multipart (file + fields)
    WP-->>C: 201 {id, source_url, ...}
    C-->>M: MediaItem
    M-->>U: return to editor; image block inserted
```

---

## Output Structure

New and modified files (repo-relative):

```
wptui/
  paths.py                      # NEW  filepath normalization (headless)
  api/
    dto.py                      # MOD  extend PostDetail; add PostSettings, Term, MediaItem
    client.py                   # MOD  create_post, upload_media, list/create term, get_media
    __init__.py                 # MOD  export new DTOs
  blocks/
    factory.py                  # MOD  new_image_block(media)
  screens/
    post_list.py                # MOD  "n" -> create post/page
    editor.py                   # MOD  create-mode, hold PostSettings, ctrl+e, save meta
    post_settings.py            # NEW  PostSettingsScreen
  widgets/
    term_picker.py              # NEW  categories/tags multi-select + create
    image_upload.py             # NEW  ImageUploadModal
    image_card.py               # MOD  "upload from file" affordance
tests/
  test_paths.py                 # NEW
  test_client_editorial.py      # NEW  create/meta/media/terms (httpx MockTransport)
  test_post_settings.py         # NEW
  test_image_upload.py          # NEW
  test_create_flow.py           # NEW  end-to-end new post -> save
```

---

## Implementation Units

Grouped into three phases: **A. API foundation** (U1–U3), **B. Editorial surface** (U4–U6),
**C. Media** (U7–U8).

### U1. Extend DTOs and post_type-aware post CRUD

**Goal:** Give the API layer a full editable post/page model and creation.
**Requirements:** R1, R2, R4, R6, R10, KTD1–KTD3.
**Dependencies:** none.
**Files:** `wptui/api/dto.py`, `wptui/api/client.py`, `wptui/api/__init__.py`, `tests/test_client_editorial.py`.
**Approach:**
- Extend `PostDetail` with the editable fields (all with defaults so existing construction keeps working): `post_type`, `slug`, `excerpt_raw`, `date`, `password`, `categories: list[int]`, `tags: list[int]`, `featured_media: int`, and page fields `parent`, `menu_order`, `template`. Extend `from_json` (excerpt via `_raw`; ids default to `[]`/`0`). Add `post_type` to `PostSummary`.
- Add a `PostSettings` frozen dataclass (the editor's in-memory settings model) plus a `to_payload()` that emits only the REST keys relevant to its `post_type`.
- `get_post(post_id, post_type="post")` and `update_post(...)` route to `/wp/v2/{posts|pages}/{id}`; extend `_fields` to fetch the new fields; `update_post` accepts a `settings: PostSettings | None` and merges its payload.
- `create_post(post_type, *, title_raw, content_raw, settings)` → `POST /wp/v2/{posts|pages}`, returns `PostDetail`. No conflict pre-check.
**Patterns to follow:** existing `_request`/`_json`/`_post_detail` in `wptui/api/client.py`; frozen-dataclass `from_json` in `dto.py`.
**Test scenarios:**
- Covers R1. `create_post("post", ...)` issues `POST /wp/v2/posts` and returns a `PostDetail` with the new id (MockTransport).
- Covers R1/R4. `create_post("page", ...)` targets `/wp/v2/pages` and includes `parent`/`menu_order`/`template` in the payload; `post`-only keys (categories/tags) are absent for pages and vice-versa.
- Covers R2/R6. `update_post` with a `PostSettings` merges settings keys and content into one request body; verify the JSON payload.
- `get_post` requests the extended `_fields` and populates `categories`/`tags`/`featured_media`/`excerpt_raw`.
- Malformed: a non-dict create/update response raises `ApiError` (reuse `_post_detail` guard).
**Verification:** unit tests green; a created post round-trips its fields through `to_payload()`.

### U2. Media upload and taxonomy term endpoints

**Goal:** Client methods to upload media and read/create taxonomy terms.
**Requirements:** R3, R5, R7, R8, KTD4.
**Dependencies:** U1 (DTOs, `_json`).
**Files:** `wptui/api/dto.py` (`MediaItem`, `Term`), `wptui/api/client.py`, `tests/test_client_editorial.py`.
**Approach:**
- `MediaItem` DTO: `id`, `source_url`, `alt`, `caption_raw`, `title_raw`, `mime`; `from_json`.
- `upload_media(path, *, title="", alt="", caption="", description="")`: read bytes, `mimetypes.guess_type`, `POST /wp/v2/media` with `files={"file": (basename, bytes, mime)}` and `data={...}` for the metadata; extended timeout (KTD8); returns `MediaItem`. Raise `ApiError` on a non-2xx / non-JSON body.
- `get_media(media_id)` → `MediaItem` (used to resolve a featured image's URL for display).
- `list_terms(taxonomy, search=None)` → `list[Term]` from `/wp/v2/{categories|tags}`; `create_term(taxonomy, name)` → `Term` via POST.
**Patterns to follow:** `_request`/`_json` guards; per-request timeout override via httpx.
**Test scenarios:**
- Covers R7/R8. `upload_media` posts multipart with the file part and the metadata fields; assert the request has a `file` part and `alt_text`/`caption`/`title` in the body; returns `MediaItem` from a 201.
- Covers R3. `list_terms("tags", "foo")` GETs `/wp/v2/tags?search=foo`; `create_term("tags", "bar")` POSTs and returns the new `Term`.
- Upload of a missing file raises a clear error before any request; non-JSON/`4xx` media response raises `ApiError`.
- MIME from extension: `.png`/`.jpg`/`.gif`/`.webp` map correctly; unknown extension falls back to `application/octet-stream`.
**Verification:** unit tests green against MockTransport.

### U3. Filepath normalization helper

**Goal:** Turn terminal-supplied path strings (typed/pasted/drag-dropped) into a usable absolute path.
**Requirements:** R9, KTD6.
**Dependencies:** none.
**Files:** `wptui/paths.py`, `tests/test_paths.py`.
**Approach:** `normalize_dropped_path(raw: str) -> str` that, in order: strips surrounding whitespace/newlines; removes one layer of matching single/double quotes; decodes a `file://` URI (percent-decode, drop host); unescapes shell backslash-escapes (`\ ` → space, `\\` → `\`); expands `~`. Return the cleaned path (not required to exist — existence is the caller's check). Add `looks_like_path(raw)` helper for the editor to distinguish a pasted path from pasted text if needed.
**Patterns to follow:** headless-module rule (no `textual` import), like `wptui/blocks`.
**Test scenarios:**
- Covers R9. Double- and single-quoted paths (`"…/a b.png"`, `'…/a b.png'`) → unquoted.
- Covers R9. Backslash-escaped spaces (`/home/u/a\ b.png`) → real spaces; `file:///home/u/a%20b.png` → `/home/u/a b.png`.
- `~/Pictures/x.png` expands to the home dir; trailing `\n`/spaces from bracketed paste are stripped.
- A plain already-clean absolute path is returned unchanged; an empty string returns empty.
**Verification:** unit tests green; property-style check that normalization is idempotent.

### U4. Editor create-mode and save-with-settings

**Goal:** Let the editor create new posts/pages and save content + settings together.
**Requirements:** R1, R6, R10, KTD1–KTD3.
**Dependencies:** U1.
**Files:** `wptui/screens/editor.py`, `wptui/screens/post_list.py`, `tests/test_create_flow.py`.
**Approach:**
- `EditorScreen` gains an optional create-mode: constructed with a `post_type` and no summary → `post_id = None`, empty canvas, empty `PostSettings`. Existing-open path unchanged.
- Hold `self._settings: PostSettings`. `_save`: if `post_id is None`, call `create_post(...)` (no conflict check) and adopt the returned id; else `update_post(..., settings=self._settings)`. Reuse the existing `_saving` guard and error handling.
- `PostListScreen`: bind `n` to a small type chooser (post vs page — a 2-option `Ask…`-style modal or two follow-up keys), then `push_screen(EditorScreen(post_type=...))`. On return, reload the list.
**Patterns to follow:** `EditorScreen._save` worker + conflict/except structure; `PostListScreen` BINDINGS and `push_screen`.
**Test scenarios:**
- Covers R1/R10. New-post editor with `post_id=None`: first `ctrl+s` calls `create_post` (not `update_post`) and no conflict pre-check fires; the returned id is adopted so a second save PUTs.
- Covers R6. Saving includes the in-memory `PostSettings` payload alongside content and title (RecordingClient asserts the merged fields).
- Backing out of a brand-new editor without saving issues no create call (no orphan draft).
- Create failure surfaces via the status line and does not crash the worker (reuse the broad-except guard).
**Verification:** end-to-end pilot test: open new-post editor, type content, save → one `create_post`; edit again → `update_post`.

### U5. Post settings screen

**Goal:** A dedicated screen to edit the core built-in settings, type-conditional.
**Requirements:** R2, R4, R5 (field only; upload wired in U8), R6, KTD7.
**Dependencies:** U4.
**Files:** `wptui/screens/post_settings.py`, `wptui/screens/editor.py` (keybinding + wiring), `tests/test_post_settings.py`, `wptui/app.tcss`.
**Approach:**
- `PostSettingsScreen(settings, post_type)` composes a form: `Select` for status; visibility control (public/private/password) + password `Input`; `Input` for slug; `TextArea`/`Input` for excerpt; date `Input`. Page-only: parent (post picker or id `Input` for v1), template `Select`, menu-order `Input`. Post-only fields (categories/tags via U6, featured image via U8) render only for `post_type == "post"` / where applicable.
- On escape/save-back, write field values into a new `PostSettings` and hand it to the editor (message or shared reference). `EditorScreen` binds `ctrl+e` to push it.
**Patterns to follow:** `ConnectScreen` form layout + `@on` handlers; `EditorScreen` binding/message patterns; `app.tcss` form styles.
**Test scenarios:**
- Covers R2. Editing status/slug/excerpt/visibility in the screen updates the editor's `PostSettings`; reopening shows the edited values.
- Covers R4. For `post_type="page"`, category/tag fields are absent and parent/template/menu-order are present; for `post_type="post"`, the reverse.
- Covers R2. Choosing "password" visibility reveals the password field and includes `status=private`/`password` in the settings payload appropriately.
- Escape returns to the editor without losing entered values.
**Verification:** pilot test drives the screen and asserts the editor's `PostSettings` reflects the edits and serializes into the next save.

### U6. Term picker (categories & tags)

**Goal:** Multi-select existing terms and create new ones inline.
**Requirements:** R3.
**Dependencies:** U2, U5.
**Files:** `wptui/widgets/term_picker.py`, `wptui/screens/post_settings.py` (wire in), `tests/test_post_settings.py`.
**Approach:** A `TermPicker` (modal or inline widget) parameterized by taxonomy: search box → `list_terms`, a checkable list for multi-select, and an "add new" action that calls `create_term` and selects it. Returns selected term ids into `PostSettings.categories`/`.tags`. v1 treats categories as a flat list (no hierarchy UI — see Scope Boundaries).
**Patterns to follow:** `PostListScreen` search+`DataTable` selection; `@work` for the term fetch.
**Test scenarios:**
- Covers R3. Searching lists matching terms; selecting two writes both ids into the settings.
- Covers R3. "Add new tag" calls `create_term` and includes the new id in the selection (RecordingClient).
- Empty search shows the default/first page of terms; a fetch error surfaces without crashing.
**Verification:** pilot test selects and creates terms; the resulting ids appear in the saved payload.

### U7. Image upload modal and block insertion

**Goal:** Add an image block by filepath, with a metadata prompt, uploading to the library.
**Requirements:** R7, R8, R9, KTD4–KTD6.
**Dependencies:** U2, U3.
**Files:** `wptui/widgets/image_upload.py`, `wptui/blocks/factory.py` (`new_image_block`), `wptui/screens/editor.py` (add-image action), `wptui/widgets/image_card.py`, `tests/test_image_upload.py`.
**Approach:**
- `ImageUploadModal(ModalScreen)`: a path `Input` (accepts paste/drag) → on submit, `normalize_dropped_path`; then reveal metadata inputs (alt/caption/title/description, all optional) → on confirm, `upload_media(...)`, return the `MediaItem`.
- `new_image_block(media)` in `factory.py`: build a `core/image` block whose inner HTML is `<figure class="wp-block-image"><img src="{url}" alt="{alt}" class="wp-image-{id}"/>…<figcaption>…</figcaption></figure>` and attributes `{"id": media.id, ...}`, dirty=True — reusing the existing image inner-HTML shape so `blocks/image.py` and the serializer handle it unchanged.
- `EditorScreen`: an "add image" action opens the modal; on return, insert the new block (reuse the canvas insertion path from `BlockCanvas`). `image_card.py` gains an "upload from file" affordance that opens the same modal to (re)assign its media.
**Patterns to follow:** existing `blocks/image.py` inner-HTML shape and `blocks/factory.py`; `BlockCanvas.insert_paragraph` for block insertion; `InlineMarkdownArea._on_paste` for paste handling reference.
**Test scenarios:**
- Covers R7/R8. Submitting a path + metadata calls `upload_media` with those fields and inserts a `core/image` block referencing the returned `source_url`/id (RecordingClient).
- Covers R9. A quoted/`file://`/backslash-escaped path pasted into the modal is normalized before upload (asserts the path passed to `upload_media`).
- Covers R7. The minted image block serializes losslessly through `serialize()` and reads back via `blocks/image.py get_image_parts` with the expected src/alt/caption.
- Upload failure keeps the modal open and shows an error; no block is inserted.
**Verification:** pilot test drives modal → upload (mock) → block appears in the canvas and serializes correctly.

### U8. Featured image via the upload flow

**Goal:** Set/clear a post's featured image using the same upload modal or an existing-media reference.
**Requirements:** R5.
**Dependencies:** U5, U7.
**Files:** `wptui/screens/post_settings.py`, `tests/test_post_settings.py`.
**Approach:** In `PostSettingsScreen`, a "featured image" field shows the current `featured_media` (resolve URL/filename via `get_media` for display) with actions to upload-from-file (open `ImageUploadModal`, store the returned id) or clear (set `0`). The id flows into `PostSettings.featured_media` and saves with the post.
**Patterns to follow:** U7 modal reuse; U5 settings-writeback.
**Test scenarios:**
- Covers R5. Upload-from-file in the settings screen sets `PostSettings.featured_media` to the returned media id and it appears in the save payload.
- Covers R5. Clearing sets `featured_media = 0` (WordPress convention for "no featured image") in the payload.
- Display resolves an existing `featured_media` id to a filename/URL via `get_media` without blocking the UI.
**Verification:** pilot test sets a featured image and confirms the id in the saved payload.

---

## Scope Boundaries

**In scope (confirmed with user):** creating posts and pages; core built-in settings
(status/visibility/password, slug, excerpt, date; page parent/template/menu-order);
categories & tags with inline create; featured image via upload; image blocks by filepath
upload with a metadata prompt; terminal path normalization.

**Deferred for later:**
- Custom (registered) post meta keys and custom taxonomies via REST schema discovery — explicitly out for v1 (user chose "core built-in fields").
- Category **hierarchy** UI (parent/child nesting); v1 assigns categories as a flat multi-select by id.
- A full media-library browser/search; v1 supports upload-new and set-by-id/URL only.
- Revisions, scheduling UI beyond a raw date field, autosave, and multi-image galleries.
- Streaming/chunked or progress-barred uploads (v1 does a single blocking multipart POST with an extended timeout).

**Deferred to Follow-Up Work (plan-local sequencing):** an in-editor block-type insertion menu entry for "image" beyond the add-image action; richer page-parent picker (v1 may use an id input if a picker proves heavy in U5).

---

## Risks & Dependencies

- **Upload size/timeout.** Large images can exceed the client's 20s default read timeout. *Mitigation:* per-request extended timeout on the media POST (KTD8); document that very large files may still fail and are out of v1 scope for chunking.
- **Server upload constraints.** Hosts vary in `upload_max_filesize`, allowed MIME types, and may require an `Authorization` header that some security plugins strip. *Mitigation:* surface the server's error message (reuse `_error_detail`); a clear failure, not a crash.
- **MIME detection.** `mimetypes.guess_type` can miss/mislabel; a wrong `Content-Type` can be rejected. *Mitigation:* map the common image extensions explicitly, fall back to `application/octet-stream`, and surface server rejection.
- **Terminal drag/paste variance.** Different terminals deliver dropped paths differently (quoting, `file://`, escaping, multi-file drops). *Mitigation:* `normalize_dropped_path` handles the common single-file forms; multi-file drops and exotic terminals are best-effort and noted. This is genuinely terminal-dependent and only partially unit-testable — normalization is tested on representative strings, not live drag events.
- **Conflict guard on create.** A create has no `modified_gmt`; the pre-check must be skipped when `post_id is None` (R10) or it would error.
- **Type-conditional fields.** Sending `categories` to `/pages` or `parent` to `/posts` is invalid. *Mitigation:* `PostSettings.to_payload()` emits only keys valid for its `post_type` (U1).
- **Dependency:** WordPress REST API v2 with Application Passwords (already in use); media upload requires the authenticated user to have `upload_files` capability.

---

## Verification Contract

- **Unit (headless):** `test_paths.py`, `test_client_editorial.py` (create/update/media/terms via `httpx.MockTransport`) pass; minted image blocks round-trip through `serialize()`/`blocks.image`.
- **Widget (pilot):** `test_create_flow.py`, `test_post_settings.py`, `test_image_upload.py` drive the real screens headlessly (as existing tests do) with a Recording/fake client — asserting the merged save payloads and inserted blocks, never hitting the network.
- **End-to-end (manual, against a real WP install):** create a new post, set status=draft, add a category and a tag, upload a local image into a block and as the featured image, save; confirm in wp-admin that the post exists with the right meta, the image is in the media library and referenced, and untouched blocks remain byte-identical on re-open.
- **Regression:** the full existing suite (currently 105 tests) stays green — the block/inline engines and existing edit/save path are unchanged.

## Definition of Done

- R1–R10 satisfied; each feature-bearing unit's test scenarios implemented and green.
- New posts and pages can be created and published; core settings + categories/tags + featured image are editable via the settings screen and persist in one save.
- An image block can be created from a typed/pasted/drag-dropped filepath with a metadata prompt, uploading to the library.
- Headless libraries (`wptui/paths.py`, `wptui/blocks`, `wptui/inline`) remain `textual`-free.
- Existing suite still green; new code covered by tests following the established patterns.

---

## Sources & Research

- Local: current `wptui/api/client.py` (`_request`/`_json`/`_post_detail`, conflict guard), `wptui/api/dto.py` (`from_json` DTOs), `wptui/screens/{editor,post_list,connect}.py` (screen/worker/binding patterns), `wptui/blocks/{image,factory,serialize}.py` (image inner-HTML shape + lossless round-trip), `wptui/widgets/inline_area.py` (`_on_paste` reference).
- WordPress REST API v2 (stable, known): `POST /wp/v2/{posts,pages}` (create), `POST /wp/v2/media` (multipart upload; `alt_text`/`caption`/`title`/`description` fields; `featured_media` on posts), `/wp/v2/categories` & `/wp/v2/tags` (terms). No external research was required — the endpoints are settled and already partially consumed by this client.

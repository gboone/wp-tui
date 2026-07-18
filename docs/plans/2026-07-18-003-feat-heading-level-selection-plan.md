---
title: "feat: Heading level selection (H1-H6)"
type: feat
status: implementation-ready
created: 2026-07-18
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-plan-bootstrap
---

# feat: Heading level selection (H1-H6)

## Summary

Let the user pick and change a heading's level (H1–H6). The `/` block switcher gains
`Heading 1`…`Heading 6` entries for creating a heading at a chosen level, and a new **F3**
trigger opens a small level picker that changes the focused heading's level **in place,
preserving its text**. The block label also starts showing the level (`heading 2`) so the
current level is visible.

The plumbing already exists — `new_heading_block(level)` supports any level and round-trip
preserves a heading's level across text edits — so this is purely the missing UI.

**Product Contract preservation:** N/A — solo plan (no upstream brainstorm).

---

## Problem Frame

WordPress stores a heading's level in two places: the wrapper tag (`<h2>`…`<h6>`) and, for
non-H2, a `{"level":N}` attribute (H2 is the default and omits it). wp-tui already preserves
both — a clean block re-emits verbatim, and editing a heading's text reuses the captured
wrapper (`wptui/blocks/text.py`), so an H3 stays an H3. But the UI never lets you *choose* a
level: the `/` switcher's single "Heading" entry always makes H2 (`wptui/blocks/switcher.py`),
there's no way to change an existing heading's level, and the block label reads only `heading`
so the level isn't even visible. This was deferred in the switcher plan ("Heading level
selection in the picker").

---

## Requirements

- **R1** — The `/` switcher offers `Heading 1` through `Heading 6`; selecting one on an empty
  block creates a heading at that level.
- **R2** — A reliable trigger (**F3**) opens a level picker for the focused heading; choosing
  a level changes that heading **in place**, keeping its text and inline formatting.
- **R3** — The level is stored WordPress-faithfully: wrapper tag `<hN>` plus `{"level":N}` for
  N≠2, and no `level` attribute for H2.
- **R4** — Changing a level does not disturb other blocks (the edited heading is dirty and
  rebuilds; everything else stays byte-identical).
- **R5** — The block label shows the level for headings (e.g. `heading 3`), updating when the
  level changes.
- **R6** — The F3 trigger is a no-op (nothing changes) when the focused block is not a heading.

---

## Key Technical Decisions

- **KTD1 — Headless `set_heading_level(block, level)`.** A pure helper co-located with
  `new_heading_block` in `wptui/blocks/factory.py` (so the two produce identical wrapper/attr
  shapes) rewrites the heading's wrapper tag and `level` attribute while preserving the body
  via the existing `split_wrapper` machinery. Marks the block dirty; sets `attributes_raw =
  None` so the changed attributes re-encode. Testable without a terminal.
- **KTD2 — F3 + a modal picker, reusing the established pattern.** Terminal key limits rule out
  `ctrl+digit`/`ctrl+shift+letter` (unreliable) and `ctrl+h` (backspace). A function key is
  reliable and F2 is already the Vim toggle, so **F3** opens a small `OptionList` level picker
  modeled on `BlockSwitcherModal` / `MediaPickerModal`. The picker is a thin view; the canvas
  applies the change. (User-specified approach.)
- **KTD3 — Create via the switcher, change via F3.** New headings flow through the existing
  `/` switcher (empty-block only); changing an existing heading needs a separate trigger
  because `/` types literally in a non-empty block. Both share the modal-picker look.
- **KTD4 — Level in the label from block attributes.** `TextBlockEditor` derives the label
  suffix from `block.attributes.get("level", 2)` for `core/heading`; a recompose after a level
  change refreshes it, so no extra wiring.

---

## Implementation Units

### U1. Headless `set_heading_level` helper

**Goal:** A pure function that changes a `core/heading` block's level in place, preserving its
body and matching WordPress's wrapper/attribute shape.

**Requirements:** R2, R3, R4

**Dependencies:** none

**Files:**
- `wptui/blocks/factory.py` (extend)
- `tests/test_factory.py` (extend)

**Approach:** Read the current body with `get_editable_body` (`wptui/blocks/text.py`), rebuild
`inner_html` as `\n<h{level} class="wp-block-heading">{body}</h{level}>\n` and `inner_content`
to match, set `attributes["level"] = level` for N≠2 (pop it for H2), set `attributes_raw =
None`, and mark dirty. Mirror the exact shape `new_heading_block` emits so a created-then-
changed heading and a directly-created one serialize identically.

**Patterns to follow:** `new_heading_block` and `_leaf_block` in `wptui/blocks/factory.py`;
`split_wrapper` / `get_editable_body` in `wptui/blocks/text.py`.

**Test scenarios:**
- H2 → H3: serialized output contains `{"level":3}` and `<h3 class="wp-block-heading">`; the
  body text is unchanged; `serialize(parse(serialize()))` is stable.
- H3 → H2: the `level` attribute is dropped and the wrapper is `<h2>`.
- A heading whose body contains inline formatting (`<strong>`) keeps that formatting after a
  level change.
- Result equals `new_heading_block(N)` bytes when applied to a freshly-built heading with the
  same body (consistency with the factory).

---

### U2. Heading levels in the block switcher

**Goal:** The `/` switcher lists `Heading 1`…`Heading 6`, each creating a heading at that level.

**Requirements:** R1

**Dependencies:** none

**Files:**
- `wptui/blocks/switcher.py` (modify the registry)
- `tests/test_block_switcher_registry.py` (extend)

**Approach:** Replace the single `Heading` registry entry with six `Heading N` entries, each
`lambda: new_heading_block(N)`, ordered H1–H6, with aliases (`h1`…`h6`, `heading 1`…, plus the
generic `heading`/`header`/`title` so typing `heading` surfaces all six). Keep the entries
contiguous in registry (display) order.

**Patterns to follow:** the existing `BlockType` entries and `match()` in
`wptui/blocks/switcher.py`.

**Test scenarios:**
- `match("h3")` returns exactly the Heading 3 entry; its factory yields a `core/heading` whose
  serialized form is H3.
- `match("heading")` returns all six heading entries in H1→H6 order.
- Each heading entry's factory produces the level its label names.
- Registry stays headless (the existing subprocess import guard still passes).

---

### U3. Heading level picker + F3 trigger

**Goal:** F3 opens a level picker for the focused heading and applies the chosen level in place.

**Requirements:** R2, R4, R6

**Dependencies:** U1

**Files:**
- `wptui/widgets/heading_level.py` (new modal)
- `wptui/widgets/canvas.py` (a `set_focused_heading_level` method)
- `wptui/screens/editor.py` (F3 binding + handler)
- `wptui/app.tcss` (modal styling, mirroring the switcher)
- `tests/test_heading_level.py` (new)

**Approach:** A `HeadingLevelModal(ModalScreen)` with an `OptionList` of `Heading 1`…`Heading 6`
(reuse `BlockSwitcherModal`'s shape and `DEFAULT_CSS`-for-test-harness approach), dismissing
with the chosen level or `None`. `EditorScreen` binds F3 (`priority=True`, like `ctrl+e`);
`action_heading_level` checks the focused top-level block is a `core/heading` (no-op otherwise),
pushes the modal, and on a result calls `canvas.set_focused_heading_level(N)`. That canvas
method locates the focused owner, applies `set_heading_level` (U1), and re-renders with focus
restored to the heading's editor.

**Patterns to follow:** `BlockSwitcherModal` (`wptui/widgets/block_switcher.py`); the F-key /
`priority=True` binding + `action_*` + modal-dismiss-callback flow in `wptui/screens/editor.py`
(`action_add_image` / `_do_convert`); `replace_block` focus handling in `wptui/widgets/canvas.py`.

**Test scenarios:**
- F3 on a focused heading opens `HeadingLevelModal`; choosing `Heading 4` makes the document
  serialize that block as H4 with the text preserved; focus returns to the heading editor.
- F3 on a non-heading block (paragraph) opens no modal / makes no change (R6).
- Dismissing the modal with Escape leaves the heading unchanged.
- Changing the level of one heading in a 3-block document leaves the other two byte-identical.

---

### U4. Show the heading level in the block label

**Goal:** The block label reads `heading N` for headings and refreshes when the level changes.

**Requirements:** R5

**Dependencies:** none

**Files:**
- `wptui/widgets/text_block.py` (label composition)
- `tests/test_text_block.py` (new or extend — create if absent)

**Approach:** In `TextBlockEditor.compose`, when the block is `core/heading`, append the level
from `block.attributes.get("level", 2)` to the label (`heading 2`). A recompose after a level
change (U3) re-derives it, so no extra refresh wiring.

**Patterns to follow:** the existing label line in `wptui/widgets/text_block.py`.

**Test scenarios:**
- A heading block with no `level` attribute labels as `heading 2`.
- A heading block with `{"level":4}` labels as `heading 4`.
- A non-heading block's label is unchanged (e.g. `paragraph`).

---

## Scope Boundaries

**In scope:** picking a level for new headings via `/`; changing a focused heading's level via
F3; WordPress-faithful storage; the level shown in the label.

### Deferred to Follow-Up Work
- **Markdown shorthand** (`## ` at the start of a paragraph → H2, `### ` → H3) as an alternative
  fast path to creating/leveling headings. Natural but separate from this UI.
- **Content-preserving conversion between arbitrary block types** (e.g. paragraph → heading
  keeping text). This plan changes level *within* headings only; cross-type text migration is
  the still-deferred switcher follow-up.

### Not in scope (non-goals)
- Changing levels of headings nested inside containers (quotes/groups) — F3 targets the focused
  top-level heading, consistent with the other structural ops.

---

## Verification

- New unit tests pass; the full suite stays green (`pytest`).
- Manual: `/` → `Heading 3` creates an H3; type text; press F3 → pick `Heading 5` → the heading
  becomes H5 with text intact; the label reads `heading 5`; save and confirm the level in
  WordPress with every other block byte-identical.
- Headless boundary holds: `set_heading_level` and the switcher registry import no `textual`.

---

## Sources & Research

- `wptui/blocks/factory.py` — `new_heading_block(level)`, the exact wrapper/attr shape U1 must
  match.
- `wptui/blocks/text.py` — `split_wrapper` / `get_editable_body`, reused to preserve the body.
- `wptui/blocks/switcher.py` — the `BlockType` registry U2 extends.
- `wptui/widgets/block_switcher.py` — the modal-picker pattern U3 mirrors.
- `wptui/screens/editor.py` — the F-key `priority` binding + modal-dismiss flow.
- `docs/plans/2026-07-18-001-feat-slash-block-switcher-plan.md` — deferred "Heading level
  selection in the picker," which this delivers.

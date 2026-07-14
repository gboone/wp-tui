---
date: 2026-07-14
topic: pipe-markdown-create-post
---

## Summary

Piping a markdown document into wp-tui (`cat notes.md | wp-tui`, `pbpaste | wp-tui`) parses it into real WordPress blocks — headings, lists, quotes, code, inline formatting — and opens the editor directly with that content, staged like any other new post until the user saves.

## Problem Frame

wp-tui is brand new, so there's no existing workflow for getting external content into it. The comparable habit is pasting into wp-admin's block editor: content copied from an LLM chat, an Obsidian note, or a Google Doc gets pasted straight into the browser editor and Gutenberg converts it into blocks on the spot. wp-tui has no equivalent today — the only way to add a heading, list, or quote block is to build it up by hand inside the running editor, one block at a time.

## Key Decisions

- **Detect piped input automatically, no explicit flag.** When stdin isn't a terminal, wp-tui treats it as markdown to import rather than requiring a subcommand or flag. Matches the invocation pattern this feature is built around (`pbpaste | wp-tui`) and keeps the common case frictionless.
- **Stage locally; create on first save.** Piped content populates a new, unsaved post exactly like pressing "new post" today — no WordPress API write happens until the user's first Ctrl+S. This preserves the existing convention that a new post issues no write until saved, so a bad or accidental pipe never litters the site with orphan drafts.
- **Convert to WordPress's block-comment HTML, then reuse the existing block parser.** Rather than hand-building a block tree, markdown gets rendered into the same `<!-- wp:heading -->…<!-- /wp:heading -->`-style text WordPress itself produces, then fed through the parser that already turns real WordPress content into the editable block tree. This inherits correctness (nested list structure, wrapper detection, content interleaving) from code already proven on real WordPress content instead of reimplementing it.
- **Skip image conversion in v1.** wp-tui has no existing path from an external image reference to an uploaded WordPress media-library item — that only happens today through the interactive media picker. Building automatic download-and-upload is a separate, larger effort, so markdown image syntax is simply not converted in this feature.
- **A leading H1 becomes the post title.** If the piped markdown opens with a single `#`-level heading, its text becomes the post title and it is not also rendered as a heading block in the body — matching how a markdown draft's title line is typically written. With no leading H1, the title starts blank, same as any new post today.
- **Fail loudly if the terminal can't be reattached.** Piping conflicts with how the TUI framework reads its own keyboard input from stdin. After reading the piped content, wp-tui must reattach its input to the controlling terminal to stay interactive; if that reattachment isn't possible, it exits with a clear error rather than launching a broken or half-interactive session.

## Requirements

**Invocation & input detection**
- R1. Running `wp-tui` with non-terminal stdin is detected automatically and treated as markdown content to import — no explicit flag or subcommand required.
- R2. The full piped input is read and buffered before the interactive UI takes over, after which the app's own keyboard/mouse input reattaches to the controlling terminal.
- R3. If no controlling terminal is available to reattach to, the app exits with a clear, specific error message instead of starting a broken or partially-interactive session.

**Markdown conversion**
- R4. Headings, paragraphs, lists (including basic nesting), blockquotes, and fenced code blocks convert to their corresponding WordPress core blocks.
- R5. Inline formatting inside converted blocks (bold, italic, code spans, links) is preserved via the existing inline markdown conversion.
- R6. Markdown image syntax is not converted into WordPress image blocks in v1.
- R7. Content with no recognizable markdown syntax — plain prose, or plain text pasted from a rich-text source like Google Docs or Word — converts to plain paragraph blocks without error, using the same conversion path as any other input.

**Title & post creation**
- R8. If the piped content opens with a single leading H1, its text becomes the post title, and that heading is not duplicated as a body block.
- R9. Absent a leading H1, the post title starts blank.
- R10. The post type defaults to "post".
- R11. No WordPress API write happens until the user's first save — the imported content behaves exactly like any other new, unsaved post (autosave/crash-recovery snapshotting included).

**Editor integration**
- R12. After the existing interactive connect flow completes (unchanged — same saved-profile picker as any other launch), a new-post editor pre-filled with the converted content opens as the first thing the user sees, sitting on top of the post list rather than replacing it.

## Acceptance Examples

- AE1. **Covers R1, R12.** Given `cat notes.md | wp-tui` where `notes.md` contains markdown headings and a list. When the app launches and the user completes the normal connect flow. Then a pre-filled editor with the converted blocks opens on top of the post list as the first thing the user sees.
- AE2. **Covers R8, R9.** Given piped markdown starting with `# My Post Title` followed by body content. When converted. Then the title field reads "My Post Title" and the body has no redundant heading block for it. Given piped markdown with no leading H1. When converted. Then the title field is blank.
- AE3. **Covers R3.** Given wp-tui is invoked in a context with no controlling terminal available. When it attempts to reattach input after reading the piped content. Then it exits with a clear error rather than opening a broken session.
- AE4. **Covers R6, R7.** Given content copied as plain text from a Google Doc, where headings and bold text were visually styled but carry no markdown syntax once copied as plain text. When converted. Then the result is plain paragraph blocks with no heading/list/bold structure — expected behavior, not an error.

## Scope Boundaries

**Deferred for later**
- Downloading and uploading markdown-referenced images to the WordPress media library.
- YAML frontmatter parsing for post metadata (tags, categories, status).
- Preserving Google Docs/Word rich formatting — that would require capturing the HTML/RTF clipboard flavor instead of plain text, a materially different and larger feature than markdown parsing.
- A file-path argument as an alternative to piping — stdin piping is the only invocation path in scope here.

## Dependencies / Assumptions

- Assumes a markdown parser (library or equivalent) is available for block-level splitting — detecting headings, lists, blockquotes, and fenced code boundaries. Exact choice is a planning decision.
- Assumes reattaching input to the controlling terminal (`/dev/tty`) after consuming piped stdin is feasible on the target platform; confirmed use case is a standard macOS terminal (Terminal.app, iTerm).
- Google Docs/Word content copied via a plain-text clipboard path (e.g. `pbpaste`) carries no markdown syntax — no `#`, no `**`, nothing — because those apps only encode formatting in a separate rich-text/HTML clipboard flavor. Converting to plain paragraphs in that case is expected, not a defect.

## Outstanding Questions

**Deferred to Planning**
- Which markdown parsing library or approach to use for block-level splitting.
- Exact fallback behavior for markdown constructs with no WordPress block equivalent (image syntax, tables, footnotes, raw HTML blocks) — literal text passthrough vs. silent drop vs. opaque block.
- How deeply nested lists need to be supported (single level vs. arbitrary nesting).
- The specific mechanism for detecting non-terminal stdin and reattaching to `/dev/tty`.

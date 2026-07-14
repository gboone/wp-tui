# wp-tui

A text-based terminal UI for interacting with a self-hosted WordPress site — browse
and edit posts, work with the block editor, and format text with markdown-style
shortcuts that map to WordPress's real inline formats. Mouse navigation throughout,
with an optional Vim-style key layer.

## Status

Early development. See `~/.claude/plans/resilient-zooming-pelican.md` for the full plan.

Implemented so far (Phase 0): connect to a site with an Application Password, list
posts, and view raw block content.

## Setup

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

## Run

```sh
python -m wptui
```

You'll be prompted for your site URL, username, and an
[Application Password](https://make.wordpress.org/core/2020/11/05/application-passwords-integration-guide/)
(WordPress Admin → Users → Profile → Application Passwords). The password is stored in
your OS keychain via `keyring`; only non-secret profile data is written to the config file.

For UI debugging, run `textual console` in another terminal and launch with
`textual run --dev wptui.app:WPTuiApp`.

### Pipe in a markdown draft

Piping markdown into wp-tui converts it to WordPress blocks and opens the editor with
that content pre-filled, as a new, unsaved post — nothing is written to WordPress until
you press Ctrl+S:

```sh
cat notes.md | python -m wptui
pbpaste | python -m wptui   # macOS: pipe the clipboard instead of a file
```

After you complete the normal connect flow, the post list opens as usual and the
pre-filled editor opens on top of it (post type is always "post"); pressing Escape pops
back to a live post list rather than exiting. A leading `# Title` heading, if present,
becomes the post title; everything else becomes body blocks.

## Test

```sh
pytest
```

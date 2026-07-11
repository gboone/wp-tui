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

## Test

```sh
pytest
```

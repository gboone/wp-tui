# wp-tui

A text-based terminal UI for interacting with a self-hosted WordPress site — create and
edit posts and pages, work with the native block editor, format text with markdown-style
shortcuts that map to WordPress's real inline formats, upload or pick images from the media
library, and edit post settings (status, slug, excerpt, categories/tags, featured image).
Mouse navigation throughout, with an optional Vim-style key layer.

## Requirements

- Python 3.12 or newer
- A self-hosted WordPress site with the REST API enabled, and an
  [Application Password](https://make.wordpress.org/core/2020/11/05/application-passwords-integration-guide/)
  (WordPress Admin → Users → Profile → Application Passwords). The site must be served over
  **HTTPS** — wp-tui refuses to send credentials over plaintext `http://`.

## Installation

The recommended install is with [pipx](https://pipx.pypa.io/) (isolated, cross-platform):

```sh
pipx install wptui
wptui
```

A Homebrew tap is planned:

```sh
# once the tap is published
brew install <owner>/tap/wptui
```

You'll be prompted for your site URL, username, and Application Password. The password is
stored in your OS keychain via `keyring`; only non-secret profile data is written to the
config file.

### Known limitation — headless/SSH

`keyring` needs an OS secret backend (macOS Keychain, Linux Secret Service, Windows
Credential Locker). On a headless machine reached over SSH with no Secret Service running,
credential storage will fail, so wp-tui cannot save or load the Application Password there.
This affects any install method; it is a runtime environment limitation, not a packaging
one.

## From source (development)

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
python -m wptui
```

For UI debugging, run `textual console` in another terminal and launch with
`textual run --dev wptui.app:WPTuiApp`.

## Test

```sh
pytest
```

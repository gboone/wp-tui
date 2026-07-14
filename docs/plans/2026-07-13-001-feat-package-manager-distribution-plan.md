---
title: "Package-manager distribution (pipx / Homebrew) - Plan"
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
execution: code
product_contract_source: ce-brainstorm
created: 2026-07-13
type: feat
depth: standard
---

# Package-manager distribution (pipx / Homebrew) - Plan

Enriched from the requirements-only brainstorm on 2026-07-13. **Product Contract unchanged**
(requirements, scope boundaries, and success criteria below are carried forward verbatim);
this pass adds the Planning Contract, Implementation Units, and Verification Contract.

## Goal Capsule

**Objective:** Make wp-tui installable with a single command for the author and a few
others, cross-platform (macOS, Linux desktop, Linux over SSH), with minimal ongoing
maintenance. The foundation is publishing to **PyPI** so `pipx install wptui` works
everywhere; a **personal Homebrew tap** is a follow-on nicety for macOS users.

**Product authority:** Solo project; the author decides scope and release cadence.

**Open blockers:** None. Prerequisites verified: repo is local-only (no git remote), no
`LICENSE`, no tags. PyPI name `wptui` is available (verified 404).

---

## Product Contract

### Problem Frame

wp-tui runs today only from a cloned repo inside its dev virtualenv (`python -m wptui`).
There is no way for someone else — or the author on another machine — to install it with a
normal package-manager command. It is already well-positioned for distribution: pure
Python (no compiled extensions), a declared `wptui` console entry point (`pyproject.toml`
`[project.scripts]`), and pip-installable dependencies. The gap is packaging and
publishing, not code changes to the app itself.

### Requirements

- **R1** — Publish wp-tui to PyPI so that `pipx install wptui` installs a working `wptui` command on macOS and Linux (desktop and over SSH).
- **R2** — Provide a **personal Homebrew tap** so macOS/Linux Homebrew users can `brew install <owner>/tap/wptui`. Follow-on that depends on R1's published artifact; R1 can ship first and stand alone.
- **R3** — Host the source on a git host (GitHub assumed) — a prerequisite for tagged releases and for the tap formula to reference a source tarball. The repo is currently local-only.
- **R4** — Add a **GPL (GPLv3)** `LICENSE` file and matching license metadata, so the project is publishable and its terms are explicit.
- **R5** — Update the README with installation instructions (pipx, and the tap once it exists) **and** a documented caveat: on a headless machine over SSH with no Secret Service, credential storage via `keyring` will not work.
- **R6** — Establish a repeatable release path: version tagging plus build artifacts (wheel + sdist) that serve as the source for both the PyPI upload and the tap formula. Light enough to run occasionally by hand.

### Scope Boundaries

**In scope:** the pipx/PyPI foundation (R1), the personal Homebrew tap follow-on (R2), and
the enabling prerequisites (R3–R6): git host, GPLv3 license, README install docs + caveat,
and a manual release/build path.

**Deferred to Follow-Up Work:**
- The Homebrew tap (R2) is staged *after* the PyPI publish (R1) — shipping only R1 already satisfies the core goal.
- Automating releases (CI-driven publish + automatic formula version/sha bump). Manual is acceptable for the initial cadence; automation is a later convenience. See U5's note on PyPI Trusted Publishing as the intended automation shape.

**Outside this product's identity (non-goals):**
- **Other channels:** apt/`.deb` + an apt repo/PPA, Flatpak, and submission to **homebrew-core** (the public no-tap `brew install wptui`). Ceremony/maintenance out of proportion to a low-traffic solo tool.
- **Standalone/frozen binary** (PyInstaller/shiv/pex). Reconsider only if the audience becomes non-technical.
- **Windows** support.
- **A keyring credential fallback for headless SSH.** App behavior unchanged; the limitation is documented (R5) and left as a separate potential effort.

### Success Criteria / Acceptance Examples

- **AE1** — On a clean macOS machine with Python 3.12+, `pipx install wptui` then running `wptui` launches the app (reaches the connect screen).
- **AE2** — On a clean Linux machine (a desktop session and a plain SSH session), `pipx install wptui` then `wptui` launches. Where a keyring backend exists, saving/loading the Application Password works; the SSH-without-backend case behaves per the documented caveat rather than surprising the user.
- **AE3** — (Follow-on, R2) On macOS, `brew install <owner>/tap/wptui` then `wptui` launches the app.
- **AE4** — The README shows the install command(s) and states the headless-SSH/keyring caveat.

### Known Caveats

- **Headless SSH + keyring:** wp-tui stores the WordPress Application Password via `keyring` (`wptui/config.py`), which needs an OS secret backend (macOS Keychain, Linux Secret Service, Windows Credential Locker). On a headless server over SSH there is often no Secret Service, so credential storage fails. Installation via any channel does not change this; documented and deferred (non-goal).

---

## Planning Contract

### Key Technical Decisions

- **KTD1 — License is `GPL-3.0-or-later` (SPDX), expressed via PEP 639.** Add a `license` SPDX expression + a full GPLv3 `LICENSE` file + the OSI classifier. wp-tui's runtime deps (Textual, httpx, keyring, platformdirs) are permissively licensed, so GPLv3 is compatible. *Note:* the SPDX `license` string needs a recent build backend (setuptools ≥ 77); if the pinned backend is older, bump it or fall back to the license classifier + `license-files` (resolve at execution — see Deferred).
- **KTD2 — Manual build + publish with a TestPyPI dry-run.** Build wheel+sdist with `python -m build`; validate with `twine check`; upload to **TestPyPI** and install from there as a rehearsal; then `twine upload` to real PyPI. Rationale: lowest carrying cost for an occasional, low-cadence release. CI/Trusted-Publishing automation is deferred, not designed away.
- **KTD3 — Homebrew via a personal tap, not homebrew-core.** A `homebrew-*` repo with a formula using `virtualenv_install_with_resources` (deps pinned as `resource` blocks), pointing at the published PyPI sdist. Rationale: a solo tool sits below homebrew-core's notability/maintenance bar; a personal tap is the idiomatic low-maintenance answer.
- **KTD4 — Distribution name stays `wptui`.** Verified available on PyPI. If it were ever taken, keep the `wptui` *command* (the `[project.scripts]` entry) and change only the distribution name — the install command would change, the run command would not.
- **KTD5 — Document `pipx` as the primary install, not raw `pip`.** pipx gives an isolated, cross-platform, upgradable CLI install; it is the actual "package manager" answer for a Python TUI, with the Homebrew tap as a macOS nicety on top.

---

## Implementation Units

Sequence: **U1 + U2** (metadata + docs, independent of each other) → **U3** (git host + tag)
→ **U4** (publish, the R1 payoff) → **U5** (tap follow-on). Most units are packaging/config,
so they are verified by build/install/runtime smoke checks rather than unit tests.

### U1. PyPI-ready packaging metadata + GPLv3 LICENSE

**Goal:** Make the package publish cleanly with a good PyPI page and an explicit license.
**Requirements:** R4; enables R1, R6.
**Dependencies:** none.
**Files:** `pyproject.toml`, `LICENSE` (new).
**Approach:** Add to `[project]`: the `license` SPDX expression (`GPL-3.0-or-later`, per KTD1),
`authors`, `keywords`, `classifiers` (Python 3.12, `Environment :: Console`, the GPLv3 OSI
license classifier, macOS + POSIX operating systems), and `[project.urls]` (Homepage /
Repository / Issues — fill once the git host from U3 is known, or use placeholders resolved
in U3). `readme = "README.md"` is already set. Create `LICENSE` with the full GPLv3 text.
Confirm the build backend supports the SPDX `license` field (bump `setuptools` in
`[build-system].requires` if needed, per KTD1).
**Patterns to follow:** the existing `[project]` table in `pyproject.toml`.
**Execution note:** packaging/config — verify by building, not unit tests.
**Test scenarios:**
- `python -m build` produces both a wheel and an sdist without error.
- `twine check dist/*` passes (metadata valid; the README renders as the long description).
- Covers AE1 (partial). Installing the built wheel into a throwaway env exposes a `wptui` command that launches.
- `LICENSE` contains the GPLv3 text and the `pyproject` license metadata matches it (no license/classifier contradiction).
**Verification:** `python -m build` + `twine check` succeed; the wheel carries the GPLv3 license metadata and a working entry point.

### U2. README install docs + SSH/keyring caveat

**Goal:** Document how to install and the one behavioral caveat that install can't fix.
**Requirements:** R5 (AE4).
**Dependencies:** none (cross-references U4/U5 commands, which can be written ahead).
**Files:** `README.md`.
**Approach:** Add an **Installation** section leading with `pipx install wptui`, plus the
Homebrew tap command as a "once available" note (`brew install <owner>/tap/wptui`). Add a
short **Known limitations** note: `keyring` needs an OS secret backend, so on a headless
machine over SSH with no Secret Service, saving/loading the Application Password won't work.
State the Python 3.12+ requirement for the pipx path.
**Patterns to follow:** the existing `README.md` structure.
**Execution note:** docs; verify by rendering + `twine check` (README is the PyPI long description).
**Test scenarios:**
- Covers AE4. The README shows `pipx install wptui` and the tap command, and states the SSH/keyring caveat.
- `twine check` confirms the README renders as a valid long description (no reST/markdown errors).
**Verification:** README reads clearly and renders on the PyPI page after publish.

### U3. Git host + tagged release

**Goal:** Put the source on a git host and cut a versioned release — the prerequisite for the tap and for release hygiene.
**Requirements:** R3, R6.
**Dependencies:** U1 (so the tag captures the packaging metadata).
**Files:** none in-repo (git host operations); confirm `.gitignore` already excludes `.venv`/build artifacts (it does).
**Approach:** Create the remote repository on the chosen host (GitHub assumed), add it as
`origin`, push `master`. Create an annotated tag matching the `pyproject` version
(`v0.1.0`) and a GitHub Release from it (the release tarball is a stable source the tap can
reference). Backfill `[project.urls]` in `pyproject.toml` (U1) with the real repo URL.
**Execution note:** creating the remote repo and authenticating are the **user's** account
actions; the implementer performs the local git wiring (remote, push, tag) and guides the
host steps. Do not fabricate a remote URL — obtain it from the user.
**Test scenarios:**
- The repository is visible on the host with `master` pushed.
- Tag `v0.1.0` exists and a Release is published from it.
- `[project.urls]` now points at the real repository.
**Verification:** repo + `v0.1.0` release exist on the host; URLs in `pyproject` resolve.

### U4. Build and publish to PyPI; verify pipx install

**Goal:** Publish wp-tui to PyPI so `pipx install wptui` works everywhere (the R1 payoff).
**Requirements:** R1 (AE1, AE2), R6.
**Dependencies:** U1 (metadata), U3 (version/tag alignment).
**Files:** none new (operates on `dist/` build artifacts).
**Approach:** Per KTD2 — build wheel+sdist, `twine check`, upload to **TestPyPI**, and
rehearse `pipx install` from TestPyPI. Then `twine upload` to real PyPI. Requires a PyPI
account + API token (the user's). After publish, verify a clean `pipx install wptui` on
macOS and Linux yields a launching `wptui`.
**Execution note:** needs the user's PyPI account/token. Do the TestPyPI dry-run **and** a
local `pipx install ./dist/*.whl` smoke test before the real upload. Packaging work — the
proof is a successful install + launch, not unit tests.
**Test scenarios:**
- `pipx install ./dist/<wheel>` in a clean environment installs a `wptui` that launches (pre-publish smoke).
- Install from TestPyPI succeeds (dry-run of the real flow).
- Covers AE1. On clean macOS with Python 3.12+, `pipx install wptui` → `wptui` reaches the connect screen.
- Covers AE2. On clean Linux (desktop and SSH), `pipx install wptui` → `wptui` launches; keyring works where a backend exists; the SSH-no-backend case matches the documented caveat, not a crash.
**Verification:** `wptui` appears on `pypi.org`; `pipx install wptui` produces a working command on both platforms.

### U5. Personal Homebrew tap + formula (follow-on)

**Goal:** `brew install <owner>/tap/wptui` on macOS/Linux Homebrew.
**Requirements:** R2 (AE3).
**Dependencies:** U4 (the formula references the published PyPI sdist).
**Files:** a **separate** repository — `homebrew-tap` (or `homebrew-wptui`) — containing
`Formula/wptui.rb`. **Target repo: the new tap repo, not wp-tui.**
**Approach:** Create the tap repo. Author a formula using `virtualenv_install_with_resources`
with `depends_on "python@3.12"`; generate the dependency `resource` blocks from the
published release (Homebrew's Python-resource tooling), and point `url`+`sha256` at the
`wptui` sdist on PyPI. Include a `test do` block that runs a non-interactive check (e.g. the
CLI's version/help path) so `brew test` has something to assert.
**Execution note:** generate the formula/resources against the *published* sdist (U4 must be
done). The implementer authors the formula in the tap repo; the user owns the tap repo
creation on their host.
**Test scenarios:**
- Covers AE3. `brew install <owner>/tap/wptui` on clean macOS installs and `wptui` launches.
- `brew audit --strict --new <formula>` passes (formula hygiene).
- `brew test wptui` runs the formula's test block successfully.
- The pinned `sha256` matches the published sdist (install fails loudly on mismatch).
**Verification:** a clean `brew install <owner>/tap/wptui` yields a launching `wptui`; audit/test pass.

---

## Verification Contract

- **Build/metadata:** `python -m build` yields wheel+sdist; `twine check dist/*` passes.
- **Pre-publish smoke:** `pipx install ./dist/<wheel>` in a clean env → `wptui` launches; TestPyPI install rehearsal succeeds.
- **Published (R1):** `pipx install wptui` on clean macOS and Linux (desktop + SSH) → `wptui` launches (AE1, AE2); credential storage works where a keyring backend exists.
- **Docs (R5):** README shows the install commands and the SSH/keyring caveat, and renders on the PyPI page (AE4).
- **Release hygiene (R3, R6):** repo on a git host with a `v0.1.0` release; `pyproject` URLs resolve.
- **Follow-on (R2):** `brew install <owner>/tap/wptui` → `wptui` launches (AE3); `brew audit --strict` and `brew test` pass.
- **Regression:** the existing app test suite (currently 161 passing) stays green after the `pyproject`/metadata changes (packaging shouldn't affect runtime, but confirm once).

## Definition of Done

- R1–R6 satisfied. `pipx install wptui` installs a working `wptui` on macOS and Linux (desktop + SSH).
- `LICENSE` (GPLv3) present and consistent with `pyproject` license metadata; the package builds and `twine check` passes.
- README documents install (pipx now, tap once shipped) + the headless-SSH/keyring caveat.
- Repo is on a git host with a `v0.1.0` release; wp-tui is live on PyPI.
- (Follow-on) the personal Homebrew tap installs a working `wptui` and passes `brew audit`/`brew test`.
- Existing test suite still green.

### Deferred to Implementation

- **Exact SPDX-vs-classifier license mechanics** depend on the resolved build-backend version (KTD1) — decide `license = "GPL-3.0-or-later"` vs classifier + `license-files` when touching `pyproject`.
- **Git host + repo URL** are the user's to provide (U3); `[project.urls]` values are filled then.
- **PyPI / TestPyPI credentials** are the user's; Trusted Publishing (GitHub Actions OIDC) is the intended later automation shape (deferred) that would replace the manual `twine upload`.
- **Formula resource list** is generated against the published sdist and must be regenerated on dependency bumps.

---

## Sources & Research

- Local: `pyproject.toml` — pure-Python package, `wptui = "wptui.__main__:main"` console entry point, `requires-python = ">=3.12"`, setuptools build backend, no `license` field yet; `README.md` (41 lines, needs an install section); `wptui/config.py` — `keyring` credential storage (the SSH caveat); no `.github/workflows`, no `LICENSE`, no git remote/tags (verified).
- Verified during brainstorm/planning: PyPI `wptui` name free (404); `build`/`twine` not yet installed.
- Standard Python packaging practice (no external research required): `python -m build` + `twine` for PyPI; TestPyPI as a rehearsal index; pipx as the cross-platform CLI installer; personal Homebrew taps via `virtualenv_install_with_resources`; PEP 639 SPDX license metadata; PyPI Trusted Publishing as the eventual CI automation.

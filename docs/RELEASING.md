# Releasing wp-tui

The version lives in **one place**: `version` in `pyproject.toml`. `wptui.__version__`
is derived from the installed package metadata (`importlib.metadata`), so it follows
`pyproject.toml` automatically — never edit a version literal in the source.

## 1. Cut the release (this repo)

```sh
# bump `version` in pyproject.toml, then:
git add pyproject.toml
git commit -m "chore(release): X.Y.Z"
git tag -a vX.Y.Z -m "vX.Y.Z"
git push origin master
git push origin vX.Y.Z
```

## 2. Build & publish to PyPI

```sh
rm -rf dist build wptui.egg-info
python -m build                 # in the dev venv: pip install -e ".[dev]"
twine check dist/*
twine upload dist/*             # uploads the exact bytes; the sha256 is now fixed
```

PyPI versions are **immutable** — you cannot re-upload the same version with different
bytes. If you publish and then find a bug, bump to the next patch version and republish;
don't try to overwrite.

### Sanity checks before uploading
- `python -c "import zipfile,glob; assert any(n.endswith('.tcss') for n in zipfile.ZipFile(glob.glob('dist/*.whl')[0]).namelist())"`
  — the wheel must contain `wptui/app.tcss` (it is `package-data`; a missing stylesheet
  crashes a fresh install at launch).
- Fresh-env smoke test: `pipx run --spec ./dist/wptui-X.Y.Z-py3-none-any.whl wptui --version`.

## 3. Update the Homebrew tap (separate repo)

The formula lives **only** in the `gboone/homebrew-tap` repo (`Formula/wptui.rb`), never
in this repo. After the PyPI upload:

```sh
# in the homebrew-tap checkout
brew bump-formula-pr wptui \
  --url="<sdist url from https://pypi.org/project/wptui/#files>"
# then regenerate the dependency resources and verify:
brew update-python-resources Formula/wptui.rb
brew install --build-from-source Formula/wptui.rb
brew test wptui
git commit -am "wptui X.Y.Z" && git push
```

`brew bump-formula-pr` fills in the new `url` + `sha256`; `update-python-resources`
regenerates the transitive dependency `resource` blocks (textual, httpx, keyring,
platformdirs and their closure). Re-run the latter on every dependency change.

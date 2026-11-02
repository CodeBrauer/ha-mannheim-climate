# Contributing

Rules for code, tests, commits, pull requests and versioning are in
[`AGENTS.md`](https://github.com/CodeBrauer/ha-mannheim-climate/blob/main/AGENTS.md). They
apply to humans and AI agents alike.

## Development environment

| Command | Purpose |
|---|---|
| `scripts/setup` | Creates `.venv` with Home Assistant (uv, Python 3.14) |
| `scripts/develop` | Starts Home Assistant on <http://localhost:8123> with `config/` and this integration |
| `scripts/lint` | `ruff format` and `ruff check` (`select = ALL`), then the documentation check |
| `scripts/test` | pytest; arguments are passed on, e.g. `scripts/test -k recommend` |
| `scripts/docs` | Serves the documentation locally; `scripts/docs de` for German, `scripts/docs build` for both |

On macOS some Home Assistant dependencies (`pymicro-vad`, `pyspeex-noise`) have no wheels
for Python 3.14 and fail to compile. Build them once with the SDK path:

```bash
SDK=$(xcrun --show-sdk-path) SDKROOT="$SDK" CXXFLAGS="-isysroot $SDK -I$SDK/usr/include/c++/v1" uv pip install --python .venv/bin/python pymicro-vad pyspeex-noise
```

!!! warning "The API is shared"
    The API limits apply per public IP, shared with your own Home Assistant. Never poll the
    live API in loops or scripts. Tests never call it; they use `tests/fixtures/sensors.json`.

## Continuous integration

| Workflow | Runs on | Checks |
|---|---|---|
| Lint | push, pull request | `ruff check`, `ruff format --check` |
| Test | push, pull request | pytest with coverage |
| Validate | push, pull request, daily | hassfest, HACS validation |
| Docs | changes to the documentation | translation check, strict build of both languages; deploys to GitHub Pages from `main` |
| Release | published release | Attaches `mannheim_climate.zip`, which HACS installs |

Releases follow the runbook in
[`.claude/skills/release/SKILL.md`](https://github.com/CodeBrauer/ha-mannheim-climate/blob/main/.claude/skills/release/SKILL.md).

## Documentation

This site is built with [Zensical](https://zensical.org) from Markdown in `docs/`:

| Path | Content |
|---|---|
| `docs/en/` | English pages, the source |
| `docs/de/` | German translation, same files and structure |
| `docs/screenshots/` | Images, shared with the READMEs (linked into both languages) |
| `mkdocs.yml`, `mkdocs.de.yml` | Site configuration; the German one inherits the English one |

Changes that alter documented behaviour update the pages in both languages in the same pull
request. `scripts/check_docs.py` makes sure nothing is forgotten: every English page needs a
German page with the same headings, code blocks, tables and images, and each German page
records the version of the English page it was translated from.

```bash
python3 scripts/check_docs.py                               # what is missing or outdated
python3 scripts/check_docs.py --stamp docs/en/user/setup.md # after updating the translation
scripts/docs build                                          # check and strict build of both languages
```

The workflow for updating a translation with as little effort as possible is in
[`.claude/skills/docs-site/SKILL.md`](https://github.com/CodeBrauer/ha-mannheim-climate/blob/main/.claude/skills/docs-site/SKILL.md).

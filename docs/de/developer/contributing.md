<!-- source: a5d370806356e0ff6cf3a6358303d68ba7846140 -->
# Mitarbeit

Die Regeln für Code, Tests, Commits, Pull Requests und Versionierung stehen in
[`AGENTS.md`](https://github.com/CodeBrauer/ha-mannheim-climate/blob/main/AGENTS.md). Sie
gelten für Menschen und KI-Agenten gleichermaßen.

## Entwicklungsumgebung

| Befehl | Zweck |
|---|---|
| `scripts/setup` | Legt `.venv` mit Home Assistant an (uv, Python 3.14) |
| `scripts/develop` | Startet Home Assistant auf <http://localhost:8123> mit `config/` und dieser Integration |
| `scripts/lint` | `ruff format` und `ruff check` (`select = ALL`), danach der Doku-Check |
| `scripts/test` | pytest; Argumente werden weitergegeben, z. B. `scripts/test -k recommend` |
| `scripts/docs` | Startet die Doku lokal; `scripts/docs de` für Deutsch, `scripts/docs build` für beide |

Unter macOS gibt es für einige Abhängigkeiten von Home Assistant (`pymicro-vad`,
`pyspeex-noise`) keine Wheels für Python 3.14, und der Build scheitert. Einmal mit SDK-Pfad
bauen:

```bash
SDK=$(xcrun --show-sdk-path) SDKROOT="$SDK" CXXFLAGS="-isysroot $SDK -I$SDK/usr/include/c++/v1" uv pip install --python .venv/bin/python pymicro-vad pyspeex-noise
```

!!! warning "Die API ist geteilt"
    Die API-Limits gelten pro öffentlicher IP, geteilt mit deinem eigenen Home Assistant.
    Frag die echte API nie in Schleifen oder Skripten ab. Tests rufen sie nie auf; sie nutzen
    `tests/fixtures/sensors.json`.

## Continuous Integration

| Workflow | Läuft bei | Prüft |
|---|---|---|
| Lint | Push, Pull Request | `ruff check`, `ruff format --check` |
| Test | Push, Pull Request | pytest mit Coverage |
| Validate | Push, Pull Request, täglich | hassfest, HACS-Validierung |
| Docs | Änderungen an der Doku | Übersetzungs-Check, strikter Build beider Sprachen; Deploy auf GitHub Pages von `main` |
| Release | veröffentlichtes Release | Hängt `mannheim_climate.zip` an, das HACS installiert |

Releases folgen dem Runbook in
[`.claude/skills/release/SKILL.md`](https://github.com/CodeBrauer/ha-mannheim-climate/blob/main/.claude/skills/release/SKILL.md).

## Dokumentation

Diese Seite wird mit [Zensical](https://zensical.org) aus Markdown in `docs/` gebaut:

| Pfad | Inhalt |
|---|---|
| `docs/en/` | Englische Seiten, die Quelle |
| `docs/de/` | Deutsche Übersetzung, gleiche Dateien und Struktur |
| `docs/screenshots/` | Bilder, gemeinsam mit den READMEs (in beide Sprachen verlinkt) |
| `mkdocs.yml`, `mkdocs.de.yml` | Konfiguration der Seite; die deutsche erbt von der englischen |

Änderungen, die dokumentiertes Verhalten ändern, passen die Seiten in beiden Sprachen im
selben Pull Request an. `scripts/check_docs.py` sorgt dafür, dass nichts vergessen wird: Jede
englische Seite braucht eine deutsche Seite mit denselben Überschriften, Code-Blöcken,
Tabellen und Bildern, und jede deutsche Seite merkt sich die Version der englischen Seite,
aus der sie übersetzt wurde.

```bash
python3 scripts/check_docs.py                               # was fehlt oder veraltet ist
python3 scripts/check_docs.py --stamp docs/en/user/setup.md # nach dem Aktualisieren der Übersetzung
scripts/docs build                                          # Check und strikter Build beider Sprachen
```

Der Ablauf, eine Übersetzung mit möglichst wenig Aufwand zu aktualisieren, steht in
[`.claude/skills/docs-site/SKILL.md`](https://github.com/CodeBrauer/ha-mannheim-climate/blob/main/.claude/skills/docs-site/SKILL.md).

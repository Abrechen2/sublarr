# Sublarr — Development Workflow

Solo-Projekt-Workflow. Pragmatisch, aber mit genug Disziplin um eine saubere
Git-History zu behalten und keine kaputten Builds auf `master` zu haben.

---

## Branching-Strategie

```
master (stable, immer deploybar)
  ├── feat/beschreibung    — neues Feature
  ├── fix/beschreibung     — Bugfix
  ├── chore/beschreibung   — Tooling, CI, Dependencies
  ├── docs/beschreibung    — nur Dokumentation
  └── refactor/beschreibung — Code-Umbau ohne neue Funktionalitaet
```

### Wann Branch + PR?

| Aenderung | Branch + PR | Direkt auf master |
|-----------|:-----------:|:-----------------:|
| Neues Feature | Ja | - |
| Bugfix (mehr als 1 Datei) | Ja | - |
| Refactoring | Ja | - |
| Security-Fix | Ja | - |
| CI/Workflow-Aenderungen | Ja | - |
| Version-Bump (`chore: bump version`) | - | Ja |
| Typo in README/Docs (1-2 Zeilen) | - | Ja |
| Hotfix (1 Datei, offensichtlich) | - | Ja, mit Begruendung |

**Faustregel:** Wenn es mehr als 5 Minuten dauert oder mehr als 1 Datei betrifft → Branch.

---

## Entwicklungs-Flow

### 1. Vorbereitung

```bash
git checkout master
git pull origin master
git checkout -b feat/kurze-beschreibung
```

### 2. Entwicklung

- Conventional Commits: `feat:`, `fix:`, `chore:`, `refactor:`, `docs:`, `test:`, `security:`
- Commit-Messages beschreiben WAS und WARUM — nicht "fix", "update", "misc"
- Mehrere kleine Commits sind besser als ein grosser

### 3. Tests lokal laufen lassen (PFLICHT vor Push)

```bash
# Backend
cd backend && python -m pytest --tb=short -q

# Frontend
cd frontend && npm run test -- --run
cd frontend && npm run lint
```

Wenn Tests fehlschlagen → fixen, nicht ignorieren. CI blockt den Merge sowieso.

### 4. Push + PR erstellen

```bash
git push -u origin feat/kurze-beschreibung
gh pr create --title "feat: kurze Beschreibung" --body "## Summary
- Was wurde geaendert
- Warum

## Test plan
- [ ] Backend-Tests gruen
- [ ] Frontend-Tests gruen
- [ ] Manuell getestet: ..."
```

### 5. Self-Review

Auch als Solo-Dev: Den PR-Diff einmal durchlesen.

Checkliste:
- [ ] Keine Credentials, API-Keys, Debug-Logs
- [ ] Keine `console.log` oder `print()` Debugging-Reste
- [ ] Commit-Messages sind verstaendlich
- [ ] Kein versehentlich committed: `.env`, `node_modules`, `__pycache__`

### 6. Merge

- **Merge-Strategie: Squash Merge** (default)
  - Haelt master-History sauber: 1 Feature = 1 Commit
  - GitHub UI: "Squash and merge"
- **Ausnahme:** Merge Commit bei grossen Features mit sinnvoller Zwischen-History

### 7. Aufraeumen

```bash
git checkout master
git pull origin master
git branch -d feat/kurze-beschreibung     # lokal loeschen
```

---

## Release-Flow

Releases sind entkoppelt von der taeglichen Arbeit. Nicht jeder Merge ist ein Release.

### Wann releasen?

- **Patch** (0.12.x): Gesammelt nach 2-5 Bugfixes, oder bei kritischen Fixes sofort
- **Minor** (0.x.0): Nach einem Feature-Milestone (z.B. alle geplanten Phases fertig)
- **Major** (x.0.0): Breaking Changes — aktuell nicht relevant (Beta-Phase)

### Release-Reihenfolge (KRITISCH — genau einhalten)

```
1. Alle Aenderungen auf master gemerged
2. backend/VERSION anpassen
3. CHANGELOG.md aktualisieren
4. Commit: "chore: bump version to x.y.z-beta"   (direkt auf master OK)
5. Tag + Push: git tag v0.12.3-beta && git push origin v0.12.3-beta
6. release.yml triggert automatisch: CI → Docker Build → GitHub Release
```

**Merksatz:** Code fertig → Version bump → Tag → Release. Nie andersrum.

---

## Claude Code Verhalten

Wenn Claude Code in diesem Projekt arbeitet, gelten diese Regeln automatisch:

### Vor dem Coden
- Aktuellen Branch pruefen (`git branch --show-current`)
- Wenn auf `master` und Aenderung ist nicht trivial → neuen Branch vorschlagen
- Bei unklarem Scope → Plan Mode nutzen

### Waehrend dem Coden
- Conventional Commits einhalten
- Tests nach Aenderungen laufen lassen (Backend und/oder Frontend, je nach Scope)
- Keine Aenderungen an CI-Workflows in Feature-PRs (eigener `chore/` Branch)

### Vor dem Commit
- `git diff` pruefen auf Credentials, Debug-Logs, ungewollte Dateien
- Nur geaenderte Dateien stagen (kein `git add .`)

### PR erstellen
- Titel: Conventional Commit Format
- Body: Summary + Test Plan
- Auf CI warten bevor Merge vorgeschlagen wird

---

## Anti-Patterns (vermeiden)

| Nicht machen | Stattdessen |
|---|---|
| `git commit -m "fix"` | `git commit -m "fix: provider timeout bei langsamen APIs"` |
| Direkt auf master fuer Features | Feature-Branch + PR |
| CI-Aenderungen in Feature-PRs | Eigener `chore/ci-*` Branch |
| Release vor Merge | Alle PRs mergen, dann releasen |
| `git add .` | Explizit Dateien stagen |
| Tests ueberspringen | Lokal testen, CI als Sicherheitsnetz |
| Version bump vergessen | Gehoert zum Release-Flow, nicht zum Feature |

# Troubleshooting Guide

## npm Vulnerabilities

### Lighthouse CI Vulnerabilities

Wenn du `npm audit` ausführst und Vulnerabilities von `@lhci/cli` siehst:

```
12 vulnerabilities (7 low, 5 high)
```

**Das ist normal und nicht kritisch**, weil:
- `@lhci/cli` ist ein **optionales Dev-Dependency** (nur für Performance-Tests)
- Die Vulnerabilities sind in transitiven Dependencies (Lighthouse/Puppeteer)
- Sie werden **nur in CI/Development** verwendet, nicht in Production
- Die Vulnerabilities betreffen hauptsächlich:
  - `cookie` (alte Version in @sentry/node)
  - `tar-fs` (alte Version in puppeteer-core)
  - `tmp` (alte Version in inquirer)
  - `ws` (alte Version in puppeteer-core)

**Lösungen:**

1. **Ignorieren (empfohlen):** Da es ein optionales Dev-Dependency ist, kannst du es ignorieren.

2. **Optional Dependency:** `@lhci/cli` ist bereits als `optionalDependencies` markiert. Wenn du es nicht brauchst, kannst du es entfernen:
   ```bash
   npm uninstall @lhci/cli
   ```

3. **Aktualisieren (kann Breaking Changes haben):**
   ```bash
   npm audit fix --force
   ```
   **Warnung:** Dies kann Breaking Changes verursachen und andere Dependencies aktualisieren.

4. **Nur für CI verwenden:** Lighthouse CI wird nur in CI-Pipeline verwendet, nicht lokal. Die Vulnerabilities sind dort isoliert.

### Andere npm Warnungen

**Deprecation-Warnungen** (z.B. `inflight`, `glob`, `rimraf`) sind normal:
- Sie kommen von transitiven Dependencies
- Sie sind Warnungen, keine Fehler
- Die Installation funktioniert trotzdem
- Sie werden automatisch aktualisiert, wenn die Haupt-Dependencies aktualisiert werden

## PowerShell Script-Fehler

### "Die Benennung 'y/N' wurde nicht als Name eines Cmdlet erkannt"

**Problem:** `Read-Host` interpretiert "(y/N)" als Teil des Prompts.

**Lösung:** Script wurde bereits korrigiert. Stelle sicher, dass du die neueste Version verwendest:
```powershell
git pull  # Falls du Git verwendest
```

Oder führe das Script direkt aus:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup-dev.ps1
```

## Pre-commit Hooks

### Hooks laufen nicht

**Problem:** Pre-commit Hooks werden nicht automatisch ausgeführt.

**Lösung:**
```bash
# Installiere pre-commit
pip install pre-commit

# Installiere die Hooks
pre-commit install
```

### Hooks sind zu langsam

**Lösung:** Du kannst bestimmte Hooks deaktivieren oder nur bei Push ausführen:
```bash
# Nur bei Push (nicht bei jedem Commit)
pre-commit install --hook-type pre-push
```

Oder editiere `.pre-commit-config.yaml` und setze `always_run: false` für langsame Hooks.

## CI-Pipeline Fehler

### Tests schlagen fehl

**Problem:** Tests schlagen in CI fehl, laufen aber lokal.

**Mögliche Ursachen:**
- Unterschiedliche Python/Node-Versionen
- Fehlende Umgebungsvariablen
- Unterschiedliche Test-Daten

**Lösung:**
- Prüfe die CI-Logs für spezifische Fehlermeldungen
- Stelle sicher, dass `.env.example` alle benötigten Variablen enthält
- Führe Tests lokal mit den gleichen Versionen aus wie in CI

### Coverage zu niedrig

**Problem:** CI schlägt fehl wegen niedriger Coverage.

**Lösung:**
- Prüfe den Coverage-Report in den CI-Artifacts
- Erhöhe die Coverage schrittweise
- Passe `--cov-fail-under` in `pytest.ini` an (aktuell 80%)

## Type-Checking Fehler

### mypy findet viele Fehler

**Problem:** mypy meldet viele Type-Errors.

**Lösung:**
- mypy läuft aktuell mit `continue-on-error: true` in CI
- Korrigiere Type-Errors schrittweise
- Erweitere `mypy.ini` mit weiteren Ignores, wenn nötig

## Dependency Pinning

### requirements.txt vs requirements.in

**Problem:** Soll ich `requirements.in` oder `requirements.txt` bearbeiten?

**Lösung:**
- **Aktuell:** Bearbeite `requirements.txt` direkt (wie bisher)
- **Mit pip-tools:** Bearbeite `requirements.in` und führe `pip-compile` aus
- **Empfehlung:** Nutze `requirements.in` für bessere Dependency-Management

**Migration zu pip-tools:**
```bash
cd backend
pip install pip-tools
pip-compile requirements.in --output-file requirements.txt --upgrade
```

## Weitere Hilfe

Bei weiteren Problemen:
1. Prüfe die CI-Logs in GitHub Actions
2. Führe Tests lokal aus: `pytest` oder `npm test`
3. Prüfe die Logs: `backend/logs/` oder Frontend-Console
4. Erstelle ein Issue auf GitHub mit:
   - Fehlermeldung
   - Schritte zur Reproduktion
   - System-Informationen (OS, Python/Node-Version)

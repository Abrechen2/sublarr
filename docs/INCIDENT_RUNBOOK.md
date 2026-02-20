# Incident Runbook — Sublarr

> **Zweck:** Schnelle Diagnose und Behebung häufiger Ausfälle im Betrieb.

## Quick Reference

| Symptom | Wahrscheinliche Ursache | Lösung |
|---------|------------------------|--------|
| API antwortet nicht | Backend crashed | Siehe "Backend nicht erreichbar" |
| Übersetzungen schlagen fehl | Ollama nicht erreichbar | Siehe "Übersetzungs-Backend-Fehler" |
| Provider-Suche schlägt fehl | API-Keys ungültig | Siehe "Provider-Fehler" |
| Dateien werden nicht gespeichert | Speicherplatz voll | Siehe "Dateisystem-Probleme" |

---

## 1. Backend nicht erreichbar

### Symptome
- HTTP 502/503/Connection Refused
- Frontend zeigt "Cannot connect to API"
- Health-Check schlägt fehl

### Diagnose

```bash
# 1. Prüfe ob Backend läuft
curl http://localhost:5765/api/v1/health

# 2. Prüfe Logs
tail -f backend/logs/sublarr.log

# 3. Prüfe Prozess
ps aux | grep python | grep app.py
```

### Häufige Ursachen

**1. Backend crashed (Python Exception)**
- **Lösung:** Logs prüfen, Fehler beheben, Backend neu starten
- **Prävention:** Error-Handling verbessern (siehe `error_handler.py`)

**2. Port bereits belegt**
- **Lösung:** Anderen Port verwenden oder Prozess beenden
```bash
lsof -i :5765
kill <PID>
```

**3. Datenbank-Lock (SQLite)**
- **Lösung:** WAL-Mode prüfen, Lock-Datei entfernen
```bash
ls -la dev.db*
rm dev.db-shm dev.db-wal  # Nur wenn sicher
```

### Lösungsschritte

1. **Backend neu starten:**
```bash
cd backend
python app.py
```

2. **Docker-Container neu starten:**
```bash
docker compose restart sublarr
```

3. **Bei persistierenden Fehlern:** Logs analysieren, Issue erstellen

---

## 2. Übersetzungs-Backend-Fehler

### Symptome
- Übersetzungen schlagen fehl mit "Cannot connect to Ollama"
- `TRANS_002` oder `TRANS_003` Error-Codes
- Health-Check zeigt Translation-Backend als "unhealthy"

### Diagnose

```bash
# 1. Prüfe Ollama-Status
curl http://localhost:11434/api/tags

# 2. Prüfe Model-Verfügbarkeit
ollama list

# 3. Prüfe Backend-Health
curl http://localhost:5765/api/v1/health/detailed | jq '.translation_backends'
```

### Häufige Ursachen

**1. Ollama nicht gestartet**
- **Lösung:** Ollama starten
```bash
ollama serve
# oder
docker run -d -p 11434:11434 ollama/ollama
```

**2. Model nicht verfügbar**
- **Lösung:** Model pullen
```bash
ollama pull <model-name>
```

**3. Falsche URL in Config**
- **Lösung:** Settings → Translation → Ollama URL prüfen

**4. Fallback-Backend nicht konfiguriert**
- **Lösung:** DeepL oder anderes Backend als Fallback konfigurieren

### Lösungsschritte

1. **Ollama neu starten:**
```bash
# Systemd
sudo systemctl restart ollama

# Docker
docker restart ollama
```

2. **Fallback-Backend aktivieren:**
- Settings → Translation → Fallback-Chain konfigurieren

3. **Model neu pullen:**
```bash
ollama pull <model-name>
```

---

## 3. Provider-Fehler

### Symptome
- Provider-Suche liefert keine Ergebnisse
- `ProviderAuthError` oder `ProviderRateLimitError` in Logs
- Provider-Status zeigt "disabled" oder "degraded"

### Diagnose

```bash
# 1. Prüfe Provider-Status
curl http://localhost:5765/api/v1/providers | jq '.[] | {name, enabled, health}'

# 2. Prüfe Provider-Health
curl http://localhost:5765/api/v1/providers/stats

# 3. Teste Provider manuell
curl -X POST http://localhost:5765/api/v1/providers/test/<provider-name>
```

### Häufige Ursachen

**1. API-Keys ungültig/abgelaufen**
- **Lösung:** Settings → Providers → API-Keys aktualisieren

**2. Rate-Limit erreicht**
- **Lösung:** Warten oder Premium-Account verwenden

**3. Provider-API down**
- **Lösung:** Warten oder anderen Provider verwenden

**4. Auto-Disable nach Fehlern**
- **Lösung:** Provider manuell re-enable in Settings

### Lösungsschritte

1. **API-Keys prüfen:**
- Settings → Providers → Test-Button klicken

2. **Provider re-enable:**
- Settings → Providers → Toggle auf "Enabled"

3. **Provider-Priorität anpassen:**
- Settings → Providers → Priority ändern

---

## 4. Dateisystem-Probleme

### Symptome
- Subtitles werden nicht gespeichert
- `OSError: [Errno 28] No space left on device`
- `RuntimeError: Insufficient disk space`

### Diagnose

```bash
# 1. Prüfe Speicherplatz
df -h /path/to/media

# 2. Prüfe Berechtigungen
ls -la /path/to/media

# 3. Prüfe Backend-Logs
grep -i "disk\|space\|permission" backend/logs/sublarr.log
```

### Häufige Ursachen

**1. Speicherplatz voll**
- **Lösung:** Platz schaffen oder größeres Volume verwenden

**2. Berechtigungen fehlen**
- **Lösung:** PUID/PGID in Docker prüfen, Berechtigungen setzen
```bash
chown -R $PUID:$PGID /path/to/media
```

**3. Path-Mapping falsch**
- **Lösung:** Settings → Sonarr/Radarr → Path-Mapping prüfen

### Lösungsschritte

1. **Speicherplatz freigeben:**
```bash
# Alte Backups löschen
find /config/backups -type f -mtime +30 -delete

# Provider-Cache leeren
curl -X POST http://localhost:5765/api/v1/providers/cache/clear
```

2. **Berechtigungen korrigieren:**
```bash
chown -R $PUID:$PGID /path/to/media
```

3. **Path-Mapping testen:**
- Settings → Sonarr/Radarr → Test-Button

---

## 5. Datenbank-Probleme

### Symptome
- `DatabaseError` oder `DatabaseIntegrityError`
- Backend startet nicht
- Daten fehlen oder sind inkonsistent

### Diagnose

```bash
# 1. Prüfe Datenbank-Integrität
sqlite3 dev.db "PRAGMA integrity_check;"

# 2. Prüfe Datenbank-Größe
ls -lh dev.db*

# 3. Prüfe WAL-Mode
sqlite3 dev.db "PRAGMA journal_mode;"
```

### Häufige Ursachen

**1. Datenbank-Lock**
- **Lösung:** WAL-Mode aktivieren, Lock-Dateien entfernen

**2. Datenbank korrupt**
- **Lösung:** Backup wiederherstellen

**3. Schema-Migration fehlgeschlagen**
- **Lösung:** Logs prüfen, manuell migrieren

### Lösungsschritte

1. **Backup wiederherstellen:**
- Settings → System → Restore Backup

2. **Datenbank reparieren:**
```bash
sqlite3 dev.db ".recover" | sqlite3 dev.db.recovered
mv dev.db.recovered dev.db
```

3. **Bei persistierenden Problemen:** Issue erstellen mit DB-Dump

---

## 6. Frontend-Build-Fehler

### Symptome
- Frontend lädt nicht
- `npm run build` schlägt fehl
- TypeScript-Errors

### Diagnose

```bash
# 1. Prüfe Node-Version
node --version  # Sollte 20 oder 21 sein

# 2. Prüfe Dependencies
cd frontend && npm ci

# 3. Prüfe TypeScript-Errors
cd frontend && npx tsc --noEmit
```

### Lösungsschritte

1. **Dependencies neu installieren:**
```bash
cd frontend
rm -rf node_modules package-lock.json
npm install
```

2. **Build manuell testen:**
```bash
cd frontend
npm run build
```

---

## 7. Webhook-Probleme

### Symptome
- Sonarr/Radarr Webhooks kommen nicht an
- Auto-Scan funktioniert nicht
- Subtitles werden nicht automatisch gesucht

### Diagnose

```bash
# 1. Prüfe Webhook-URL in Sonarr/Radarr
# Settings → Connect → Webhooks → Sublarr

# 2. Teste Webhook manuell
curl -X POST http://localhost:5765/api/v1/webhook/sonarr \
  -H "Content-Type: application/json" \
  -d '{"eventType": "Download"}'

# 3. Prüfe Backend-Logs
grep -i "webhook" backend/logs/sublarr.log
```

### Lösungsschritte

1. **Webhook-URL prüfen:**
- Sonarr/Radarr: `http://sublarr:5765/api/v1/webhook/sonarr`
- API-Key falls konfiguriert

2. **Webhook neu konfigurieren:**
- Sonarr/Radarr → Settings → Connect → Webhooks → Add

---

## Monitoring & Prävention

### Health-Checks regelmäßig prüfen

```bash
# Automatisiertes Monitoring (z.B. via cron)
curl http://localhost:5765/api/v1/health/detailed | jq '.status'
```

### Logs überwachen

```bash
# Wichtige Log-Patterns
tail -f backend/logs/sublarr.log | grep -E "ERROR|WARNING|Exception"
```

### Backup-Strategie

- **Automatische Backups:** Settings → System → Auto-Backup aktivieren
- **Manuelle Backups:** Settings → System → Backup erstellen

---

## Eskalation

Wenn keine Lösung funktioniert:

1. **Logs sammeln:**
```bash
# Backend-Logs
tail -n 1000 backend/logs/sublarr.log > incident.log

# Health-Check
curl http://localhost:5765/api/v1/health/detailed > health.json

# System-Info
df -h > disk-usage.txt
```

2. **Issue erstellen:**
- GitHub: Vollständige Fehlermeldung, Logs, System-Info
- Include: Request-ID aus Error-Response

---

**Letzte Aktualisierung:** 2026-02-XX  
**Nächste Review:** Monatlich oder nach größeren Incidents

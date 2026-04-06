# Plan: Trash Overview — Unified Trash Page with Backend Fixes

**Branch:** `feat/trash-overview`  
**Datum:** 2026-04-05  
**Ziel:** Einheitliche Trash-Übersichtsseite (`/trash`) mit korrekter Auto-Purge, verbessertem Manifest und Restore-Flow für beide Trash-Typen.

---

## Kontext & Probleme

Zwei getrennte Trash-Systeme existieren, aber kein UI dafür:

| Typ | Pfad | API | Problem |
|-----|------|-----|---------|
| Sidecar-Batches | `{media}/.sublarr_trash/{batch_id}/` | `/library/trash` | Manifest hat keinen Series-Kontext; Auto-Purge nur bei nächstem Cleanup |
| MKV-Backups | `{video_dir}/.sublarr/trash/{date}/` | `/remux/backups` | Scheduler löscht NIE (nur Scan); `video_path` nicht im API-Response |

---

## Phasen

### Phase 1 — Backend: Manifest erweitern

**Ziel:** Sidecar-Trash-Manifest enthält Series-Kontext für lesbare UI-Anzeige.

**Task 1.1** — `_write_manifest()` in `backend/routes/subtitles.py` um optionale Felder erweitern:
```python
manifest = {
    "batch_id": batch_id,
    "created_at": datetime.now(UTC).isoformat(),
    "files": files,
    "series_name": series_name or "",   # NEU — aus Dateipfad ableiten
    "language": language or "",          # NEU — aus gelöschten Dateinamen ableiten
}
```
- `series_name`: letzter nicht-Season-Ordner aus dem `original`-Pfad der ersten Datei
- `language`: Sprachcode aus Dateiname (`.de.`, `.eng.`, etc.) per Regex

**Task 1.2** — Alle Aufrufer von `_write_manifest()` anpassen (beide Delete-Endpunkte in `subtitles.py`), `series_name` + `language` ableiten und mitgeben.

**Task 1.3** — `list_trash()` gibt die neuen Felder mit zurück:
```json
{
  "batches": [{
    "batch_id": "...",
    "created_at": "...",
    "file_count": 3,
    "size_bytes": 654,
    "series_name": "Extraktion Test",
    "language": "eng",
    "expires_at": "..."   // NEU: created_at + retention_days
  }]
}
```
- `expires_at` aus `created_at + subtitle_trash_retention_days` berechnen

---

### Phase 2 — Backend: MKV-Backup-API verbessern

**Ziel:** `list_backups` gibt `video_path` mit zurück damit Frontend Restore aufrufen kann.

**Task 2.1** — `list_backups()` in `backend/remux/backup_cleanup.py` erweitern:
```python
def _derive_video_path(bak_path: str) -> str:
    """
    Beispiel: /media/.../.sublarr/trash/2026-04-05/Episode.mkv.1775388610.bak
    → /media/.../Episode.mkv
    """
    filename = os.path.basename(bak_path)
    # Entferne .{timestamp}.bak Suffix
    stem = re.sub(r'\.\d+\.bak$', '', filename)
    # Rekonstruiere original dir: bak_path/../../../ (raus aus .sublarr/trash/date/)
    original_dir = os.path.normpath(os.path.join(os.path.dirname(bak_path), '../../..'))
    return os.path.join(original_dir, stem)

result.append({
    "path": bak_path,
    "video_path": _derive_video_path(bak_path),   # NEU
    "size_bytes": stat.st_size,
    "mtime": stat.st_mtime,
    "expires_at": ...,  # NEU: mtime + remux_backup_retention_days
})
```

**Task 2.2** — `GET /api/v1/remux/backups` gibt `expires_at` mit zurück (im Route-Handler berechnen, da dort `remux_backup_retention_days` verfügbar).

---

### Phase 3 — Backend: Auto-Purge reparieren

**Ziel:** Beide Trash-Typen werden automatisch und zuverlässig nach Ablauf gelöscht.

**Task 3.1** — `cleanup_scheduler.py` `old_backups`-Rule: von Scan-only auf echtes Löschen umstellen:
```python
elif rule_type == "old_backups":
    from remux.backup_cleanup import cleanup_old_backups
    retention_days = getattr(settings, "remux_backup_retention_days", 7)
    result = cleanup_old_backups(_trash_paths_from_settings(settings), retention_days)
    # Log + update rule + log_cleanup
```
Hierfür `_trash_paths()` aus `routes/remux.py` in eine shared Funktion extrahieren oder Logik duplizieren (einfacher, da kein Request-Context im Scheduler).

**Task 3.2** — Sidecar-Trash-Purge ebenfalls im Scheduler hinzufügen (neuer Block nach `old_backups`):
```python
elif rule_type == "old_sidecar_trash":
    from routes.subtitles import _auto_purge_old_trash
    retention = getattr(settings, "subtitle_trash_retention_days", 30)
    purged = _auto_purge_old_trash(settings.media_path, retention)
    # Log + update rule
```

**Task 3.3** — Config-Defaults anpassen in `backend/config.py`:
```python
subtitle_trash_retention_days: int = 30   # war 7
remux_backup_retention_days: int = 7      # bleibt 7 (MKVs = groß)
```

**Task 3.4** — Alembic-Migration NICHT nötig (reine Config-Änderung). Aber prüfen ob Default-Werte über `config_entries` in der DB überschrieben werden — wenn ja, Migration für Default-Update (oder nur Docs).

---

### Phase 4 — Backend: Unified Trash Endpoint

**Ziel:** Ein einziger Endpunkt für die UI, der beide Trash-Typen kombiniert.

**Task 4.1** — Neuer Endpoint `GET /api/v1/trash` in einer neuen Route-Datei `backend/routes/trash.py`:
```python
@bp.route("/trash", methods=["GET"])
def get_unified_trash():
    """Returns both sidecar batches and MKV backups in one response."""
    # Sidecar-Batches aus /library/trash-Logik
    # MKV-Backups aus list_backups()
    return jsonify({
        "sidecar_batches": [...],   # Wie bisher + series_name + language + expires_at
        "mkv_backups": [...],       # path + video_path + size_bytes + mtime + expires_at
        "total_size_bytes": ...,
        "retention": {
            "sidecar_days": subtitle_trash_retention_days,
            "mkv_days": remux_backup_retention_days,
        }
    })
```

**Task 4.2** — Blueprint in `app.py` registrieren.

---

### Phase 5 — Backend: MKV-Restore mit Sidecar-Löschung

**Ziel:** Optionale Sidecar-Löschung beim MKV-Restore.

**Task 5.1** — `POST /api/v1/remux/backups/restore` um optionalen Parameter erweitern:
```json
{
  "backup_path": "...",
  "video_path": "...",
  "delete_sidecars": true   // NEU, default false
}
```

**Task 5.2** — Wenn `delete_sidecars=true`: nach dem Atomic Swap alle Dateien im selben Verzeichnis mit gleichem Stammnamen aber Subtitle-Extension (`.srt`, `.ass`, `.vtt`) in den Sidecar-Trash verschieben (via `_move_to_trash()`-Logik, Batch-Manifest schreiben).

Sidecar-Matching per Filename-Stem (ohne `.bak` Suffix):
```
Episode 1.mkv.1775388610.bak → Stem = "Episode 1"
→ Suche: Episode 1.*.srt, Episode 1.*.ass, etc.
```

---

### Phase 6 — Frontend: API-Client + Hooks

**Ziel:** Typisierte API-Funktionen und React-Query-Hooks.

**Task 6.1** — Neue Datei `frontend/src/api/trash.ts`:
```typescript
export interface SidecarBatch {
  batch_id: string
  created_at: string
  file_count: number
  size_bytes: number
  series_name: string
  language: string
  expires_at: string
}

export interface MkvBackup {
  path: string
  video_path: string
  size_bytes: number
  mtime: number
  expires_at: string
}

export interface TrashOverview {
  sidecar_batches: SidecarBatch[]
  mkv_backups: MkvBackup[]
  total_size_bytes: number
  retention: { sidecar_days: number; mkv_days: number }
}

export async function getTrashOverview(): Promise<TrashOverview> { ... }
export async function restoreSidecarBatch(batchId: string): Promise<{ restored: number; failed: number }> { ... }
export async function deleteSidecarBatch(batchId: string): Promise<void> { ... }
export async function restoreMkvBackup(backupPath: string, videoPath: string, deleteSidecars: boolean): Promise<{ restored: string }> { ... }
export async function deleteMkvBackup(backupPath: string): Promise<void> { ... }
```

**Task 6.2** — Neue Datei `frontend/src/hooks/useTrashApi.ts`:
```typescript
export function useTrashOverview() {
  return useQuery({
    queryKey: ['trash-overview'],
    queryFn: getTrashOverview,
    staleTime: 30_000,
  })
}
export function useRestoreSidecarBatch() { ... }   // useMutation + invalidate
export function useDeleteSidecarBatch() { ... }
export function useRestoreMkvBackup() { ... }
export function useDeleteMkvBackup() { ... }
```

**Task 6.3** — `frontend/src/api/client.ts` re-exportiert aus `trash.ts`.

---

### Phase 7 — Frontend: Trash-Seite

**Ziel:** `/trash` als vollwertige Seite mit beiden Sektionen.

**Task 7.1** — Neue Datei `frontend/src/pages/Trash.tsx`:

Layout-Struktur:
```
Trash
├── Header: "Papierkorb" + Gesamtgröße + "Alles leeren"-Button
├── Info-Banner: "Sidecar: 30 Tage · MKV-Backups: 7 Tage · [→ Einstellungen]"
├── Sektion "Sidecar-Untertitel" (badge: Anzahl)
│   └── SidecarBatchCard × n
│       ├── Icon 🗑 + Serienname + Sprache-Badge
│       ├── "3 Dateien · 654 B · läuft ab am 05.05.2026"
│       ├── Dateiliste (collapsed, expand on click)
│       └── [Endgültig löschen] [Wiederherstellen]
└── Sektion "MKV-Backups" (badge: Anzahl + Gesamtgröße)
    └── MkvBackupCard × n
        ├── Icon 📼 + Dateiname + Größe
        ├── "Erstellt am 05.04.2026 · läuft ab am 12.04.2026"
        └── [Endgültig löschen] [Wiederherstellen →]
```

**Task 7.2** — `MkvRestoreModal.tsx` (Confirm-Dialog):
```
⚠ MKV-Backup wiederherstellen

Das Original-MKV (mit eingebetteten Streams) wird zurückgeschrieben.
Die aktuelle Version (ohne Streams) wird ersetzt.

☑ Extrahierte Sidecar-Untertitel ebenfalls löschen
  (empfohlen — sonst sind Streams und Sidecars doppelt vorhanden)

                    [Abbrechen]  [Wiederherstellen]
```
- Checkbox default: `true`
- `autoFocus` auf Wiederherstellen-Button

**Task 7.3** — Leerer Zustand (kein Trash):
```
🗑
Papierkorb ist leer
Gelöschte Untertitel und MKV-Backups erscheinen hier.
```

---

### Phase 8 — Frontend: Navigation & Routing

**Ziel:** `/trash` erreichbar, Sidebar-Icon sichtbar wenn Trash nicht leer.

**Task 8.1** — `App.tsx`: neue Route hinzufügen:
```tsx
<Route path="/trash" element={<TrashPage />} />
```
(lazy-loaded wie alle anderen Pages)

**Task 8.2** — `IconSidebar.tsx`: Trash-Nav-Item mit bedingtem Badge:

```tsx
// Abfrage: useTrashOverview() — aber nur Badge-Count, kein Full-Fetch
// Besser: separater leichtgewichtiger Endpoint oder trashCount aus Overview
{trashCount > 0 && (
  <NavItem
    to="/trash"
    icon={Trash2}
    labelKey="nav.trash"
    badge={trashCount}
    testId="nav-link-trash"
  />
)}
```

**Achtung:** `useTrashOverview()` im Sidebar würde bei jeder Seite einen API-Call auslösen. Lösung: Badge-Count im globalen State cachen (z.B. in einem kleinen Zustand-Store oder `useQuery` mit langem `staleTime: 300_000`).

**Task 8.3** — i18n-Key hinzufügen: `"nav.trash": "Papierkorb"` (falls i18n-System genutzt wird).

---

### Phase 9 — Settings: Retention-Einstellungen

**Ziel:** Beide Retention-Werte sichtbar und konfigurierbar.

**Task 9.1** — In `AutomationSettings.tsx` (oder passendem Settings-Tab): bestehende `subtitle_trash_retention_days` Einstellung prüfen und `remux_backup_retention_days` daneben platzieren:

```
Papierkorb-Aufbewahrung
├── Sidecar-Untertitel: [30] Tage   (0 = unbegrenzt)
└── MKV-Backups:         [ 7] Tage  (0 = unbegrenzt)
    ⚠ MKV-Backups können mehrere GB groß sein.
```

**Task 9.2** — Prüfen ob `remux_backup_retention_days` bereits in der Settings-UI vorhanden ist (in `RemuxTab.tsx`) — wenn ja, dort belassen und von Trash-Settings verlinken.

---

## Reihenfolge der Implementierung

```
Phase 1 (Manifest)
    ↓
Phase 2 (MKV API)
    ↓
Phase 3 (Auto-Purge)
    ↓
Phase 4 (Unified Endpoint)
    ↓
Phase 5 (MKV Restore + Sidecars)
    ↓
Phase 6 (Frontend API + Hooks)
    ↓
Phase 7 (Trash-Seite)
    ↓
Phase 8 (Nav + Routing)
    ↓
Phase 9 (Settings)
```

Backend-Phasen (1-5) zuerst, da Frontend davon abhängt.

---

## Offene Risiken & Entscheidungen

| Risiko | Entscheidung |
|--------|-------------|
| Sidebar lädt Trash-Count bei jeder Seite | `staleTime: 300_000` (5 min) — akzeptabel für internes Tool |
| `_derive_video_path()` fragil bei Sonderzeichen | Validierung: prüfen ob abgeleiteter Pfad existiert; wenn nicht → `video_path: null` + Restore-Button disabled |
| Sidecar-Matching beim MKV-Restore falsch | Nur exakter Stem-Match; User sieht welche Sidecars gelöscht werden (Preview in Modal) |
| `remux_backup_retention_days` schon in RemuxTab | Prüfen in Phase 9 — ggf. nur Link statt Duplikat |
| Scheduler-Cleanup läuft wöchentlich | Akzeptabel — Trash-Seite zeigt genaues Ablaufdatum; User kann auch manuell leeren |

---

## Tests

- **Backend (pytest):** `tests/test_trash_routes.py` — listet, restores, delete für beide Typen; `test_manifest_series_context.py` — neues Manifest-Format
- **Frontend (Vitest):** `Trash.test.tsx` — Render, leerer Zustand, Restore-Flow
- **Kein E2E erforderlich** — Unit + Integration reichen für diese Dateioperations-Logik

---

## Commit-Strategie

```
feat: extend sidecar trash manifest with series_name and language         (Phase 1)
feat: add video_path and expires_at to remux backup listing              (Phase 2)
fix: cleanup scheduler now deletes old MKV backups and sidecar trash     (Phase 3)
feat: unified GET /api/v1/trash endpoint combining both trash types      (Phase 4)
feat: MKV restore supports optional sidecar deletion                     (Phase 5)
feat: trash API client and React Query hooks                             (Phase 6)
feat: /trash overview page with sidecar and MKV backup sections         (Phase 7)
feat: sidebar trash icon with badge and /trash route                    (Phase 8)
chore: add retention settings for both trash types in settings UI        (Phase 9)
```

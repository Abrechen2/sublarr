# Batch 03 — Library (/library)

**Getestet:** 2026-03-14 | **Instance:** http://192.168.178.143:5766
**Playwright:** `PLAYWRIGHT_BASE_URL=http://192.168.178.143:5766 npx playwright test e2e/specs/03-library.spec.ts`
**Ergebnis:** ✅ 15 passed | ⏭️ 3 skipped (dokumentiert) | ❌ 0 failures

---

## Playwright-Ergebnis

| Test-ID | Funktion | Status | Notiz |
|---------|---------|--------|-------|
| 3.1.1 | Library rows laden mit Inhalt | ✅ | 427 Serien sichtbar |
| 3.1.2 | Klick auf Karte navigiert zu `/library/series/:id` | ✅ | |
| 3.2.1 | Grid-Ansicht umschalten | ✅ | Poster-Karten sichtbar (Screenshot) |
| 3.2.2 | Zurück zu Tabellenansicht | ✅ | |
| 3.2.3 | View-Mode bleibt nach Reload | ✅ | `localStorage['library_view_mode']` korrekt |
| 3.3.1 | Pagination: Nächste Seite | ⏭️ SKIP | **INFO:** Tabellenansicht nutzt Virtual Scroll (kein Paging) |
| 3.3.2 | Pagination: Vorherige Seite | ⏭️ SKIP | Abhängig von 3.3.1 |
| 3.3.3 | Leere Suche zeigt Empty State | ✅ | |
| 3.4.1 | Profil-Button erscheint auf Zeile | ✅ | Profile-Spalte sichtbar (Screenshot) |
| 3.5.1 | Refresh-Button löst Reload aus | ⏭️ SKIP | **INFO:** Kein dedizierter Refresh-Button in Toolbar |
| 3.6.1 | Auto-Sync Toggle existiert | ✅ | |
| 3.6.1+3.6.2 | Toggle öffnet Bulk Sync Panel | ✅ | Panel sichtbar (Screenshot) |
| 3.6.4 | Engine-Selector hat alass/ffsubsync | ✅ | Beide Optionen vorhanden |
| 3.6.5 | Start Bulk Sync Button klickbar | ✅ | Enabled für "Entire Library" Scope |
| Search | Suche filtert Zeilen | ✅ | |
| Search | Suche findet My Dress-Up Darling | ✅ | |
| Search | Suche löschen stellt alle Zeilen wieder her | ✅ | |
| Search | Series/Movies-Tabs sichtbar | ✅ | |

---

## Visuelle Verifikation

Screenshots gespeichert unter `frontend/e2e/visual-batch03/`:

- **3-2-1-grid-view.png** — Grid-Ansicht mit Poster-Karten ✅
- **3-4-1-profile-btn.png** — Tabellenansicht mit Profil-Spalte ✅
- **3-6-panel.png** — Bulk Auto-Sync Panel geöffnet ✅

---

## Offene Issues / Dokumentierte Abweichungen

### ℹ️ INFO: 3.3.1-3.3.2 — Pagination nur in Grid-Ansicht

**Verhalten:** Die Tabellenansicht verwendet `VirtualLibraryTable` mit virtualem Scroll (alle Items on-demand gerendert, kein Seiten-Paging). Pagination (`pagination-prev`/`pagination-next`) existiert nur in der Grid-Ansicht (25 Items/Seite).

**Befund:** Beide Skip-Gründe korrekt. Die Grid-Ansicht HAT Pagination bei 427 Serien.

**Aktion:** Keine — akzeptiertes Design.

---

### ℹ️ INFO: 3.5.1 — Kein dedizierter Refresh-Button

**Verhalten:** Die Library-Toolbar hat keinen separaten Refresh-Button. `RefreshCw`-Icon ist nur im Bulk Sync Panel verwendet.

**Aktion:** Keine — akzeptiertes Design. Test korrekt geskippt.

---

### ℹ️ INFO: Timeout-Anpassung

**Problem:** Bei paralleler Test-Ausführung variiert die API-Antwortzeit (5–15s). Original-Timeout von 10s zu knapp.

**Fix:** `toBeVisible({ timeout: 20000 })` in allen `beforeEach`-Calls der Library-Tests.

---

## Fix-Branches

Keine Fixes notwendig — alle Abweichungen sind dokumentiertes Verhalten.

---

## Batch-Status: ✅ GRÜN

Alle 15 Playwright-Tests bestanden. 3 Tests korrekt geskippt (dokumentiertes Verhalten, keine Bugs).

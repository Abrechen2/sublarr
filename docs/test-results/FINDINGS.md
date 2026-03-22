# Sublarr UI Test Findings — v0.33.0-beta

> **Instanz:** http://192.168.178.194:5765
> **Datum:** 2026-03-22
> **Testplan:** [UI_TEST_PLAN_v0.33.0.md](UI_TEST_PLAN_v0.33.0.md)
> **Tester:** Claude (Playwright-Browser, manuell)

---

## Zusammenfassung

| Schwere | Anzahl |
|---------|--------|
| 🔴 Kritisch | 2 |
| 🟠 Hoch | 2 |
| 🟡 Mittel | 4 |
| 🔵 Niedrig | 3 |
| 💅 UX | 2 |
| ✅ Positiv (Lücken geschlossen) | 4 |
| **Gesamt** | **17** |

---

## Findings

---

### FINDING-001 — 🔴 Kritisch: Settings/System und Settings/Translation crashen

**Testfall:** TC-10.8 (SystemSettings), TC-10.6 (TranslationSettings)
**Typ:** Runtime-Fehler / React-Context
**Schwere:** Kritisch — Seite rendert nicht, ErrorBoundary zeigt "Something went wrong"

**Beschreibung:**
`/settings/system` und `/settings/translation` crashen mit:
```
useAdvancedSettings must be used within AdvancedSettingsProvider
```
Betroffen sind alle Settings-Seiten, die `SettingRow`-Komponenten verwenden (`SecurityTab`, `AdvancedTab`, `TranslationTab`, etc.). Der `AdvancedSettingsProvider` fehlt im `SettingsPage`-Wrapper.

**Ursache:** `SettingRow` in `components/shared/SettingRow.tsx` ruft `useAdvancedSettings()` auf. Der Context-Provider war nur in `LegacySettings.tsx` und `WebhooksPage.tsx` lokal vorhanden, aber nie global in `Settings/index.tsx`.

**Erwartetes Verhalten:** Alle Settings-Unterseiten laden ohne Fehler.

**Reproduktion:**
1. Einloggen
2. Navigiere zu `/settings/system` oder `/settings/translation`
3. Seite zeigt "Something went wrong"

**Betroffene Routen:**
- `/settings/system` (→ SecurityTab, AdvancedTab)
- `/settings/translation` (→ TranslationTab, WhisperTab)
- Potenziell: alle Settings-Seiten die SettingRow verwenden

**Fix:** `AdvancedSettingsProvider` um `<Routes>` in `Settings/index.tsx` wrappen — **bereits behoben**.

**Screenshot:** 09-automation-settings.png (Vergleich: funktionierendes Automation)

---

### FINDING-002 — 🔴 Kritisch: Login-Button bleibt deaktiviert (React-Controlled-Input-Problem)

**Testfall:** TC-16.1
**Typ:** Funktionsfehler — Auth-Formular
**Schwere:** Kritisch — Benutzer kann sich nicht über das UI einloggen

**Beschreibung:**
Das Login-Formular zeigt ein Passwort-Eingabefeld. Wenn Benutzer Zeichen eingeben (auch per Browser-Autofill oder programmatisch), bleibt der "Log In"-Button weiterhin `disabled`. Der Button wird erst aktiv wenn React-State korrekt aktualisiert wird — was bei Playwright's `fill()` und bei direkt gesetztem `input.value` per JS nicht funktioniert.

**Ursache:** React kontrolliertes Input — der State wird über `onChange` gesetzt. Playwright's native `fill()` triggert zwar `input`-Events, aber React's synthetisches Event-System reagiert unter bestimmten Bedingungen (React 19, TypeScript strict) nicht darauf. Direktes Setzen von `input.value` ohne Dispatch des richtigen synthetischen Events schlägt ebenfalls fehl.

**Erwartetes Verhalten:** Text in Passwortfeld eingeben → Button wird aktiv → Login funktioniert.

**Reproduktion:**
1. Öffne http://192.168.178.194:5765/login
2. Klicke auf das Passwortfeld
3. Tippe beliebigen Text
4. Log In Button bleibt grayed out / disabled

**Evidence:** Screenshot 02-login-blank.png, 03-after-login.png

**Hinweis:** Wenn Auth deaktiviert ist (kein Passwort konfiguriert), kann ein leerer POST an `/api/v1/auth/login` den Login umgehen. Das eigentliche UI-Problem bleibt aber bestehen wenn Auth aktiv ist.

---

### FINDING-003 — 🟠 Hoch: Sidebar zeigt nur 4 statt 5+ Navigationslinks

**Testfall:** TC-1.1
**Typ:** Navigation / UI-Vollständigkeit
**Schwere:** Hoch — Mehrere wichtige Bereiche sind nicht direkt erreichbar

**Beschreibung:**
Die Icon-Sidebar zeigt nur:
- Dashboard
- Bibliothek
- Aktivität
- Einstellungen (Bottom-Bereich)

Die App enthält aber auch `/activity?tab=wanted`, `/activity?tab=blacklist`, Sprachprofile (`/settings/language-profiles`), Movie Detail Pages und weitere. Alle Activity-Unterbereiche (Wanted, Queue, History, Blacklist) sind nur über Tabs innerhalb der Activity-Seite erreichbar — kein direkter Seitenlink.

**Erwartetes Verhalten:** Wichtige Bereiche (zumindest Wanted / Gesucht mit Badge-Count) sollten direkt in der Sidebar erreichbar sein.

**Workaround:** Navigiere zu `/activity` und wähle den gewünschten Tab.

**Screenshot:** 10-wanted.png (zeigt Activity-Seite mit Tab-Navigation)

---

### FINDING-004 — 🟠 Hoch: Dashboard — "Needs Attention"-Widget Widerspruch

**Testfall:** TC-2.3
**Typ:** Datenwiderspruch / UI-Logik
**Schwere:** Hoch — Verwirrende Darstellung, falsche Information

**Beschreibung:**
Das "Needs Attention"-Badge in der Sidebar zeigt **6091** Einträge.
Das Dashboard-Widget "Needs Attention" zeigt aber im Card-Body: **"No items need attention"**.

Diese direkte Widerspruch lässt den Benutzer im Unklaren ob wirklich Einträge vorhanden sind oder nicht. Vermutlich werden Wanted-Items (6091) als "Attention"-Trigger gezählt, aber die Karte filtert diese anders.

**Erwartetes Verhalten:** Badge-Count und Widget-Inhalt müssen konsistent sein. Entweder zeigt das Widget die 6091 Einträge, oder der Badge zeigt 0.

**Reproduktion:**
1. Öffne Dashboard
2. Sidebar-Badge: "99+" (kapped) oder tatsächlich 6091
3. Klicke "Needs Attention" im Dashboard → "No items need attention"

**Screenshot:** 04-dashboard-authenticated.png

---

### FINDING-005 — 🟡 Mittel: Dashboard — Automation-Status Widerspruch

**Testfall:** TC-2.2
**Typ:** Datenwiderspruch
**Schwere:** Mittel — Verwirrend aber nicht funktionsbrechend

**Beschreibung:**
Der Automation-Banner im Dashboard sagt "Automatisierung läuft" (grünes Icon).
Das Automation-Widget zeigt jedoch "Disabled".

Der StatusBar unten zeigt: "Automation: paused".

Drei verschiedene Automation-Statusindikatoren, drei verschiedene Aussagen.

**Erwartetes Verhalten:** Alle Automation-Statusindikatoren müssen denselben Zustand zeigen.

---

### FINDING-006 — 🟡 Mittel: Providers-Seite — `/api/v1/marketplace/plugins` gibt 500 zurück

**Testfall:** TC-10.4
**Typ:** Backend-Fehler
**Schwere:** Mittel — Seite lädt, aber Marketplace-Feature ist kaputt

**Beschreibung:**
Bei Navigation zu `/settings/providers` wird `GET /api/v1/marketplace/plugins` aufgerufen und gibt HTTP 500 zurück. Die Seite selbst lädt noch (kein Crash), aber der Plugin-Marketplace-Bereich zeigt keine Daten.

**Erwartetes Verhalten:** Entweder liefert der Endpoint eine leere Liste zurück, oder der Endpoint ist noch nicht implementiert und die UI sollte das graceful behandeln (kein fetch, oder 404 statt 500).

**Reproduktion:**
1. Navigiere zu `/settings/providers`
2. Browser Console: `Failed to load resource: 500 /api/v1/marketplace/plugins`

---

### FINDING-007 — 🟡 Mittel: Connections-Seite — Passwortfeld-Warnung im Browser

**Testfall:** TC-10.2
**Typ:** Accessibility / HTML-Struktur
**Schwere:** Mittel — Keine Nutzerauswirkung, aber Browser-Warning

**Beschreibung:**
Bei Navigation zu `/settings/connections` gibt Chromium mehrfach aus:
```
[DOM] Password field is not contained in a form
```
Passwortfelder (z.B. für API-Keys) sind nicht in `<form>`-Elementen eingebettet. Das verhindert Browser-Autofill, Passwort-Manager-Integration und ist eine Accessibility-Lücke.

**Erwartetes Verhalten:** Passwort-Inputs in `<form>` mit `autocomplete`-Attributen einbetten, oder explizit `autocomplete="off"` setzen wenn kein Autofill gewünscht.

---

### FINDING-008 — 🟡 Mittel: Episode-Score zeigt "—" für alle Episoden

**Testfall:** TC-4.3
**Typ:** Datendarstellung
**Schwere:** Mittel — Score-Information fehlt

**Beschreibung:**
In der Series-Detail-Seite zeigt die Spalte "Score" für alle Episoden "—" (Strich), obwohl Untertitel (.srt-Dateien) vorhanden sind.

**Mögliche Ursachen:**
- Score wird erst nach Download berechnet und nicht rückwirkend für vorhandene Dateien
- Score-Wert ist `null` in der DB für Dateien die vor dem Score-System existierten
- UI-Mapping fehlt (falscher Feldname)

**Erwartetes Verhalten:** Für Episoden mit existierenden Untertiteln sollte entweder ein Score angezeigt werden, oder ein hinweisender Tooltip ("Score wird bei nächstem Search berechnet").

**Screenshot:** 06-series-detail.png

---

### FINDING-009 — 🔵 Niedrig: "More Actions"-Button öffnet direkt Interactive Search

**Testfall:** TC-4.5
**Typ:** UX / Navigation
**Schwere:** Niedrig — Unerwartetes Verhalten, kein Datenverlust

**Beschreibung:**
Der "More Actions"-Button auf Episode-Zeilen (Symbol: drei Punkte oder ähnliches) öffnet direkt die Interactive Search statt eines Dropdown-Menüs mit mehreren Aktionen. Laut Test-Plan sollte dieser Button Aktionen wie "Translate", "Extract Embedded", "Blacklist" etc. anbieten.

**Erwartetes Verhalten:** Dropdown-Menü mit allen verfügbaren Aktionen für die Episode.

---

### FINDING-010 — 🔵 Niedrig: WebSocket-Verbindung fällt auf Polling zurück (DEV-Mode Fix)

**Testfall:** TC-17.1
**Typ:** Hinweis / bereits gefixt
**Schwere:** Niedrig — behoben vor diesem Deploy

**Beschreibung:**
In der Entwicklungsumgebung versuchte Socket.IO zunächst eine WebSocket-Verbindung zu Werkzeug aufzubauen, was fehlschlug. Fix: `WebSocketContext.tsx` erzwingt im DEV-Mode polling-only.

**Status:** ✅ Bereits behoben in Commit `cef346b` (aktuelle Version).

---

### FINDING-011 — 🔵 Niedrig: Auth-Onboarding — Bootstrap-Endpoint gibt 403 von Remote

**Testfall:** TC-16.2
**Typ:** By Design / Dokumentation
**Schwere:** Niedrig — sicherheitsrelevantes Design, kein Bug

**Beschreibung:**
`POST /api/v1/auth/bootstrap` gibt bei Remote-Zugriff HTTP 403 zurück. Das ist absichtlich — der Endpoint ist localhost-only für den ersten Setup.

**Problem:** Wenn die React-App auf einem Remote-Server läuft und der Browser versucht Bootstrap aufzurufen, schlägt dies fehl und die App rendert leer wenn noch kein User angelegt ist.

**Empfehlung:** Die App sollte bei 403 auf Bootstrap graceful auf `/setup` oder `/login` weiterleiten statt eine leere Seite zu zeigen.

---

### FINDING-012 — 💅 UX: Login-Seite — Formular hat kein visuelles Gewicht

**Testfall:** TC-16.1
**Typ:** UX / Design
**Schwere:** UX

**Beschreibung:**
Die Login-Seite zeigt ein sehr kleines, mittig ausgerichtetes Formular ohne visuelle Hierarchie, Brand-Elemente oder Kontext. Kein Logo, kein App-Name, keine Beschreibung.

**Empfehlung:** Login-Formular mit Logo, App-Name und ggf. kurzer Tagline aufwerten. Formular-Card mit mehr Padding und Shadow versehen.

**Screenshot:** 02-login-blank.png

---

### FINDING-013 — 💅 UX: Statusbar zeigt "Automation: paused" ohne Erklärung

**Testfall:** TC-17.3
**Typ:** UX / Feedback
**Schwere:** UX

**Beschreibung:**
Die untere Statusbar zeigt permanent "Automation: paused" aber es gibt keine UI-Möglichkeit direkt aus der Statusbar heraus den Status zu verstehen oder zu ändern. Der Benutzer weiß nicht warum Automation pausiert ist oder wie er sie startet.

**Empfehlung:** Tooltip oder Klick auf "Automation: paused" → öffnet Automation-Einstellungen oder zeigt Pause-Grund (z.B. "Kein Provider konfiguriert").

---

## Positive Findings (Lücken aus Gap-Analyse geschlossen)

### ✅ POS-001: AutomationSettings — alle Config-Keys korrekt

Laut SETTINGS_GAP_ANALYSIS.md waren alle 8 AutomationSettings-Keys falsch. **Alle sind jetzt korrekt** (z.B. `wanted_search_interval_hours`, `upgrade_enabled`, `upgrade_min_score_delta`). Die Gap-Analyse ist hier überholt.

### ✅ POS-002: Whisper-Transkription und OP/ED-Erkennung vorhanden

Laut UI_GAP_ANALYSIS.md A7 fehlten diese Features. In der getesteten Version **sind beide Buttons vorhanden** in der Series-Detail-Seite.

### ✅ POS-003: NFO-Export vorhanden

Laut UI_GAP_ANALYSIS.md A1 fehlte der NFO-Export-Button. In der getesteten Version **ist der Button vorhanden**.

### ✅ POS-004: Wanted/Queue/History/Blacklist als Activity-Tabs

Laut früherer Analyse fehlten diese Seiten. Sie sind als **Tabs in der Activity-Seite** vollständig implementiert (TC-5, TC-6, TC-7, TC-8 entsprechend bestätigt).

---

*Stand: 2026-03-22 — Tests gegen http://192.168.178.194:5765 (v0.33.0-beta)*

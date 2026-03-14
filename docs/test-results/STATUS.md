```
# UI Test — Status Übersicht

> Instance: `http://192.168.178.143:5766`
> Playwright-Command: `PLAYWRIGHT_BASE_URL=http://192.168.178.143:5766 npx playwright test`

## Batches

| Batch | Sections | Inhalt | Playwright | Manuell | Status |
|-------|----------|--------|:----------:|:-------:|--------|
| [B01](batch-01-navigation.md) | 1 | Navigation, Routing, Theme, Shortcuts, 404 | ✅ 22/22 | ✅ | ✅ GRÜN |
| [B02](batch-02-dashboard.md) | 2, 24 | Dashboard + Widgets | ✅ 5/5 | ✅ | ✅ GRÜN |
| [B03](batch-03-library.md) | 3 | Library Grid, Pagination, Profile, Bulk Sync | ✅ 15/15 | ✅ | ✅ GRÜN |
| [B04](batch-04-series-detail.md) | 4.1–4.3 | Series Detail: Header, Episodenliste, Actions | ⏳ | ⏳ | 🔲 Ausstehend |
| [B05](batch-05-subtitle-editor.md) | 4.4–4.7 | Subtitle Editor, Player Modal, Glossar | ➖ | ⏳ | 🔲 Ausstehend |
| [B06](batch-06-wanted.md) | 5, 23 | Wanted + Ergänzungen | ⏳ | ⏳ | 🔲 Ausstehend |
| [B07](batch-07-secondary-views.md) | 6, 7, 8 | Activity, History, Blacklist | ⏳ | ⏳ | 🔲 Ausstehend |
| [B08](batch-08-settings.md) | 9, 25, 32 | Settings (Basis + Erweitert + Field-Level) | ⏳ | ⏳ | 🔲 Ausstehend |
| [B09](batch-09-auth.md) | 14 | Auth: Login, Setup, Onboarding | ⏳ | ⏳ | 🔲 Ausstehend |
| [B10](batch-10-system-views.md) | 10–13 | Statistics, Tasks, Logs, Plugins | ⏳ | ⏳ | 🔲 Ausstehend |
| [B11](batch-11-global-quality.md) | 15–18 | Global Components, A11y, Responsive, Performance | ⏳ | ⏳ | 🔲 Ausstehend |
| [B12](batch-12-websocket.md) | 19, 20, 29 | WebSocket, Keyboard Shortcuts Erweitert | ⏳ | ⏳ | 🔲 Ausstehend |
| [B13](batch-13-edge-cases.md) | 21–28, 31, 33 | Edge Cases, Subtitle Editor Extended, Cleanup | ➖ | ⏳ | 🔲 Ausstehend |

**Legende:** ✅ Grün | ❌ Fehler | ⏳ Ausstehend | ➖ Kein Playwright (nur manuell)

---

## Regeln

1. **Batch nur abschließen wenn 100% grün** (Playwright + manuelle Items)
2. **Vor jeder neuen Batch:** Regression-Smoke der vorherigen abgeschlossenen Batches
3. **Keine Breaking Changes** die bereits grüne Tests wieder rot machen
4. **Fixes auf eigenem Branch:** `fix/ui-test-batchXX-*`

---

## Fortschritt

- Abgeschlossen: 3/13
- In Arbeit: (bereit für B04)
- Letzte Aktualisierung: 2026-03-14

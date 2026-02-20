#!/usr/bin/env python3
"""Test: Download und Übersetzung für 'Akame ga Kill! – Kill the Darkness' über die API.

Voraussetzungen:
- Sublarr-Backend läuft (z. B. npm run dev:backend → :5765)
- Sonarr konfiguriert, Serie in der Library
- Optional: SUBLARR_API_KEY in .env wenn API-Key aktiv
- DB-Migration: Falls /wanted oder /episodes/... 500 liefern, ggf. Migration anwenden
  (Spalte wanted_items.retry_after). Z. B. im Backend: flask db upgrade
  oder Spalte manuell anlegen.

Ablauf:
1. Library abfragen, Serie per Titel suchen (Akame / Kill the Darkness)
2. Entweder: Wanted-Items für die Serie → POST /wanted/<id>/process
3. Oder: Episode mit Datei wählen → Search-Provider → Download+Übersetzung für ersten Treffer
"""

import os
import sys

import requests

BASE_URL = os.environ.get("SUBLARR_API_BASE", "http://localhost:5765")
API_PREFIX = "/api/v1"
API_KEY = os.environ.get("SUBLARR_API_KEY", "")


def req(method: str, path: str, **kwargs) -> requests.Response:
    url = f"{BASE_URL}{API_PREFIX}{path}"
    headers = kwargs.pop("headers", {})
    if API_KEY:
        headers["X-Api-Key"] = API_KEY
    return requests.request(method, url, headers=headers, timeout=60, **kwargs)


def main():
    print("Sublarr Test: Akame ga Kill! – Kill the Darkness (Download + Übersetzung)")
    print("Base URL:", BASE_URL)
    print()

    # 1) Library
    r = req("GET", "/library")
    if r.status_code != 200:
        print("Fehler: /library ->", r.status_code, r.text[:500])
        return 1
    data = r.json()
    series_list = data.get("series") or []
    if not series_list:
        print("Keine Serien in der Library (Sonarr konfiguriert und verbunden?).")
        return 1

    # 2) Serie finden
    series = None
    for s in series_list:
        title = (s.get("title") or "").lower()
        if "akame" in title or "kill the darkness" in title:
            series = s
            break
    if not series:
        print("Serie 'Akame ga Kill! / Kill the Darkness' nicht gefunden. Vorhandene Serien (Auszug):")
        for s in series_list[:15]:
            print(" -", s.get("title"))
        return 1

    series_id = series["id"]
    print("Serie gefunden:", series.get("title"), "(ID:", series_id, ")")
    print()

    # 3) Wanted-Items für diese Serie (API liefert "data", nicht "items")
    r = req("GET", "/wanted", params={"series_id": series_id, "status": "wanted", "per_page": 10})
    if r.status_code != 200:
        print("Hinweis: /wanted ->", r.status_code, "(nutze Episoden-Pfad)")
        items = []
    else:
        wanted_data = r.json()
        items = wanted_data.get("data") or wanted_data.get("items") or []
    total = len(items)

    if items:
        # Ein Wanted-Item verarbeiten (kompletter Pipeline: Suche → Download → Übersetzung)
        item_id = items[0]["id"]
        title = items[0].get("title", "")
        season_ep = items[0].get("season_episode", "")
        print(f"Wanted-Item gefunden: ID {item_id} – {title} {season_ep}")
        print("Starte Process (Download + Übersetzung) …")
        r = req("POST", f"/wanted/{item_id}/process")
        if r.status_code in (200, 202):
            body = r.json()
            print("Erfolg:", body.get("status", body))
            if body.get("status") == "processing":
                print("Läuft asynchron; Fortschritt per WebSocket (wanted_item_processed).")
            return 0
        print("Fehler: /wanted/<id>/process ->", r.status_code, r.text[:400])
        return 1

    # 4) Keine Wanted-Items → Serie-Detail, erste Episode mit Datei, dann Search + Download+Übersetzung
    print("Keine Wanted-Items für diese Serie. Versuche Episode-Suche …")
    r = req("GET", f"/library/series/{series_id}")
    if r.status_code != 200:
        print("Fehler: /library/series/<id> ->", r.status_code)
        return 1
    detail = r.json()
    episodes = detail.get("episodes") or []
    episode_id = None
    for ep in episodes:
        if ep.get("has_file"):
            episode_id = ep.get("id")
            break
    if not episode_id:
        print("Keine Episode mit Datei gefunden. Bitte zuerst in Sonarr eine Episode herunterladen.")
        return 1

    print("Episode mit Datei:", episode_id)
    r = req("GET", f"/episodes/{episode_id}/search-providers")
    if r.status_code != 200:
        print("Fehler: /episodes/<id>/search-providers ->", r.status_code, r.text[:300])
        return 1
    search_data = r.json()
    results = search_data.get("results") or []
    if not results:
        print("Keine Untertitel-Treffer von den Providern.")
        return 1

    first = results[0]
    provider_name = first.get("provider_name", "")
    subtitle_id = first.get("subtitle_id", "")
    language = first.get("language", "en")
    print("Erster Treffer:", provider_name, "| Sprache:", language)
    print("Starte Download + Übersetzung …")
    r = req(
        "POST",
        f"/episodes/{episode_id}/download-specific",
        json={
            "provider_name": provider_name,
            "subtitle_id": subtitle_id,
            "language": language,
            "translate": True,
        },
    )
    if r.status_code == 200:
        out = r.json()
        print("Erfolg:", out.get("path", out))
        return 0
        print("Fehler: /episodes/<id>/download-specific ->", r.status_code, r.text[:400])
    return 1


if __name__ == "__main__":
    sys.exit(main())

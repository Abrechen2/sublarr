"""Seed a fresh Sublarr Discord server with starter content per channel."""
from __future__ import annotations

import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

TOKEN = os.environ["DISCORD_BOT_TOKEN"]
GUILD = os.environ["GUILD_ID"]
BASE = "https://discord.com/api/v10"
REPO_ROOT = Path(__file__).resolve().parent.parent
HEAD = {
    "Authorization": f"Bot {TOKEN}",
    "User-Agent": "SublarrSetup (https://sublarr.de, 1.0)",
}


def req(method, path, body=None, content_type="application/json"):
    url = BASE + path
    headers = dict(HEAD)
    if body is not None and isinstance(body, (dict, list)):
        data = json.dumps(body).encode()
        headers["Content-Type"] = content_type
    else:
        data = body
    r = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(r) as resp:
        t = resp.read().decode("utf-8", errors="replace")
        time.sleep(0.35)
        return json.loads(t) if t else {}


def multipart_post(path, payload_json: dict, files: list[tuple[str, Path]]):
    """POST /channels/X/messages with attachments. files = [(name, path), ...]"""
    boundary = f"--------------boundary{uuid.uuid4().hex}"
    body = b""
    # payload_json part
    body += f"--{boundary}\r\n".encode()
    body += b'Content-Disposition: form-data; name="payload_json"\r\n'
    body += b"Content-Type: application/json\r\n\r\n"
    body += json.dumps(payload_json).encode() + b"\r\n"
    # file parts
    for i, (name, fpath) in enumerate(files):
        mt = mimetypes.guess_type(str(fpath))[0] or "application/octet-stream"
        with open(fpath, "rb") as f:
            content = f.read()
        body += f"--{boundary}\r\n".encode()
        body += (
            f'Content-Disposition: form-data; name="files[{i}]"; filename="{name}"\r\n'
            f"Content-Type: {mt}\r\n\r\n"
        ).encode()
        body += content + b"\r\n"
    body += f"--{boundary}--\r\n".encode()

    headers = dict(HEAD)
    headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    r = urllib.request.Request(BASE + path, data=body, method="POST", headers=headers)
    with urllib.request.urlopen(r) as resp:
        t = resp.read().decode("utf-8", errors="replace")
        time.sleep(0.35)
        return json.loads(t)


# ---------- Posts ----------

ANNOUNCEMENTS = """🎉 **Sublarr Discord is live!**

Welcome to the official Sublarr community. This server is for:
• 🛠️ **Install help** — Docker, Unraid, Proxmox, bare-metal
• 🎬 **Provider tuning** — OpenSubtitles, AnimeTosho, Jimaku, SubDL
• 🧪 **Beta testing** the next release (opt in by reacting 🧪 in <#rules>)
• 💬 **General self-hoster chat**

**Where to find what**
• Code: <https://github.com/abrechen2/sublarr>
• Docs: <https://sublarr.de/docs/>
• Website: <https://sublarr.de>
• Reddit: <https://www.reddit.com/r/Sublarr/>

Current release: **v0.53.1-beta**. Next milestone: **V1.0.0** (competitive parity with Bazarr/Lingarr + polished onboarding). See the roadmap in #changelog via GitHub webhooks.

Say hi in <#general>. 👋"""

GENERAL = """Welcome! 👋

This is **#general** — the open chat for everything Sublarr-related.

**Quick icebreaker — introduce yourself:**
• What's your library scale? (episode count, series count)
• What are you running Sublarr on? (Docker? Unraid? Proxmox? Bare-metal?)
• What brought you here? (anime focus / Bazarr refugee / curious?)

No pressure. But it helps the community answer questions better when we know the rough landscape."""

SHOWCASE_INTRO = """Starting the #showcase channel with a tour of what's currently in Sublarr v0.53.1-beta. All screenshots from a live instance running against a ~560 series / 5,800 subtitle library.

**What Sublarr looks like right now:**"""

SHOWCASE_SHOTS = [
    ("reddit-06-live-activity.png",
     "**Dashboard — Live Activity Feed**\nReal-time SocketIO feed of every download as it lands. Right sidebar: per-provider health, services, disk usage, quick actions."),
    ("reddit-01-dashboard-hero.png",
     "**Dashboard overview**\nTop stats + full provider breakdown. All 10 configured providers are Healthy."),
    ("reddit-03-keys-pool.png",
     "**Multi-key pool (v0.53.0-beta)**\nEach provider can hold multiple API keys with different tiers. The scheduler picks the best one per request and cools a key down automatically on 429."),
    ("reddit-04-burst-mode.png",
     "**API-Pacing Mode**\nBudget scheduler with 3 modes: Stretch (even), Burst (front-load), Adaptive (usage-based). Adaptive Backoff learns per-provider 429 limits over time."),
    ("reddit-07-activity-history.png",
     "**Downloads history**\nFull audit log with per-provider filter, language, format (SRT/ASS), score, and retry action."),
    ("reddit-02-dedup-cross-episode.png",
     "**Duplicate scanner — cross-episode safe**\nUnlike most dedup tools, Sublarr warns when a hash-match crosses episode boundaries (orange badge) so you never delete an S01E10 thinking it's a dupe of S02E10."),
    ("reddit-05-series-override.png",
     "**Per-series scheduler override**\nOn any series detail page: priority override + minimum attempts per day. So your currently-airing anime gets scanned aggressively while your archive runs on backlog."),
    ("reddit-08-wizard.png",
     "**First-run wizard**\nDetects hardware and suggests a scheduler profile. Three clicks to a working setup."),
]

INSTALL_HELP = """**📋 Posting Template — please include:**

```
• Sublarr version:  (see /api/v1/health or top-right sidebar)
• Deployment:       Docker Compose / Unraid / Proxmox CT / bare-metal
• Host OS:          Ubuntu 22 / Unraid 6.12 / Debian 12 / …
• Database:         sqlite (default) / postgres / …
• Reverse proxy:    none / nginx / Traefik / Caddy / …
• Mounts:           /config → ..., /media → ...

WHAT I EXPECTED:
  e.g. "wanted search should pick up new episode X"

WHAT HAPPENED:
  e.g. "wanted list empty, search never runs"

LOGS:
  `docker logs sublarr --tail 100` (paste as code block or file attachment)

WHAT I ALREADY TRIED:
  1. …
  2. …
```

Paste the above as a code block (triple-backticks) at the top of your question. Thanks — makes help 10× faster.

**Common first-run gotchas**
• `/media` must be the **same path mount** that Sonarr/Radarr see. If they see `/media/tv` and Sublarr sees `/tvshows`, path-mapping is needed.
• If the container boots but health check fails → permissions on `/config` (run as your UID:GID, not root).
• If subtitles aren't found → enable more providers in Settings → Providers."""

PROVIDERS_OVERVIEW = """**Current provider status** (as of v0.53.1-beta, 2026-04-18)

**Built-in and working:**
• `opensubtitles` (VIP-tier key supported, multi-key pool)
• `animetosho` — anime focus, AniDB IDs
• `jimaku` — Japanese + anime subs
• `subdl`
• `gestdown` — TV-focused
• `kitsunekko` — anime
• `napisy24`
• `titrari`
• `subscene`
• `addic7ed`
• `tvsubtitles`

**Hidden by default** (low quality / niche):
• `legendasdivx`, `turkcealtyazi`, `whisper_subgen`

**Tips**
• If you get 429s, check the budget dashboard — the scheduler learns limits automatically but a manual tier upgrade (free → VIP) in the Key editor helps.
• Provider priority is configurable in Settings. Higher priority = tried first.
• Each provider can be disabled without removing it (soft-disable).
• For per-series needs, use Scheduler Override on the series detail page.

**Known limitations**
• Some providers (addic7ed, gestdown) rate-limit anon requests heavily — add credentials if you can.
• `jimaku` needs an API key (free at jimaku.cc)."""

CONTRIBUTING = """**Want to contribute? 🎉**

Sublarr is a solo project that's starting to open up. Here's how to help:

**Good first issues**
Filter GitHub for `good first issue`:
<https://github.com/abrechen2/sublarr/issues?q=is%3Aopen+label%3A%22good+first+issue%22>

**Dev setup (5 min)**
```bash
git clone https://github.com/abrechen2/sublarr
cd sublarr
npm run install:all      # installs backend deps + frontend deps
npm run dev              # runs Flask (:5765) + Vite (:5173)
```

**Before you PR**
• Read `CLAUDE.md` in the repo root (coding conventions)
• Run the backend lint + tests:
  ```
  cd backend && ruff check . && python -m pytest
  ```
• Run frontend lint + tests:
  ```
  cd frontend && npm run lint && npm run test -- --run
  ```

**Commit style**
Conventional Commits: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`.

**What's the roadmap?**
See `docs/superpowers/specs/2026-04-18-v1-competitive-parity.md` in the repo — Phase 5–10 covers everything between now and V1.0.0.

Questions → ping here. PRs welcome!"""

PLUGIN_DEV = """**Writing a custom provider or post-processor?**

**Full API reference:**
<https://sublarr.de/docs/development/plugin-development/>

**Minimum provider skeleton** (Python):
```python
from providers.base import SubtitleProvider, SubtitleResult

class MyProvider(SubtitleProvider):
    name = "myprovider"
    rate_limits = {"second": 1, "hour": 100, "day": 1000}

    def search(self, query: SearchQuery) -> list[SubtitleResult]:
        # return list of SubtitleResult(url, lang, format, score, provider_id)
        ...

    def download(self, result: SubtitleResult) -> bytes:
        # return raw subtitle bytes (srt/ass/vtt)
        ...
```

Drop it in `backend/providers/` and it auto-registers.

**Post-processing hooks**
See `backend/services/post_processing/` for the chain pattern — each step is a small class with a `process(path, metadata) -> (path, metadata)` method. Easy to add your own (e.g. custom style-override, font substitution).

Questions? Ping here. Expect reply within a day."""


def post_msg(channel_id: str, content: str):
    m = req("POST", f"/channels/{channel_id}/messages", {"content": content})
    print(f"  posted to channel {channel_id} (msg id {m['id']})")
    return m


def main():
    chans = req("GET", f"/guilds/{GUILD}/channels")
    by_name = {c["name"]: c for c in chans}

    def cid(name):
        return by_name[name]["id"]

    print("Seeding Discord server")

    # 1. #announcements
    print("→ #announcements launch message")
    post_msg(cid("announcements"), ANNOUNCEMENTS)

    # 2. #general intro
    print("→ #general icebreaker")
    m = post_msg(cid("general"), GENERAL)
    try:
        req("PUT", f"/channels/{cid('general')}/pins/{m['id']}")
        print("  pinned")
    except Exception as e:
        print(f"  pin failed: {e}")

    # 3. #showcase — intro + screenshots
    print("→ #showcase intro + 8 screenshots")
    post_msg(cid("showcase"), SHOWCASE_INTRO)
    shots_dir = REPO_ROOT
    for fname, caption in SHOWCASE_SHOTS:
        fpath = shots_dir / fname
        if not fpath.exists():
            print(f"  skip missing: {fname}")
            continue
        multipart_post(
            f"/channels/{cid('showcase')}/messages",
            {"content": caption},
            [(fname, fpath)],
        )
        print(f"  uploaded: {fname}")

    # 4. #install-help template
    print("→ #install-help template")
    m = post_msg(cid("install-help"), INSTALL_HELP)
    try:
        req("PUT", f"/channels/{cid('install-help')}/pins/{m['id']}")
        print("  pinned")
    except Exception as e:
        print(f"  pin failed: {e}")

    # 5. #providers overview
    print("→ #providers overview")
    m = post_msg(cid("providers"), PROVIDERS_OVERVIEW)
    try:
        req("PUT", f"/channels/{cid('providers')}/pins/{m['id']}")
        print("  pinned")
    except Exception as e:
        print(f"  pin failed: {e}")

    # 6. #contributing
    print("→ #contributing starter")
    m = post_msg(cid("contributing"), CONTRIBUTING)
    try:
        req("PUT", f"/channels/{cid('contributing')}/pins/{m['id']}")
        print("  pinned")
    except Exception as e:
        print(f"  pin failed: {e}")

    # 7. #plugin-dev
    print("→ #plugin-dev starter")
    m = post_msg(cid("plugin-dev"), PLUGIN_DEV)
    try:
        req("PUT", f"/channels/{cid('plugin-dev')}/pins/{m['id']}")
        print("  pinned")
    except Exception as e:
        print(f"  pin failed: {e}")

    print("\nstarter posts complete")


if __name__ == "__main__":
    main()

"""One-shot cleanup: remove German template defaults, re-parent rules/mod-only."""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

TOKEN = os.environ["DISCORD_BOT_TOKEN"]
GUILD = os.environ["GUILD_ID"]
HEAD = {
    "Authorization": f"Bot {TOKEN}",
    "Content-Type": "application/json",
    "User-Agent": "SublarrSetup (https://sublarr.de, 1.0)",
}


def req(method: str, path: str, body: dict | None = None):
    url = f"https://discord.com/api/v10{path}"
    data = None if body is None else json.dumps(body).encode()
    r = urllib.request.Request(url, data=data, method=method, headers=HEAD)
    try:
        with urllib.request.urlopen(r) as resp:
            t = resp.read().decode()
            time.sleep(0.3)
            return json.loads(t) if t else {}
    except urllib.error.HTTPError as e:
        return {"__err": e.code, "__body": e.read().decode()[:250]}


def main():
    chans = req("GET", f"/guilds/{GUILD}/channels")
    if isinstance(chans, dict) and "__err" in chans:
        print(f"list failed: {chans}")
        return

    # 1. delete German template defaults
    for c in chans:
        if c["name"] in ("Textkanäle", "Sprachkanäle", "Allgemein"):
            r = req("DELETE", f"/channels/{c['id']}")
            status = r.get("__err", "ok") if isinstance(r, dict) else "ok"
            print(f"del {c['name']!r} (type={c['type']}): {status}")
            if isinstance(r, dict) and "__err" in r:
                print(f"   body: {r['__body']}")

    # refresh list + re-parent orphans
    chans = req("GET", f"/guilds/{GUILD}/channels")
    by_name = {c["name"]: c for c in chans}
    info_id = by_name["INFO"]["id"]
    staff_id = by_name["STAFF"]["id"]

    for name, parent in [("rules", info_id), ("moderator-only", staff_id)]:
        if name in by_name:
            r = req("PATCH", f"/channels/{by_name[name]['id']}", {"parent_id": parent})
            status = r.get("__err", "ok") if isinstance(r, dict) else "ok"
            print(f"move {name!r} -> parent: {status}")
            if isinstance(r, dict) and "__err" in r:
                print(f"   body: {r['__body']}")

    print("cleanup complete")


if __name__ == "__main__":
    main()

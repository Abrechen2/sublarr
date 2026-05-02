"""
Sublarr Discord server provisioning.

Reads DISCORD_BOT_TOKEN + GUILD_ID from environment. Never persists them.
Idempotent for roles/categories/channels by name: existing entries are reused.

Usage:
    DISCORD_BOT_TOKEN='...' GUILD_ID='...' python discord_setup.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

BASE = "https://discord.com/api/v10"
TOKEN = os.environ["DISCORD_BOT_TOKEN"]
GUILD = os.environ["GUILD_ID"]
HEADERS = {
    "Authorization": f"Bot {TOKEN}",
    "Content-Type": "application/json",
    "User-Agent": "SublarrSetup (https://sublarr.de, 1.0)",
}


def req(method: str, path: str, body: dict | None = None) -> dict:
    url = BASE + path
    data = None if body is None else json.dumps(body).encode()
    r = urllib.request.Request(url, data=data, method=method, headers=HEADERS)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(r) as resp:
                text = resp.read().decode()
                time.sleep(0.25)  # polite global rate-limit
                return json.loads(text) if text else {}
        except urllib.error.HTTPError as e:
            payload = e.read().decode()
            if e.code == 429:
                retry = json.loads(payload).get("retry_after", 1.0)
                print(f"  rate-limited, sleeping {retry}s")
                time.sleep(retry + 0.1)
                continue
            raise RuntimeError(f"HTTP {e.code} on {method} {path}: {payload}")
    raise RuntimeError(f"giving up after 5 retries on {method} {path}")


# ---------- Role definitions ----------
# Create from top-to-bottom in Discord display order. Discord assigns position
# at creation time; later we PATCH positions. Admin only temporarily for setup.
ROLES = [
    {"name": "Maintainer", "color": 0x0F9BB5, "hoist": True, "permissions": "8", "mentionable": True},
    {"name": "Moderator",  "color": 0xE67E22, "hoist": True, "permissions": "1099780115462", "mentionable": True},
    {"name": "Contributor","color": 0x2ECC71, "hoist": True, "permissions": "0", "mentionable": True},
    {"name": "Beta-Tester","color": 0x3498DB, "hoist": True, "permissions": "0", "mentionable": True},
]
# permissions "1099780115462" = view + send + manage_messages + kick + ban + timeout + moderate_members

CATEGORIES = ["INFO", "COMMUNITY", "SUPPORT", "DEV", "BETA", "STAFF", "VOICE"]

TEXT_CHANNELS = [
    # (name, category, topic, private_role_name_or_None)
    ("welcome", "INFO",
     "Welcome to Sublarr! GitHub: github.com/abrechen2/sublarr · Docs: sublarr.de/docs · Website: sublarr.de. Read #rules before posting.",
     None),
    ("announcements", "INFO",
     "Official announcements from the maintainer team. Releases, breaking changes, security notices.",
     None),
    ("changelog", "INFO",
     "Auto-feed: every master commit + every GitHub release.",
     None),

    ("general", "COMMUNITY",
     "General Sublarr chat. English preferred; other languages welcome in threads.",
     None),
    ("showcase", "COMMUNITY",
     "Show your setup! Screenshots, library stats, infra configs. No piracy content.",
     None),
    ("off-topic", "COMMUNITY",
     "Anything not Sublarr.",
     None),

    ("install-help", "SUPPORT",
     "Docker, Unraid, Proxmox, bare-metal help. Posting template: version · deployment · logs · what have you tried?",
     None),
    ("providers", "SUPPORT",
     "Provider integrations (OpenSubtitles, AnimeTosho, Jimaku, SubDL). For 429 errors, attach a rate-limit dashboard screenshot.",
     None),
    ("translation", "SUPPORT",
     "Ollama setup, DeepL fallback, glossary tuning, fine-tuning questions.",
     None),

    ("plugin-dev", "DEV",
     "Custom providers, post-processing hooks, webhook integrations. API reference: sublarr.de/docs/development/plugin-development",
     None),
    ("contributing", "DEV",
     "How-to-PR, coding conventions, test setup. Read CLAUDE.md first.",
     None),

    ("beta-channel", "BETA",
     "Pre-release tests. @Beta-Tester only. React with 🧪 in #rules to join.",
     "Beta-Tester"),
    ("beta-feedback", "BETA",
     "Feedback on beta builds — broken, improved, missing?",
     "Beta-Tester"),

    ("mod-chat", "STAFF",
     "Moderator-only chat.",
     "Moderator"),
    ("mod-log", "STAFF",
     "AutoMod events, kicks, bans, audit trail.",
     "Moderator"),
]

VOICE_CHANNELS = [
    ("General", "VOICE", None),
    ("Pair-Programming", "VOICE", None),
]

# ---------- Main setup ----------

def slug(n: str) -> str:
    return n.lower().strip()


def run():
    print(f"Setting up guild {GUILD}")

    # 1. Fetch existing state
    existing_channels = req("GET", f"/guilds/{GUILD}/channels")
    existing_roles = req("GET", f"/guilds/{GUILD}/roles")
    print(f"  existing: {len(existing_channels)} channels, {len(existing_roles)} roles")

    role_by_name = {r["name"]: r for r in existing_roles}
    chan_by_slug = {slug(c["name"]): c for c in existing_channels}

    # 2. Create missing roles
    print("\n[1/6] Creating roles")
    for r in ROLES:
        if r["name"] in role_by_name:
            print(f"  skip: {r['name']} already exists")
            continue
        created = req("POST", f"/guilds/{GUILD}/roles", r)
        role_by_name[r["name"]] = created
        print(f"  created: {r['name']} (id={created['id']})")

    # 3. Create missing categories
    print("\n[2/6] Creating categories")
    cat_ids: dict[str, str] = {}
    for name in CATEGORIES:
        if slug(name) in chan_by_slug:
            c = chan_by_slug[slug(name)]
            if c["type"] == 4:
                cat_ids[name] = c["id"]
                print(f"  skip: {name} category already exists")
                continue
        created = req("POST", f"/guilds/{GUILD}/channels",
                      {"name": name, "type": 4})
        cat_ids[name] = created["id"]
        chan_by_slug[slug(name)] = created
        print(f"  created: {name} (id={created['id']})")

    # 4. Create text channels + topics, set category parent
    print("\n[3/6] Creating text channels")
    text_ids: dict[str, str] = {}
    for name, cat, topic, private_role in TEXT_CHANNELS:
        body = {
            "name": name,
            "type": 0,
            "topic": topic,
            "parent_id": cat_ids[cat],
        }
        if private_role:
            body["permission_overwrites"] = [
                {"id": GUILD, "type": 0, "deny": "1024"},  # @everyone: deny view
                {"id": role_by_name[private_role]["id"], "type": 0, "allow": "1024"},
            ]
        if slug(name) in chan_by_slug:
            c = chan_by_slug[slug(name)]
            if c["type"] == 0:
                text_ids[name] = c["id"]
                patch = {k: v for k, v in body.items() if k != "type"}
                req("PATCH", f"/channels/{c['id']}", patch)
                print(f"  update: {name} (id={c['id']})")
                continue
        created = req("POST", f"/guilds/{GUILD}/channels", body)
        text_ids[name] = created["id"]
        chan_by_slug[slug(name)] = created
        print(f"  created: {name} (id={created['id']})")

    # 5. Create voice channels
    print("\n[4/6] Creating voice channels")
    for name, cat, _ in VOICE_CHANNELS:
        if slug(name) in chan_by_slug and chan_by_slug[slug(name)]["type"] == 2:
            print(f"  skip: voice {name} already exists")
            continue
        created = req("POST", f"/guilds/{GUILD}/channels",
                      {"name": name, "type": 2, "parent_id": cat_ids[cat]})
        chan_by_slug[slug(name)] = created
        print(f"  created: voice {name} (id={created['id']})")

    # 6. Move existing forum channels (bug-report, feature-request) into SUPPORT / DEV
    print("\n[5/6] Re-parenting existing forum channels")
    for cname, parent in [("bug-report", "SUPPORT"), ("feature-request", "DEV")]:
        if cname in chan_by_slug:
            c = chan_by_slug[cname]
            req("PATCH", f"/channels/{c['id']}", {"parent_id": cat_ids[parent]})
            print(f"  moved: {cname} → {parent}")

    # 7. AutoMod rules
    print("\n[6/6] AutoMod rules")
    try:
        existing_am = req("GET", f"/guilds/{GUILD}/auto-moderation/rules")
        am_names = {r["name"] for r in existing_am}
    except RuntimeError as e:
        am_names = set()
        print(f"  warn: could not list AutoMod rules ({e})")

    automod_rules = [
        {
            "name": "Slur filter",
            "event_type": 1,
            "trigger_type": 4,  # keyword preset
            "trigger_metadata": {"presets": [1, 2, 3]},  # profanity, sexual, slurs
            "actions": [{"type": 1}],  # block
            "enabled": True,
        },
        {
            "name": "Mention spam",
            "event_type": 1,
            "trigger_type": 5,  # mention spam
            "trigger_metadata": {"mention_total_limit": 5},
            "actions": [{"type": 1}, {"type": 3, "metadata": {"duration_seconds": 600}}],
            "enabled": True,
        },
    ]
    for rule in automod_rules:
        if rule["name"] in am_names:
            print(f"  skip: AutoMod '{rule['name']}' exists")
            continue
        try:
            req("POST", f"/guilds/{GUILD}/auto-moderation/rules", rule)
            print(f"  created: AutoMod '{rule['name']}'")
        except RuntimeError as e:
            print(f"  warn: AutoMod '{rule['name']}' failed ({e})")

    # 8. Post welcome and rules messages
    print("\n[Welcome + Rules messages]")
    welcome_en = (
        "👋 **Welcome to Sublarr!**\n\n"
        "Sublarr is a self-hosted subtitle manager — tuned for anime libraries "
        "and ASS-preserving workflows. Focus: format fidelity (no automatic "
        "ASS → SRT downgrade), resilient provider usage, per-series fine-tuning.\n\n"
        "**🔗 Quick Links**\n"
        "• GitHub: <https://github.com/abrechen2/sublarr>\n"
        "• Docs: <https://sublarr.de/docs/>\n"
        "• Website: <https://sublarr.de>\n"
        "• Reddit: <https://www.reddit.com/r/Sublarr/>\n\n"
        "**🚀 Get Started**\n"
        f"1. Read <#{chan_by_slug.get('rules', {}).get('id', '0')}>\n"
        f"2. Say hi in <#{text_ids.get('general', '0')}>\n"
        f"3. Install questions → <#{text_ids.get('install-help', '0')}>\n"
        f"4. Bugs → file a GitHub Issue first, then <#{chan_by_slug.get('bug-report', {}).get('id', '0')}>\n\n"
        "**🧪 Join the beta?**\n"
        f"React with 🧪 in <#{chan_by_slug.get('rules', {}).get('id', '0')}> to unlock the Beta-Tester channels.\n\n"
        "Enjoy!"
    )
    rules_text = (
        "📜 **Server Rules**\n\n"
        "**1. Be respectful** — no insults, harassment, or hate speech.\n"
        "**2. No piracy content** — we're a subtitle manager, not a warez forum. "
        "No release-group links, torrent sites, streaming mirrors. Subtitle providers are fine.\n"
        "**3. Language** — DE and EN. Other languages welcome in private threads.\n"
        "**4. Post correctly** — use the matching channel. File bugs on GitHub first.\n"
        "**5. No spam / heavy self-promotion** — blatant ads removed.\n"
        "**6. No private data** — no API keys, IPs, or credentials in logs you post.\n"
        "**7. Mods have the final say** — comply and DM the maintainer if you disagree.\n\n"
        "Violation → Warning → Timeout → Kick → Ban.\n\n"
        "React with 🧪 below to join the Beta-Tester channels."
    )

    welcome_id = text_ids.get("welcome")
    if welcome_id:
        msg = req("POST", f"/channels/{welcome_id}/messages", {"content": welcome_en})
        req("PUT", f"/channels/{welcome_id}/pins/{msg['id']}")
        print(f"  posted welcome + pinned")

    rules_id = chan_by_slug.get("rules", {}).get("id")
    if rules_id:
        msg = req("POST", f"/channels/{rules_id}/messages", {"content": rules_text})
        req("PUT", f"/channels/{rules_id}/pins/{msg['id']}")
        # add 🧪 reaction so users can opt in
        import urllib.parse as up
        req("PUT", f"/channels/{rules_id}/messages/{msg['id']}/reactions/{up.quote('🧪')}/@me")
        print(f"  posted rules + pinned + 🧪 reaction")

    # 9. Create GitHub webhooks
    print("\n[GitHub webhooks]")
    webhook_urls = {}
    for cname in ("changelog", "announcements"):
        cid = text_ids.get(cname)
        if not cid:
            continue
        wh = req("POST", f"/channels/{cid}/webhooks",
                 {"name": "GitHub"})
        webhook_urls[cname] = f"https://discord.com/api/webhooks/{wh['id']}/{wh['token']}/github"
        print(f"  webhook created for #{cname}")

    print("\n========================================")
    print("DONE. Next step: add these to GitHub")
    print("========================================")
    for cname, url in webhook_urls.items():
        print(f"\n#{cname}  →  Payload URL:")
        print(f"  {url}")
    print("\nAt github.com/abrechen2/sublarr/settings/hooks → Add webhook")
    print("  Content type: application/json")
    print("  #changelog:     Pushes + Releases + Issues + PRs + Stars")
    print("  #announcements: Releases only")


if __name__ == "__main__":
    try:
        run()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

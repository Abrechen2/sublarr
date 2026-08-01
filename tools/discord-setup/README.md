# Sublarr Discord CLI

Standalone `discord.js` utility for the Sublarr Discord server. It reads
channels on demand, replies in forum threads and text channels, and posts
release announcements. One shot per invocation — it logs in, acts and
disconnects. There is no daemon and no listener.

Ported from the equivalent TravStats tool, minus the server-provisioning half:
Sublarr's server was built by hand and is not managed as code.

| Command | What it does |
|---|---|
| `npm run read` | List every channel with its type and id |
| `npm run read <channel> [limit]` | Text channel: last `limit` messages (default 20, max 100), oldest first. Forum: recent posts and their messages |
| `npm run reply -- <thread\|channel> <message…\|--file <path>> [--dry-run]` | Post into a forum thread (id or unique title substring) or an exactly-named text channel |
| `npm run announce -- <beta\|rc\|release> [version] [--notes-file <path>\|--notes <text>] [--dry-run]` | Post a release embed built from `CHANGELOG.md` (or the given notes) plus the GitHub tag link |

`npm run read` needs no `--` because it takes no flags. `reply` and `announce`
do, because npm would otherwise try to interpret `--dry-run` / `--file` /
`--notes-file` as its own flags rather than passing them through.

## Release announcements: this is the only path

There is no fallback automation. If nobody runs `announce`, no announcement
happens. A GitHub Actions workflow used to post release embeds automatically,
but it was retired 2026-08-01 (commit `f00a29f3`) along with the two GitHub
repo webhooks that duplicated it and the orphaned `DISCORD_WEBHOOK_*` repo
secrets — that workflow posted under the release author's own GitHub login
and avatar, so announcements appeared to come from a real person instead of
the project. `announce` posts under the bot's identity instead, and only on
explicit approval.

## Setup

```bash
cd tools/discord-setup
npm install
cp .env.example .env      # then paste the token in an EDITOR, not via the shell
npm run read              # should list the guild's channels
```

`DISCORD_BOT_TOKEN` is a secret; its source of truth is Infisical (project
`sublarr`, environment `prod`). `DISCORD_GUILD_ID` is not a secret — the
default in `.env.example` is correct and needs no change.

**Bot permissions:** View Channels, Read Message History, Send Messages, Send
Messages in Threads, Embed Links — bitmask `274877991936`. No Administrator —
nothing is provisioned. No Create Public Threads either: the tool only
answers in threads that already exist, never opens new ones.

The two easy-to-miss permissions both fail late, not early:

- **Send Messages in Threads** — plain `Send Messages` does not cover posting
  into a forum thread. `#bug-report`, `reply`'s main real-world target, is a
  forum. Without this permission a `reply --dry-run` looks fine (it never
  posts) and the real send then fails.
- **Embed Links** — required to send an embed at all. `announce` always
  sends an embed, so without this permission its dry run (which never
  connects — see below) previews perfectly and the real post then fails.

## Never post without approval

Every write is dry-run first, shown to the owner, and sent only after an
explicit go-ahead. A public post cannot be taken back. Reading needs no
approval.

Three rails back this up in code:

- `announce --dry-run` returns **before** `login()` — no connection, no send.
- Text channels resolve by **exact** name only. A substring match would
  resolve `general` to `#general-dev`.
- `read` and `announce` resolve channels through the same exact-name rule
  (`channelResolve.ts`), restricted to message-capable types (text,
  announcement, forum, thread) and aborting — logging every candidate — on an
  ambiguous match instead of guessing. This matters in practice, not just in
  theory: the guild has a real lowercase collision, a text `#general` and a
  voice `#General`, and voice channels satisfy discord.js's `isTextBased()`
  too. `reply` applies the equivalent rule itself (`resolveReplyTarget`),
  since it also needs to search forum threads.

## Troubleshooting

**Every message reads `(no text content)`** — the bot lacks the privileged
Message Content intent. This is required in practice (confirmed by live
testing: forum posts from real users came back empty while a message the bot
itself had posted came through fine — the empty-server look is exactly what
made this hard to diagnose at first). It is enabled now. If it ever gets
disabled again: Developer Portal → your application → Bot → Privileged
Gateway Intents → enable **Message Content**. The placeholder exists
precisely so this failure is visible; a blank line would otherwise look like
an empty channel.

**`Unknown Guild`** — the guild id is wrong. Discord → Settings → Advanced →
Developer Mode on, right-click the server icon → Copy Server ID.

**`Used disallowed intents`** — an intent is enabled in the portal that the
code does not declare. The code asks for `Guilds` only.

## Development

```bash
npm run typecheck
npm test
```

Pure functions (changelog extraction, embed building, target resolution,
message formatting) are unit-tested. The live Discord I/O has no offline mock
and is verified against the real guild instead — mocking the gateway would
test the mock, not the bot.

#!/bin/sh
set -e

# Runtime UID/GID — Unraid Community Apps passes PUID=99 / PGID=100; other
# hosts vary. The image's bundled "sublarr" user is built at uid/gid 1000.
# We remap it to the requested ids at start so file ownership on the mounted
# /config volume matches the host.
PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

if [ "$(id -g sublarr 2>/dev/null)" != "$PGID" ]; then
    groupmod -o -g "$PGID" sublarr
fi
if [ "$(id -u sublarr 2>/dev/null)" != "$PUID" ]; then
    usermod -o -u "$PUID" sublarr
fi

# /config is a bind-mounted volume, frequently created root-owned by the host
# (e.g. a fresh Unraid appdata directory). Without this chown the SQLite
# database cannot be created and the worker crash-loops with
# "sqlite3.OperationalError: unable to open database file".
# /media is intentionally left untouched — it is the user's library, may be
# very large, and its access is governed by the host's own permissions.
chown -R "$PUID:$PGID" /config 2>/dev/null || true

# Files Sublarr writes into /media (extracted sidecars, remuxed containers,
# health fixes) must stay readable by the media server (Emby/Plex run as a
# different user). The default root umask (0022) is fine, but be explicit and
# allow a host override so subtitles never land mode 600/unreadable.
umask "${UMASK:-022}"

# Drop from root to the runtime user and hand off to gunicorn (the CMD).
exec gosu "$PUID:$PGID" "$@"

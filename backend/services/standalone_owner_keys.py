"""Pre-1.18 standalone rows: read where they are, copied on the first write.

Before 1.18.0 the standalone pages wrote a title's profile assignment,
settings, glossary entries and fansub preferences under its positive row id
whenever no Sonarr (series) or Radarr (movie) client was configured. Since
1.18.0 they are written under the owner key, the negated id
(docs/specs/standalone-ids.md), so standalone series 3 and Sonarr series 3
never share a row.

Whether a positive key belongs to the arr or to a standalone title cannot be
read from the row, so no row is ever moved, rewritten or deleted because of
it. Instead:

* Readers ask for the owner key first. When there is no row under it, the
  legacy positive key (= the standalone row id) is read instead, read-only,
  if all of these hold (``legacy_key``):

  - the matching arr (Sonarr for series, Radarr for movies) is not
    configured — a configured arr owns every positive key;
  - no durable evidence shows the install ever used that arr (a stored arr
    URL / instance list, a wanted row, translation job or automation queue
    row with an arr id; cached, see ``arr_evidence``);
  - the title has not claimed its rows yet (``standalone_legacy_claims``);
  - the standalone title exists.

* Writers write the owner key, as before. The first write for a title whose
  legacy rows are still readable first copies them to the owner key and
  records the claim (``claim``), in the writer's own transaction: changing
  one setting keeps the others, adding a glossary term keeps the old terms,
  and deleting under the owner key never brings the old rows back. The
  legacy rows themselves stay untouched.

Nothing runs at startup. The ``sa2_standalone_owner_keys`` marker that
release candidates of 1.18.0 wrote into ``untracked_data_repairs`` is no
longer read or written; it is harmless.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime

import sqlalchemy as sa

logger = logging.getLogger(__name__)

SERIES = "series"
MOVIE = "movie"

# Config keys whose non-empty value means the arr was set up at some point.
# A cleared field ("" / "[]") is no evidence.
_CONFIG_KEYS = {
    SERIES: ("sonarr_url", "sonarr_instances_json"),
    MOVIE: ("radarr_url", "radarr_instances_json"),
}

# (table, SQL condition) whose first match is evidence. Fixed SQL, no input.
# Only positive ids count: the automation queue stores the movie *owner key*,
# negative for a standalone movie.
_ID_EVIDENCE = {
    SERIES: (
        ("wanted_items", "sonarr_series_id > 0 OR sonarr_episode_id > 0"),
        ("jobs", "bazarr_context_json LIKE '%\"sonarr_%'"),
    ),
    MOVIE: (
        ("wanted_items", "radarr_movie_id > 0"),
        ("jobs", "bazarr_context_json LIKE '%\"radarr_%'"),
        ("subtitle_automation_queue", "radarr_movie_id > 0"),
    ),
}

# "No evidence" is re-checked after this many seconds; found evidence sticks
# for the life of the process (it only disappears when history is pruned).
_EVIDENCE_TTL_S = 300.0
_evidence_cache: dict[str, tuple[float, str | None]] = {}
_cache_lock = threading.Lock()


def reset_cache() -> None:
    """Forget cached evidence (tests; after a config change)."""
    with _cache_lock:
        _evidence_cache.clear()


def _session():
    from extensions import db

    return db.session


def _arr_configured(kind: str) -> bool:
    from services.media_ids import _radarr_configured, _sonarr_configured

    return _sonarr_configured() if kind == SERIES else _radarr_configured()


def _find_evidence(kind: str) -> str | None:
    session = _session()
    tables = set(sa.inspect(session.get_bind()).get_table_names())
    if "config_entries" in tables:
        for key in _CONFIG_KEYS[kind]:
            value = session.execute(
                sa.text("SELECT value FROM config_entries WHERE key = :k"), {"k": key}
            ).scalar()
            if value is not None and str(value).strip() not in ("", "[]"):
                return f"config_entries.{key} is set"
    for table, condition in _ID_EVIDENCE[kind]:
        if table not in tables:
            continue
        sql = f"SELECT 1 FROM {table} WHERE {condition} LIMIT 1"  # noqa: S608 — fixed SQL
        if session.execute(sa.text(sql)).first() is not None:
            return f"{table} rows with an arr id"
    return None


def arr_evidence(kind: str) -> str | None:
    """Why the install may have used this kind's arr, or ``None``.

    Cheap, durable signals only. Download history is deliberately not used:
    a deleted or renamed standalone title leaves history that looks foreign,
    and that would switch the fallback off for standalone-only installs.
    """
    now = time.monotonic()
    with _cache_lock:
        cached = _evidence_cache.get(kind)
    if cached is not None and (cached[1] is not None or now - cached[0] < _EVIDENCE_TTL_S):
        return cached[1]
    try:
        reason = _find_evidence(kind)
    except Exception:  # noqa: BLE001 — cannot tell: do not read positive keys
        logger.warning("Standalone legacy keys: evidence check failed", exc_info=True)
        return "evidence check failed"
    with _cache_lock:
        previous = _evidence_cache.get(kind)
        _evidence_cache[kind] = (now, reason)
    if reason and (previous is None or previous[1] is None):
        logger.warning(
            "Standalone legacy keys: %s; pre-1.18 settings saved under positive ids are not "
            "used for standalone %s",
            reason,
            "series" if kind == SERIES else "movies",
        )
    return reason


def _claimed(kind: str, standalone_id: int) -> bool:
    from db.models.standalone import StandaloneLegacyClaim

    return _session().get(StandaloneLegacyClaim, (kind, standalone_id)) is not None


def _standalone_exists(kind: str, standalone_id: int) -> bool:
    from db.models.standalone import StandaloneMovie, StandaloneSeries

    model = StandaloneSeries if kind == SERIES else StandaloneMovie
    return _session().get(model, standalone_id) is not None


def legacy_key(owner_key: int | None, kind: str) -> int | None:
    """The pre-1.18 positive key to read for a standalone owner key, or None.

    ``None`` for a Sonarr/Radarr key, a configured arr, arr evidence, a
    claimed title or an unknown title.
    """
    if owner_key is None or int(owner_key) >= 0:
        return None
    standalone_id = -int(owner_key)
    if _arr_configured(kind) or arr_evidence(kind):
        return None
    if _claimed(kind, standalone_id) or not _standalone_exists(kind, standalone_id):
        return None
    return standalone_id


def superseded_legacy(kind: str, standalone_id: int) -> bool:
    """A positive key that was a standalone title's and has been taken over.

    True while the arr is not configured and the standalone id is claimed:
    the row is then nobody's live data and is kept unchanged.
    """
    return not _arr_configured(kind) and _claimed(kind, int(standalone_id))


def readable_legacy_ids(kind: str) -> frozenset[int]:
    """Standalone ids whose positive-key rows may currently be read (bulk readers)."""
    if _arr_configured(kind) or arr_evidence(kind):
        return frozenset()
    from db.models.standalone import StandaloneMovie, StandaloneSeries

    model = StandaloneSeries if kind == SERIES else StandaloneMovie
    ids = {r[0] for r in _session().execute(sa.select(model.id))}
    return frozenset(ids - claimed_ids(kind))


def claimed_ids(kind: str) -> frozenset[int]:
    """Standalone ids that took their pre-1.18 rows over (or were deleted)."""
    from db.models.standalone import StandaloneLegacyClaim

    return frozenset(
        r[0]
        for r in _session().execute(
            sa.select(StandaloneLegacyClaim.standalone_id).where(StandaloneLegacyClaim.kind == kind)
        )
    )


def legacy_ids_as_owner_keys(kind: str, rows: list[tuple[int, object]]) -> list[tuple[int, object]]:
    """Bulk readers: ``(key, value)`` rows of one table with the fallback applied.

    With the arr configured the rows pass through unchanged. Without it, a
    positive key that is a readable legacy standalone id (and has no
    owner-key row in ``rows``) is reported under its owner key, and a
    superseded one (its title has an owner-key row in ``rows`` or claimed)
    is left out: it is nobody's live setting any more.
    """
    if not any(key and key > 0 for key, _ in rows) or _arr_configured(kind):
        return list(rows)
    keys = {key for key, _ in rows}
    readable = readable_legacy_ids(kind)
    claimed = claimed_ids(kind)
    out = []
    for key, value in rows:
        if key and key > 0 and (-key in keys or key in claimed):
            continue
        if key and key > 0 and key in readable:
            out.append((-key, value))
        else:
            out.append((key, value))
    return out


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------


def _single_row_models(kind: str):
    """(model, key column name) of the one-row-per-title tables of ``kind``."""
    from db.models.core import (
        FansubPreference,
        MovieLanguageProfile,
        MovieSettings,
        SeriesLanguageProfile,
        SeriesSettings,
    )

    if kind == SERIES:
        return (
            (SeriesLanguageProfile, "sonarr_series_id"),
            (SeriesSettings, "sonarr_series_id"),
            (FansubPreference, "sonarr_series_id"),
        )
    return ((MovieLanguageProfile, "radarr_movie_id"), (MovieSettings, "radarr_movie_id"))


def _kind_of(model) -> str:
    return MOVIE if model.__tablename__.startswith("movie_") else SERIES


def get_row(model, key: int | None):
    """The row of a one-row-per-title table for ``key``, with the legacy fallback.

    ``model`` is SeriesSettings, MovieSettings, SeriesLanguageProfile,
    MovieLanguageProfile or FansubPreference. A positive key is a plain
    primary-key lookup.
    """
    if not key:
        return None
    session = _session()
    row = session.get(model, int(key))
    if row is not None:
        return row
    legacy = legacy_key(key, _kind_of(model))
    return session.get(model, legacy) if legacy is not None else None


def row_for_write(model, key: int, **defaults):
    """The row to change for ``key``: claims the title first, creates it if missing.

    The new row is added to the session, not committed.
    """
    claim(key, _kind_of(model))
    session = _session()
    row = session.get(model, int(key))
    if row is None:
        key_col = model.__mapper__.primary_key[0].name
        row = model(**{key_col: int(key)}, **defaults)
        session.add(row)
    return row


def glossary_owner_key(series_id: int | None) -> int | None:
    """The series key whose glossary is read for ``series_id`` (legacy fallback)."""
    if series_id is None or int(series_id) >= 0:
        return series_id
    from db.models.translation import GlossaryEntry

    session = _session()
    has_own = session.execute(
        sa.select(GlossaryEntry.id).where(GlossaryEntry.series_id == int(series_id)).limit(1)
    ).first()
    if has_own is not None:
        return series_id
    legacy = legacy_key(series_id, SERIES)
    return legacy if legacy is not None else series_id


def _copy_single_rows(kind: str, owner_key: int, legacy: int) -> None:
    session = _session()
    for model, key_col in _single_row_models(kind):
        table = model.__table__
        if session.get(model, owner_key) is not None:
            continue
        others = [c.name for c in table.columns if c.name != key_col]
        session.execute(
            sa.insert(table).from_select(
                [key_col, *others],
                sa.select(sa.literal(owner_key), *[table.c[c] for c in others]).where(
                    table.c[key_col] == legacy
                ),
            )
        )


def _copy_glossary(owner_key: int, legacy: int) -> dict[int, int]:
    from db.models.translation import GlossaryEntry

    session = _session()
    if session.execute(
        sa.select(GlossaryEntry.id).where(GlossaryEntry.series_id == owner_key).limit(1)
    ).first():
        return {}
    fields = [c.name for c in GlossaryEntry.__table__.columns if c.name not in ("id", "series_id")]
    rows = session.execute(
        sa.select(GlossaryEntry).where(GlossaryEntry.series_id == legacy).order_by(GlossaryEntry.id)
    ).scalars()
    copies = [
        (old, GlossaryEntry(series_id=owner_key, **{f: getattr(old, f) for f in fields}))
        for old in rows
    ]
    session.add_all([new for _, new in copies])
    session.flush()
    return {old.id: new.id for old, new in copies}


def claim(owner_key: int | None, kind: str) -> dict[int, int] | None:
    """Before a write under ``owner_key``: take over the title's legacy rows.

    When the legacy rows are still readable (``legacy_key``), copies every
    one of them that has no owner-key counterpart yet to the owner key and
    records the claim, in the caller's session (committed with the caller's
    write). Returns ``{legacy glossary entry id: copy id}`` when it claimed,
    ``None`` when there was nothing to claim (Sonarr/Radarr keys, titles
    without readable legacy rows) or a concurrent writer claimed first.

    Call it before staging changes: losing a concurrent first-write race
    rolls the session back and leaves the winner's copy in place.
    """
    legacy = legacy_key(owner_key, kind)
    if legacy is None:
        return None
    from sqlalchemy.exc import IntegrityError

    from db.models.standalone import StandaloneLegacyClaim

    session = _session()
    try:
        session.add(
            StandaloneLegacyClaim(kind=kind, standalone_id=legacy, claimed_at=datetime.now(UTC))
        )
        session.flush()
        _copy_single_rows(kind, int(owner_key), legacy)
        mapping = _copy_glossary(int(owner_key), legacy) if kind == SERIES else {}
        session.flush()
    except IntegrityError:
        session.rollback()
        logger.debug("Standalone legacy claim for %s %s raced; using the winner's", kind, legacy)
        return None
    logger.info(
        "Standalone %s %d: copied its pre-1.18 settings to the new id on first change",
        kind,
        legacy,
    )
    return mapping


def delete_owner_rows(kind: str, standalone_id: int) -> int:
    """A deleted standalone title: remove every row stored under its owner key.

    Profile assignment, settings (incl. the foreign-track cleanup switch),
    fansub preferences and, for series, glossary entries. Only the negated
    id is touched; positive keys belong to Sonarr/Radarr or are pre-1.18
    rows (``claim_deleted_title`` stops those being read). Staged in the
    caller's session, so it commits with the title's delete. Returns the
    number of rows removed.
    """
    owner_key = -int(standalone_id)
    session = _session()
    removed = 0
    for model, key_col in _single_row_models(kind):
        table = model.__table__
        removed += session.execute(sa.delete(table).where(table.c[key_col] == owner_key)).rowcount
    if kind == SERIES:
        from db.models.translation import GlossaryEntry

        table = GlossaryEntry.__table__
        removed += session.execute(sa.delete(table).where(table.c.series_id == owner_key)).rowcount
    return removed


def claim_deleted_title(kind: str, standalone_id: int) -> None:
    """A deleted standalone title: its legacy rows are never read again.

    Without this a reused row id (SQLite reuses the highest id after a
    delete) would inherit them. Added to the caller's session.
    """
    if _claimed(kind, standalone_id):
        return
    from db.models.standalone import StandaloneLegacyClaim

    _session().add(
        StandaloneLegacyClaim(kind=kind, standalone_id=standalone_id, claimed_at=datetime.now(UTC))
    )

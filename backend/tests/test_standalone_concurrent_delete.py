"""Two cleanups deleting the same standalone title at once both succeed.

Found by the 1.18.0-rc.6 end-to-end test (R6): two DELETEs of one watched
folder 50 ms apart gave one HTTP 500 (UniqueViolation on
``standalone_legacy_claims_pkey``), and the scanner's prune failed the same
way. ``claim_deleted_title`` checked for the claim and then inserted it.

The race is replayed deterministically: right after this delete has looked
for the claim, a second connection plays the winner, claims the title,
deletes it and commits.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import sqlalchemy as sa

_NOW = datetime(2026, 10, 1, tzinfo=UTC)


def _series() -> int:
    from db.models.standalone import StandaloneSeries
    from extensions import db

    row = StandaloneSeries(
        title="Race", folder_path="/media/Race", created_at=_NOW, updated_at=_NOW
    )
    db.session.add(row)
    db.session.commit()
    return row.id


def _movie() -> int:
    from db.models.standalone import StandaloneMovie
    from extensions import db

    row = StandaloneMovie(
        title="Race", file_path="/media/Race.mkv", created_at=_NOW, updated_at=_NOW
    )
    db.session.add(row)
    db.session.commit()
    return row.id


def _winner_commits_first(monkeypatch, kind: str, table: str, standalone_id: int) -> None:
    """After this delete's claim lookup, another connection wins the race."""
    import services.standalone_owner_keys as keys
    from extensions import db

    real = keys._claimed
    done = []

    def racing(k, sid):
        result = real(k, sid)
        if not done:
            done.append(True)
            with db.engine.begin() as other:
                other.execute(
                    sa.text(
                        "INSERT INTO standalone_legacy_claims (kind, standalone_id, claimed_at) "
                        "VALUES (:k, :sid, :at)"
                    ),
                    {"k": kind, "sid": standalone_id, "at": _NOW},
                )
                other.execute(sa.text(f"DELETE FROM {table} WHERE id=:id"), {"id": standalone_id})
        return result

    monkeypatch.setattr(keys, "_claimed", racing)


def _claims() -> int:
    from extensions import db

    return db.session.execute(sa.text("SELECT COUNT(*) FROM standalone_legacy_claims")).scalar()


def test_a_series_deleted_concurrently_is_a_no_op(app_ctx, monkeypatch):
    from db.standalone import delete_standalone_series, get_standalone_series
    from services.standalone_manager import delete_series_cascade

    sid = _series()
    _winner_commits_first(monkeypatch, "series", "standalone_series", sid)

    delete_series_cascade(sid)  # raised IntegrityError before the fix

    assert get_standalone_series(sid) is None
    assert _claims() == 1
    # A later delete of the gone title is a no-op as well.
    assert delete_standalone_series(sid) is False


def test_a_movie_deleted_concurrently_is_a_no_op(app_ctx, monkeypatch):
    from db.standalone import delete_standalone_movie, get_standalone_movies
    from services.standalone_manager import delete_movie_cascade

    mid = _movie()
    _winner_commits_first(monkeypatch, "movie", "standalone_movies", mid)

    delete_movie_cascade(mid)

    assert get_standalone_movies(mid) is None
    assert _claims() == 1
    assert delete_standalone_movie(mid) is False


@pytest.mark.parametrize("kind", ["series", "movie"])
def test_claim_deleted_title_is_idempotent(app_ctx, kind):
    from extensions import db
    from services.standalone_owner_keys import claim_deleted_title

    claim_deleted_title(kind, 41)
    db.session.commit()
    # A claim that is already there (identity map cleared, as in another
    # request) is left alone instead of colliding.
    db.session.expunge_all()
    claim_deleted_title(kind, 41)
    db.session.commit()

    assert _claims() == 1


def test_a_folder_deleted_twice_at_once_answers_200_both_times(app_ctx, monkeypatch, tmp_path):
    from db.standalone import upsert_watched_folder

    monkeypatch.setattr("routes.standalone.folders._hot_reload_standalone", lambda: None)
    monkeypatch.setattr("routes.standalone.folders._media_path", lambda: "")
    monkeypatch.setattr("sonarr_client.get_sonarr_client", lambda *a, **kw: None)
    monkeypatch.setattr("radarr_client.get_radarr_client", lambda *a, **kw: None)
    from db.models.standalone import StandaloneSeries
    from extensions import db

    show = tmp_path / "lib" / "Race"
    show.mkdir(parents=True)
    row = StandaloneSeries(title="Race", folder_path=str(show), created_at=_NOW, updated_at=_NOW)
    db.session.add(row)
    db.session.commit()
    fid = upsert_watched_folder(path=str(tmp_path / "lib"))
    _winner_commits_first(monkeypatch, "series", "standalone_series", row.id)

    resp = app_ctx.test_client().delete(f"/api/v1/standalone/folders/{fid}")

    assert resp.status_code == 200, resp.get_json()
    assert db.session.execute(sa.text("SELECT COUNT(*) FROM standalone_series")).scalar() == 0

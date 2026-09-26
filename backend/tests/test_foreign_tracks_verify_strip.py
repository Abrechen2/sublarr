"""Deleting the original after a verified rewrite, built into the sweep (owner 2026-09-26).

The option is a NEW key, ``delete_original_after_verify``: the old
``verify_then_delete_backup`` never had an effect in 1.15.0 RCs, and an
auto-update must not silently arm a box someone ticked back then (owner).

A backup may only be deleted when the rewritten file is exactly what the
policy asked for: it probes, keeps every video/audio stream of the original,
and carries precisely the subtitle tracks the policy keeps from the original
— not one more (nothing left to strip) and not one less (nothing lost).
Anything else keeps the backup: a false negative costs disk for the
retention period, a false positive costs the original.
"""

from unittest.mock import patch

from services.foreign_tracks.select import TrackPolicy

_B = TrackPolicy(
    mode="one_per_language", keep_forced=True, keep_sdh=False, sidecar_policy="drop_if_real_sidecar"
)
_KEEP = {"de", "ger", "deu", "en", "eng"}


def _v(index):
    return {"index": index, "codec_type": "video", "codec_name": "h264"}


def _a(index, lang="jpn"):
    return {"index": index, "codec_type": "audio", "codec_name": "aac", "tags": {"language": lang}}


def _s(index, lang, codec="ass", title=None, frames=None):
    tags = {"language": lang}
    if title:
        tags["title"] = title
    if frames is not None:
        tags["NUMBER_OF_FRAMES"] = str(frames)
    return {"index": index, "codec_type": "subtitle", "codec_name": codec, "tags": tags}


ORIGINAL = [
    _v(0),
    _a(1),
    _s(2, "eng", "ass", "English", 400),
    _s(3, "eng", "hdmv_pgs_subtitle", "English", 800),
    _s(4, "ger", "ass", "German", 390),
    _s(5, "fre", "ass", "French", 380),
]
GOOD = [_v(0), _a(1), _s(2, "eng", "ass", "English", 400), _s(3, "ger", "ass", "German", 390)]


def _verify(original, result, tmp_path, real=frozenset()):
    from services.foreign_tracks.verify import verify_strip

    video = tmp_path / "e1.mkv"
    video.write_bytes(b"new")
    backup = tmp_path / "e1.mkv.bak"
    backup.write_bytes(b"old")

    def probe(path, use_cache=True):
        return {"streams": original if str(path) == str(backup) else result}

    with patch("remux.get_media_streams", side_effect=probe):
        return verify_strip(str(video), str(backup), _B, _KEEP, False, set(real))


def test_an_exact_result_verifies(tmp_path):
    ok, why = _verify(ORIGINAL, GOOD, tmp_path)
    assert ok, why


def test_a_lost_kept_track_fails(tmp_path):
    ok, why = _verify(ORIGINAL, [_v(0), _a(1), _s(2, "eng", "ass", "English", 400)], tmp_path)
    assert not ok
    assert "de" in why


def test_a_track_the_policy_would_strip_fails(tmp_path):
    left = GOOD + [_s(4, "fre", "ass", "French", 380)]
    ok, why = _verify(ORIGINAL, left, tmp_path)
    assert not ok


def test_a_lost_audio_track_fails(tmp_path):
    ok, why = _verify(ORIGINAL + [_a(6, "ger")], GOOD, tmp_path)
    assert not ok
    assert "audio" in why


def test_no_video_fails(tmp_path):
    ok, _ = _verify(ORIGINAL, [s for s in GOOD if s["codec_type"] != "video"], tmp_path)
    assert not ok


def test_an_empty_file_fails(tmp_path):
    from services.foreign_tracks.verify import verify_strip

    video = tmp_path / "e1.mkv"
    video.write_bytes(b"")
    backup = tmp_path / "e1.mkv.bak"
    backup.write_bytes(b"old")
    ok, why = verify_strip(str(video), str(backup), _B, _KEEP, False, set())
    assert not ok


def test_an_unprobeable_result_fails(tmp_path):
    from services.foreign_tracks.verify import verify_strip

    video = tmp_path / "e1.mkv"
    video.write_bytes(b"new")
    backup = tmp_path / "e1.mkv.bak"
    backup.write_bytes(b"old")
    with patch("remux.get_media_streams", side_effect=RuntimeError("ffprobe died")):
        ok, why = verify_strip(str(video), str(backup), _B, _KEEP, False, set())
    assert not ok
    assert "probe" in why


def test_policy_b_with_a_real_sidecar_expects_the_main_track_gone(tmp_path):
    """Under B with a real German sidecar the German main track is stripped —
    a result WITHOUT it is exactly right."""
    result = [_v(0), _a(1), _s(2, "eng", "ass", "English", 400)]
    ok, why = _verify(ORIGINAL, result, tmp_path, real={"de"})
    assert ok, why


# --- the sweep uses it ---------------------------------------------------------


def _sweep_strip(tmp_path, monkeypatch, config, verified):
    import remux
    from services.foreign_tracks import sweep as sw

    video = tmp_path / "e1.mkv"
    video.write_bytes(b"new")
    backup = tmp_path / "e1.mkv.bak"
    backup.write_bytes(b"old")
    notified = []

    class _Row:
        path = str(video)
        track_count = 2

    rows = [_Row()]

    class _Repo:
        def claim_next_affected(self):
            return rows.pop() if rows else None

        def mark_stripped(self, path):
            pass

        def mark_failed(self, *a, **k):
            raise AssertionError("must not fail")

        def mark_probed_verdicts(self, *a, **k):
            pass

    monkeypatch.setattr(sw, "_media_root_reachable", lambda root: True)
    monkeypatch.setattr(sw, "_free_bytes", lambda root: 10**15)
    monkeypatch.setattr(sw, "_strip_file", lambda *a, **k: (str(backup), 1000))
    monkeypatch.setattr(sw, "_real_sidecars_for_policy", lambda *a, **k: set())
    monkeypatch.setattr(sw, "verify_strip", lambda *a, **k: (verified, "reason"), raising=False)
    monkeypatch.setattr(
        "services.media_server_notify.notify_media_servers",
        lambda path, item_type="": notified.append(path),
    )
    from services.foreign_tracks.state import SweepState

    state = SweepState(phase="strip", enumeration_complete=True)
    result = {"stripped_files": 0, "tracks_removed": 0, "bytes_freed": 0}
    clock = iter(range(0, 10_000))
    sw._strip_phase(
        str(tmp_path),
        config,
        state,
        _Repo(),
        _KEEP,
        False,
        _B,
        [],
        10_000,
        lambda: next(clock),
        result,
        (),
    )
    return backup.exists(), notified, result, remux


def test_the_sweep_deletes_a_verified_backup_when_the_option_is_on(tmp_path, monkeypatch):
    exists, notified, result, _ = _sweep_strip(
        tmp_path, monkeypatch, {"delete_original_after_verify": True}, verified=True
    )
    assert not exists
    assert result.get("backups_deleted") == 1


def test_the_sweep_keeps_an_unverified_backup(tmp_path, monkeypatch):
    exists, _, result, _ = _sweep_strip(
        tmp_path, monkeypatch, {"delete_original_after_verify": True}, verified=False
    )
    assert exists
    assert result.get("verify_failed") == 1


def test_the_sweep_keeps_the_backup_when_the_option_is_off(tmp_path, monkeypatch):
    exists, _, _, _ = _sweep_strip(tmp_path, monkeypatch, {}, verified=True)
    assert exists


def test_the_sweep_tells_the_media_servers_about_a_rewrite(tmp_path, monkeypatch):
    _, notified, _, _ = _sweep_strip(tmp_path, monkeypatch, {}, verified=True)
    assert notified == [str(tmp_path / "e1.mkv")]


def test_the_legacy_key_alone_never_deletes_a_backup(tmp_path, monkeypatch):
    """Ticked before the upgrade, when it did nothing: must stay inert until
    the user confirms it through the new option."""
    exists, _, result, _ = _sweep_strip(
        tmp_path, monkeypatch, {"verify_then_delete_backup": True}, verified=True
    )
    assert exists
    assert "backups_deleted" not in result

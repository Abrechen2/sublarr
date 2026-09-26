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


def _s(index, lang, codec="ass", title=None, frames=None, **disposition):
    tags = {"language": lang}
    if title:
        tags["title"] = title
    if frames is not None:
        tags["NUMBER_OF_FRAMES"] = str(frames)
    stream = {"index": index, "codec_type": "subtitle", "codec_name": codec, "tags": tags}
    if disposition:
        stream["disposition"] = {k: int(v) for k, v in disposition.items()}
    return stream


ORIGINAL = [
    _v(0),
    _a(1),
    _s(2, "eng", "ass", "English", 400),
    _s(3, "eng", "hdmv_pgs_subtitle", "English", 800),
    _s(4, "ger", "ass", "German", 390),
    _s(5, "fre", "ass", "French", 380),
]
GOOD = [_v(0), _a(1), _s(2, "eng", "ass", "English", 400), _s(3, "ger", "ass", "German", 390)]


def _verify(original, result, tmp_path, real=frozenset(), policy=_B):
    from services.foreign_tracks.verify import verify_strip

    video = tmp_path / "e1.mkv"
    video.write_bytes(b"new")
    backup = tmp_path / "e1.mkv.bak"
    backup.write_bytes(b"old")

    def probe(path, use_cache=True):
        assert use_cache is False, "verification must never trust a cached probe"
        return {"streams": original if str(path) == str(backup) else result}

    with patch("ass_probe.run_ffprobe", side_effect=probe):
        return verify_strip(str(video), str(backup), policy, _KEEP, False, set(real))


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
    with patch("ass_probe.run_ffprobe", side_effect=RuntimeError("ffprobe died")):
        ok, why = verify_strip(str(video), str(backup), _B, _KEEP, False, set())
    assert not ok
    assert "probe" in why


def test_policy_b_with_a_real_sidecar_expects_the_main_track_gone(tmp_path):
    """Under B with a real German sidecar the German main track is stripped —
    a result WITHOUT it is exactly right."""
    result = [_v(0), _a(1), _s(2, "eng", "ass", "English", 400)]
    ok, why = _verify(ORIGINAL, result, tmp_path, real={"de"})
    assert ok, why


# --- the kept tracks must be the RIGHT ones, not just the right count (review C1) ---


def test_the_wrong_track_of_the_right_language_fails(tmp_path):
    """The policy keeps ENG ASS; a rewrite that kept ENG PGS instead has the
    same per-language count and must still keep its backup."""
    wrong = [
        _v(0),
        _a(1),
        _s(2, "eng", "hdmv_pgs_subtitle", "English", 800),
        _s(3, "ger", "ass", "German", 390),
    ]
    ok, why = _verify(ORIGINAL, wrong, tmp_path)
    assert not ok, why


def test_a_forced_track_kept_instead_of_the_full_one_fails(tmp_path):
    """keep_forced=False: the full German track is kept, the forced one goes.
    A rewrite that kept only the forced track re-decides it as the lone
    ``kept_last_track`` — the count matches, the track does not."""
    policy = TrackPolicy(mode="one_per_language", keep_forced=False, keep_sdh=False)
    original = [
        _v(0),
        _a(1),
        _s(2, "ger", "ass", "German", 390),
        _s(3, "ger", "ass", "Signs & Songs", 40, forced=1),
    ]
    wrong = [_v(0), _a(1), _s(2, "ger", "ass", "Signs & Songs", 40, forced=1)]
    right = [_v(0), _a(1), _s(2, "ger", "ass", "German", 390)]
    assert _verify(original, right, tmp_path, policy=policy)[0]
    ok, why = _verify(original, wrong, tmp_path, policy=policy)
    assert not ok, why


def test_values_the_remux_rewrites_do_not_fail_the_check(tmp_path):
    """mkvmerge renumbers streams and rewrites its statistics tags — neither
    may make a correct rewrite look wrong."""
    rewritten = [
        _v(0),
        _a(1),
        _s(2, "eng", "ass", "English", 401),
        _s(3, "ger", "ass", "German", None),
    ]
    ok, why = _verify(ORIGINAL, rewritten, tmp_path)
    assert ok, why


def test_a_changed_forced_flag_fails(tmp_path):
    original = [_v(0), _a(1), _s(2, "ger", "ass", "German", 390, forced=0)]
    result = [_v(0), _a(1), _s(2, "ger", "ass", "German", 390, forced=1)]
    ok, _ = _verify(original, result, tmp_path)
    assert not ok


def test_a_changed_default_flag_is_not_a_different_track(tmp_path):
    """ffmpeg (MP4 path) sets default on the first track when none is set — a
    correct remux; failing on it would only keep backups for no reason."""
    original = [_v(0), _a(1), _s(2, "ger", "ass", "German", 390, default=0)]
    result = [_v(0), _a(1), _s(2, "ger", "ass", "German", 390, default=1)]
    ok, why = _verify(original, result, tmp_path)
    assert ok, why


# --- probing (review M2) ---------------------------------------------------------


def test_verification_probes_with_ffprobe_whatever_the_metadata_engine(tmp_path, monkeypatch):
    """With scan_metadata_engine=mediainfo, the engine-routed probe drops the
    video stream, so every rewrite would fail with "no video". The check must
    use ffprobe itself, uncached."""
    from services.foreign_tracks.verify import verify_strip

    video = tmp_path / "e1.mkv"
    video.write_bytes(b"new")
    backup = tmp_path / "e1.mkv.bak"
    backup.write_bytes(b"old")

    def ffprobe(path, use_cache=True):
        assert use_cache is False
        return {"streams": ORIGINAL if str(path) == str(backup) else GOOD}

    def engine(path, use_cache=True):
        streams = ORIGINAL if str(path) == str(backup) else GOOD
        return {"streams": [s for s in streams if s["codec_type"] != "video"]}

    with (
        patch("ass_probe.run_ffprobe", side_effect=ffprobe),
        patch("remux.get_media_streams", side_effect=engine),
        patch("ass_probe.get_media_streams", side_effect=engine),
    ):
        ok, why = verify_strip(str(video), str(backup), _B, _KEEP, False, set())
    assert ok, why


def test_the_strip_decision_uses_a_fresh_probe(tmp_path):
    """The keep/strip decision must never come from a probe cached for a file
    that has since been rewritten under the same path."""
    import remux

    video = tmp_path / "e1.mkv"
    video.write_bytes(b"v")
    calls = []

    def probe(path, *args, **kwargs):
        calls.append(kwargs.get("use_cache", args[0] if args else True))
        return {"streams": [_v(0), _a(1), _s(2, "ger", "ass", "German", 390)]}

    with (
        patch("remux.get_media_streams", side_effect=probe),
        patch("remux.check_hardlink_policy", return_value=True),
    ):
        assert (
            remux.remove_foreign_subtitle_streams(video_path=str(video), target_languages=_KEEP)
            is None
        )
    assert calls == [False]


# --- the sweep uses it ---------------------------------------------------------


def _sweep_strip(tmp_path, monkeypatch, config, verified, batch=None):
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
    monkeypatch.setattr(
        "services.media_server_notify.notify_media_servers_batch",
        batch or (lambda paths: notified.extend(paths)),
        raising=False,
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


def test_the_sweep_refreshes_the_media_servers_once_per_slice(tmp_path, monkeypatch):
    """Night review I1: one synchronous refresh per rewritten file (with a
    library-scan fallback on every miss) stalled the slice; the rewritten
    paths are collected and handed over once, after the loop."""
    from services.foreign_tracks import sweep as sw
    from services.foreign_tracks.state import SweepState

    paths = []
    for name in ("e1.mkv", "e2.mkv"):
        (tmp_path / name).write_bytes(b"new")
        (tmp_path / (name + ".bak")).write_bytes(b"old")
        paths.append(str(tmp_path / name))

    class _Row:
        def __init__(self, path):
            self.path = path
            self.track_count = 1

    rows = [_Row(p) for p in reversed(paths)]
    per_file, batches = [], []

    class _Repo:
        def claim_next_affected(self):
            return rows.pop() if rows else None

        def mark_stripped(self, path):
            assert batches == [], "the refresh must come after the slice's rewrites"

        def mark_failed(self, *a, **k):
            raise AssertionError("must not fail")

        def mark_probed_verdicts(self, *a, **k):
            pass

    monkeypatch.setattr(sw, "_media_root_reachable", lambda root: True)
    monkeypatch.setattr(sw, "_free_bytes", lambda root: 10**15)
    monkeypatch.setattr(sw, "_strip_file", lambda path, *a, **k: (path + ".bak", 10))
    monkeypatch.setattr(sw, "_real_sidecars_for_policy", lambda *a, **k: set())
    monkeypatch.setattr(
        "services.media_server_notify.notify_media_servers",
        lambda path, item_type="": per_file.append(path),
    )
    monkeypatch.setattr(
        "services.media_server_notify.notify_media_servers_batch",
        lambda p: batches.append(list(p)),
        raising=False,
    )
    clock = iter(range(0, 10_000))
    sw._strip_phase(
        str(tmp_path),
        {},
        SweepState(phase="strip", enumeration_complete=True),
        _Repo(),
        _KEEP,
        False,
        _B,
        [],
        10_000,
        lambda: next(clock),
        {"stripped_files": 0, "tracks_removed": 0, "bytes_freed": 0},
        (),
    )
    assert per_file == []
    assert batches == [paths]


def test_a_failing_refresh_never_breaks_the_slice(tmp_path, monkeypatch):
    def boom(paths):
        raise RuntimeError("media server down")

    exists, _, result, _ = _sweep_strip(
        tmp_path, monkeypatch, {"delete_original_after_verify": True}, verified=True, batch=boom
    )
    assert result["stripped_files"] == 1
    assert result["backups_deleted"] == 1
    assert not exists

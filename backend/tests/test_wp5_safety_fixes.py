"""Tests for the smaller safety fixes from the #159 audit.

- Subtitle-health sweep honours its (previously dead) enable settings.
- GET /library/trash no longer purges expired batches as a side effect.
- purge_signs_after_extract only touches sidecars produced by this pass.
- Auto-mods skip modifier variants (.hi/.forced/...) and combined files.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _settings(**overrides):
    s = MagicMock()
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


class TestSubtitleHealthSweepGate:
    def test_sweep_disabled_is_a_noop(self):
        from services.subtitle_health import sweep as sweep_mod

        with (
            patch(
                "config.get_settings",
                return_value=_settings(
                    subtitle_health_enabled=True,
                    subtitle_health_sweep_enabled=False,
                    subtitle_health_auto_fix=True,
                ),
            ),
            patch("services.subtitle_health.sweep.get_sonarr_client") as mock_client,
        ):
            sweep_mod.subtitle_health_sweep_tick()

        mock_client.assert_not_called()

    def test_feature_disabled_is_a_noop(self):
        from services.subtitle_health import sweep as sweep_mod

        with (
            patch(
                "config.get_settings",
                return_value=_settings(
                    subtitle_health_enabled=False,
                    subtitle_health_sweep_enabled=True,
                    subtitle_health_auto_fix=True,
                ),
            ),
            patch("services.subtitle_health.sweep.get_sonarr_client") as mock_client,
        ):
            sweep_mod.subtitle_health_sweep_tick()

        mock_client.assert_not_called()

    def test_enabled_sweep_proceeds(self):
        from services.subtitle_health import sweep as sweep_mod

        client = MagicMock()
        client.get_series.return_value = []

        with (
            patch(
                "config.get_settings",
                return_value=_settings(
                    subtitle_health_enabled=True,
                    subtitle_health_sweep_enabled=True,
                    subtitle_health_auto_fix=False,
                ),
            ),
            patch("services.subtitle_health.sweep.get_sonarr_client", return_value=client),
        ):
            sweep_mod.subtitle_health_sweep_tick()

        client.get_series.assert_called_once()


class TestTrashListNoPurge:
    def test_get_trash_does_not_auto_purge(self, client):
        """Opening the Trash page must never rmtree expired batches."""
        with patch("routes.subtitles.trash._auto_purge_old_trash") as mock_purge:
            resp = client.get("/api/v1/library/trash")

        assert resp.status_code == 200
        mock_purge.assert_not_called()


class TestSignsPurgeScope:
    def test_preexisting_forced_sidecar_survives_scoped_purge(self, tmp_path):
        """Only the sidecars extracted in THIS pass are purge candidates —
        a user's pre-existing forced sub must survive an unrelated extract."""
        from services import embedded_extractor

        video = tmp_path / "Ep.mkv"
        video.write_bytes(b"fake")
        # Pre-existing, user-supplied forced variant + full peer.
        preexisting_forced = tmp_path / "Ep.de.forced.srt"
        preexisting_forced.write_text("forced", encoding="utf-8")
        full_de = tmp_path / "Ep.de.srt"
        full_de.write_text("dialogue", encoding="utf-8")
        # This pass extracted an English signs track + full peer.
        extracted_signs = tmp_path / "Ep.en.signs.ass"
        extracted_signs.write_text("signs", encoding="utf-8")
        full_en = tmp_path / "Ep.en.ass"
        full_en.write_text("dialogue", encoding="utf-8")

        s = MagicMock()
        s.cleanup_signs_removal_level = "signs"

        with (
            patch("config.get_settings", return_value=s),
            patch("services.embedded_extractor._trash_path", return_value=True) as trash,
        ):
            embedded_extractor.purge_signs_after_extract(
                str(video),
                extracted_paths=[str(extracted_signs), str(full_en)],
            )

        trashed = [c.args[0] for c in trash.call_args_list]
        assert str(extracted_signs) in trashed
        assert str(preexisting_forced) not in trashed, "pre-existing sidecars are not purge fodder"


class TestAutoModsSkipVariants:
    def test_hi_variant_is_exempt(self, tmp_path):
        from routes.subtitle_processor import _is_processing_exempt_sidecar

        assert _is_processing_exempt_sidecar(str(tmp_path / "Ep.en.hi.srt")) is True
        assert _is_processing_exempt_sidecar(str(tmp_path / "Ep.en.forced.srt")) is True
        assert _is_processing_exempt_sidecar(str(tmp_path / "Ep.en.srt")) is False

    def test_combined_file_is_exempt(self, tmp_path):
        from routes.subtitle_processor import _is_processing_exempt_sidecar

        assert _is_processing_exempt_sidecar(str(tmp_path / "Ep.de-en.combined.ass")) is True

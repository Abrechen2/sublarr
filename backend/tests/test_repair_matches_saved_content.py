"""Repair must hash the download the same way save_subtitle did — or it proves nothing.

``save_subtitle()`` does not store the provider's bytes as they arrive. It
sanitises them, runs the B5 repair pass over them, writes *that*, and records the
hash of *that*. So the pristine hash in ``subtitle_hashes`` is the hash of the
**normalised** content.

Repair re-downloads the raw provider bytes. Comparing those against the stored
hash fails for every file — on production all 10 files of the first dry run came
back "provider_changed", which is precisely the gate refusing to overwrite
something it could not prove. Correct behaviour, wrong input.

Both paths now go through one function, so they cannot drift apart again.
"""

import pysubs2

from subtitle_normalise import normalise_downloaded_content


def _srt_with_things_to_normalise() -> bytes:
    """Content that the sanitiser and the B5 pass both have an opinion about."""
    return (
        "﻿1\r\n"  # BOM + CRLF
        "00:00:01,000 --> 00:00:03,000\r\n"
        "<b>Hallo</b> <script>alert(1)</script> Welt\r\n"
        "\r\n"
        "2\r\n"
        "00:00:02,500 --> 00:00:05,000\r\n"  # overlaps the previous cue
        "Zweite Zeile\r\n"
    ).encode()


def test_normalisation_actually_changes_the_bytes(app_ctx):
    """Sanity: if it were a no-op, the whole bug would not exist."""
    raw = _srt_with_things_to_normalise()

    normalised = normalise_downloaded_content(raw, "srt")

    assert normalised != raw
    assert b"<script>" not in normalised


def test_it_is_idempotent(app_ctx):
    """Normalising the already-normalised content must not move it again.

    Repair hands the normalised original to the restore step; if a second pass
    changed it, the hash proof would be unstable.
    """
    raw = _srt_with_things_to_normalise()

    once = normalise_downloaded_content(raw, "srt")
    twice = normalise_downloaded_content(once, "srt")

    assert once == twice


def test_the_hash_matches_what_save_subtitle_would_store(app_ctx):
    """The stored pristine hash is the hash of the NORMALISED content."""
    from dedup_engine import compute_content_hash_from_bytes

    raw = _srt_with_things_to_normalise()

    stored_hash = compute_content_hash_from_bytes(normalise_downloaded_content(raw, "srt"))
    raw_hash = compute_content_hash_from_bytes(raw)

    assert stored_hash != raw_hash, "raw bytes must not be mistaken for the saved content"


def test_the_content_still_parses(app_ctx):
    normalised = normalise_downloaded_content(_srt_with_things_to_normalise(), "srt")

    subs = pysubs2.SSAFile.from_string(normalised.decode("utf-8"), format_="srt")

    assert len(subs.events) == 2
    assert "Hallo" in subs.events[0].plaintext

"""Shadowing: an embedded-track finding is suppressed once a clean sidecar of
the same language exists (players prefer the external sidecar, so the language
is effectively healthy). This stops the embedded finding from reappearing on
every rescan after the user extracted a clean sidecar."""

from services.subtitle_health.models import Issue, IssueType, Severity, TargetKind
from services.subtitle_health.scan import apply_shadowing


def _issue(kind, lang, itype=IssueType.ASS_ESCAPE_LEAK):
    return Issue(
        type=itype,
        severity=Severity.CONFIRMED,
        episode_id=5,
        target_kind=kind,
        target_path=f"/m/x.{lang}.srt" if kind == TargetKind.SIDECAR else "/m/x.mkv",
        stream_index=None if kind == TargetKind.SIDECAR else 0,
        lang=lang,
        count=1,
        snippets=[],
        raw_hash="h",
        fixable=True,
        suggested_fix="repair_escapes",
    )


def test_embedded_finding_shadowed_by_clean_sidecar_same_lang():
    embedded = _issue(TargetKind.EMBEDDED, "ger")  # 3-letter tag
    issues = [embedded]
    apply_shadowing(issues, sidecar_langs={"de"})  # clean .de.srt present
    assert embedded.shadowed is True


def test_not_shadowed_when_no_sidecar_for_lang():
    embedded = _issue(TargetKind.EMBEDDED, "ger")
    issues = [embedded]
    apply_shadowing(issues, sidecar_langs={"en"})  # only a foreign-lang sidecar
    assert embedded.shadowed is False


def test_not_shadowed_when_the_sidecar_itself_is_defective():
    embedded = _issue(TargetKind.EMBEDDED, "de")
    bad_sidecar = _issue(TargetKind.SIDECAR, "de")  # sidecar also has a defect
    issues = [embedded, bad_sidecar]
    apply_shadowing(issues, sidecar_langs={"de"})
    assert embedded.shadowed is False  # no CLEAN sidecar → still actionable


def test_sidecar_findings_are_never_shadowed():
    bad_sidecar = _issue(TargetKind.SIDECAR, "de")
    issues = [bad_sidecar]
    apply_shadowing(issues, sidecar_langs={"en"})
    assert bad_sidecar.shadowed is False

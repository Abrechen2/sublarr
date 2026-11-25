"""The repair replay keeps the 1.6.5 common fixes (#44/#45 follow-up).

The live short_line_merge now joins with the ASS break \\N; the 1.6.5 code
joined with a raw LF. The replay must keep the historical behaviour, or a
file damaged by 1.6.5 no longer replays byte for byte and repair refuses it.
"""

import pysubs2


def _two_short_events():
    subs = pysubs2.SSAFile()
    subs.events = [
        pysubs2.SSAEvent(start=0, end=1000, text="Hi"),
        pysubs2.SSAEvent(start=1100, end=2000, text="there"),
    ]
    return subs


def test_replay_merges_like_1_6_5():
    from services.repair.legacy_common_fixes import apply_common_fixes

    subs = _two_short_events()
    apply_common_fixes(subs, {"short_line_merge": True})
    assert subs.events[0].text == "Hi\nthere"


def test_live_code_merges_with_the_ass_break():
    from common_fixes import apply_common_fixes

    subs = _two_short_events()
    apply_common_fixes(subs, {"short_line_merge": True})
    assert subs.events[0].text == "Hi\\Nthere"

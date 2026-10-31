"""The dashboard's "Missing" counts items that still have no subtitle.

Audit #61 A27: it showed every wanted row — on prod 8 791, of which 7 517
were upgrade candidates and 683 provisional machine translations, against
590 episodes really without a subtitle.
"""


def test_missing_leaves_out_upgrades_provisional_and_extracted(client):
    with client.application.app_context():
        from db.wanted import get_wanted_summary, update_wanted_status, upsert_wanted_item

        upsert_wanted_item("episode", "/media/a.mkv", title="A", target_language="de")
        upsert_wanted_item(
            "episode", "/media/b.mkv", title="B", target_language="de", upgrade_candidate=True
        )
        row, _ = upsert_wanted_item("episode", "/media/c.mkv", title="C", target_language="de")
        update_wanted_status(row, "provisional")
        row, _ = upsert_wanted_item("episode", "/media/d.mkv", title="D", target_language="de")
        update_wanted_status(row, "extracted")

        summary = get_wanted_summary()

    assert summary["total"] == 4
    assert summary["missing"] == 1

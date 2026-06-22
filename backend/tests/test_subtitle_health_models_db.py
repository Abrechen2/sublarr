def test_subtitle_health_tables_exist(app_ctx):
    from sqlalchemy import inspect

    from extensions import db

    insp = inspect(db.engine)
    assert insp.has_table("subtitle_health_findings")
    assert insp.has_table("subtitle_health_fixes")

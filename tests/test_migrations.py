from __future__ import annotations

from sqlalchemy import create_engine, text

from autofag.storage.db import Base, add_missing_columns


def _legacy_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}", future=True)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE watch_entries ("
                "id INTEGER PRIMARY KEY, course_code VARCHAR(32), course_name TEXT,"
                "auto_enroll INTEGER, created_at DATETIME)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO watch_entries (course_code, course_name, auto_enroll, created_at)"
                " VALUES ('IN5170', 'Models of concurrency', 1, '2026-08-24 00:00:00')"
            )
        )
    return engine


def test_a_new_column_is_added_to_an_existing_database(tmp_path):
    engine = _legacy_database(tmp_path)

    added = add_missing_columns(engine)

    assert "watch_entries.dialog_choices" in added
    with engine.begin() as connection:
        row = connection.execute(
            text("SELECT course_code, dialog_choices FROM watch_entries")
        ).one()
    assert row.course_code == "IN5170"
    assert row.dialog_choices == "{}"


def test_migrating_twice_changes_nothing(tmp_path):
    engine = _legacy_database(tmp_path)

    add_missing_columns(engine)
    assert add_missing_columns(engine) == []


def test_a_fresh_database_needs_no_migration(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'fresh.db'}", future=True)
    Base.metadata.create_all(engine)

    assert add_missing_columns(engine) == []

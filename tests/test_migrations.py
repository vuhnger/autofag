from __future__ import annotations

from sqlalchemy import create_engine, text

from autofag.storage.db import Base, add_missing_columns, drop_removed_columns


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


def _ledger_with_term_column(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'ledger.db'}", future=True)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE enrollment_ledger ("
                "id INTEGER PRIMARY KEY, course_code VARCHAR(32), term VARCHAR(32) NOT NULL,"
                "state VARCHAR(32), detail TEXT, run_id VARCHAR(64),"
                "created_at DATETIME, updated_at DATETIME)"
            )
        )
    return engine


def test_a_column_the_model_dropped_stops_blocking_inserts(tmp_path):
    engine = _ledger_with_term_column(tmp_path)

    dropped = drop_removed_columns(engine)

    assert "enrollment_ledger.term" in dropped
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO enrollment_ledger"
                " (course_code, state, detail, run_id, created_at, updated_at)"
                " VALUES ('IN5170', 'attempted', '', 'run-1',"
                " '2026-08-25 00:00:00', '2026-08-25 00:00:00')"
            )
        )


def test_dropping_is_a_no_op_when_the_database_already_matches(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'current.db'}", future=True)
    Base.metadata.create_all(engine)

    assert drop_removed_columns(engine) == []

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import (
    DateTime,
    Engine,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.engine.interfaces import ReflectedColumn
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from autofag.config import StorageConfig


class Base(DeclarativeBase):
    pass


class WatchEntryRow(Base):
    __tablename__ = "watch_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    course_name: Mapped[str] = mapped_column(Text, default="")
    auto_enroll: Mapped[int] = mapped_column(Integer, default=1)
    opens_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_status: Mapped[str | None] = mapped_column(String(32), default=None)
    last_status_text: Mapped[str] = mapped_column(Text, default="")
    last_status_change_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    stopped_reason: Mapped[str | None] = mapped_column(Text, default=None)
    dialog_choices: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class StatusObservationRow(Base):
    __tablename__ = "status_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_code: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32))
    status_text: Mapped[str] = mapped_column(Text)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class EnrollmentLedgerRow(Base):
    __tablename__ = "enrollment_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_code: Mapped[str] = mapped_column(String(32), index=True)
    state: Mapped[str] = mapped_column(String(32))
    detail: Mapped[str] = mapped_column(Text, default="")
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RequestBudgetRow(Base):
    __tablename__ = "request_budget"
    __table_args__ = (UniqueConstraint("hour_bucket", name="uq_request_budget_hour"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hour_bucket: Mapped[str] = mapped_column(String(20), index=True)
    request_count: Mapped[int] = mapped_column(Integer, default=0)


class NotificationDeliveryRow(Base):
    __tablename__ = "notification_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(48))
    course_code: Mapped[str] = mapped_column(String(32), default="", index=True)
    channel: Mapped[str] = mapped_column(String(32))
    dedupe_key: Mapped[str] = mapped_column(Text, index=True)
    delivered: Mapped[int] = mapped_column(Integer, default=0)
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class RunRow(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), unique=True)
    hostname: Mapped[str] = mapped_column(String(128), default="")
    pid: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


def create_database(config: StorageConfig) -> tuple[Engine, sessionmaker]:
    data_dir = config.resolved_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    _harden_directory(data_dir)

    engine = create_engine(config.database_url(), future=True)
    Base.metadata.create_all(engine)
    add_missing_columns(engine)
    drop_removed_columns(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False, future=True)


class SchemaTooOld(RuntimeError):
    pass


def add_missing_columns(engine: Engine) -> list[str]:
    inspector = inspect(engine)
    added: list[str] = []

    with engine.begin() as connection:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {column["name"] for column in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue

                fallback = _scalar_default(column)
                if fallback is None and not column.nullable:
                    raise SchemaTooOld(
                        f"{table.name}.{column.name} kan ikke legges til uten standardverdi"
                    )

                column_type = column.type.compile(engine.dialect)
                connection.execute(
                    text(f"ALTER TABLE {table.name} ADD COLUMN {column.name} {column_type}")
                )
                if fallback is not None:
                    connection.execute(
                        text(f"UPDATE {table.name} SET {column.name} = :value"),
                        {"value": fallback},
                    )
                added.append(f"{table.name}.{column.name}")

    return added


def drop_removed_columns(engine: Engine) -> list[str]:
    inspector = inspect(engine)
    dropped: list[str] = []

    with engine.begin() as connection:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            known = {column.name for column in table.columns}
            for column in inspector.get_columns(table.name):
                if column["name"] in known:
                    continue
                try:
                    connection.execute(
                        text(f"ALTER TABLE {table.name} DROP COLUMN {column['name']}")
                    )
                except OperationalError as error:
                    if _blocks_inserts(column):
                        raise SchemaTooOld(
                            f"{table.name}.{column['name']} er ikke i bruk lenger, "
                            f"men kan ikke fjernes: {error}"
                        ) from error
                    continue
                dropped.append(f"{table.name}.{column['name']}")

    return dropped


def _blocks_inserts(column: ReflectedColumn) -> bool:
    return not column.get("nullable", True) and column.get("default") is None


def _scalar_default(column) -> object | None:
    default = column.default
    if default is None:
        return None
    argument = getattr(default, "arg", None)
    return argument if not callable(argument) else None


def create_memory_database() -> tuple[Engine, sessionmaker]:
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False, future=True)


def _harden_directory(path: Path) -> None:
    try:
        path.chmod(0o700)
    except OSError:
        return

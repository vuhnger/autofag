from __future__ import annotations

import logging
from datetime import timedelta

from autofag.clock import FakeClock
from autofag.models import CourseCode, NotificationKind, RowStatus, TempoClass, WatchEntry
from autofag.notify.channels import RecordingChannel
from autofag.notify.dispatcher import NotificationDispatcher
from autofag.storage.repos import DeliveryLog, EnrollmentLedger, RunLock, WatchlistRepository
from autofag.watch.enroller import AutoEnroller
from autofag.watch.tempo import decide
from autofag.watch.watcher import Watcher
from tests.conftest import build_harness

RUN_ID = "test-run"


def build_watcher(harness, codes, auto_enroll=True, dry_run=False):
    clock = harness.clock
    logger = logging.getLogger("test")
    watchlist = WatchlistRepository(harness.session_factory, clock)
    for code in codes:
        watchlist.upsert(WatchEntry(code=CourseCode(code), name=code, auto_enroll=auto_enroll))

    channel = RecordingChannel()
    dispatcher = NotificationDispatcher(
        channels=[channel],
        delivery_log=DeliveryLog(harness.session_factory, clock),
        config=harness.config.notify,
        clock=clock,
        logger=logger,
    )
    enroller = AutoEnroller(
        session=harness.session,
        ledger=EnrollmentLedger(harness.session_factory, clock),
        dispatcher=dispatcher,
        clock=clock,
        logger=logger,
        config=harness.config.enroll,
        run_id=RUN_ID,
        dry_run=dry_run,
    )
    watcher = Watcher(
        session=harness.session,
        watchlist=watchlist,
        enroller=enroller,
        dispatcher=dispatcher,
        run_lock=RunLock(harness.session_factory, clock),
        clock=clock,
        logger=logger,
        config=harness.config,
        run_id=RUN_ID,
        term="2026H",
    )
    return watcher, channel, watchlist


def test_available_is_notified_before_the_enroll_outcome(config):
    harness = build_harness(config)
    harness.page.advance_to_takeable("IN5170")
    watcher, channel, _ = build_watcher(harness, ["IN5170"])

    watcher.run(max_cycles=1)

    kinds = [notification.kind for notification in channel.sent]
    assert kinds[0] is NotificationKind.AVAILABLE
    assert NotificationKind.ENROLL_OUTCOME in kinds
    assert kinds.index(NotificationKind.AVAILABLE) < kinds.index(NotificationKind.ENROLL_OUTCOME)
    assert harness.page.enrolled == ["IN5170"]


def test_a_course_that_is_not_takeable_is_never_enrolled(config):
    harness = build_harness(config)
    watcher, channel, _ = build_watcher(harness, ["IN5040"])

    watcher.run(max_cycles=2)

    assert harness.page.enrolled == []
    assert [n.kind for n in channel.sent] == []


def test_dry_run_notifies_but_never_confirms(config):
    harness = build_harness(config)
    harness.page.advance_to_takeable("IN5170")
    watcher, channel, _ = build_watcher(harness, ["IN5170"], dry_run=True)

    watcher.run(max_cycles=1)

    assert NotificationKind.AVAILABLE in [n.kind for n in channel.sent]
    assert harness.page.enrolled == []


def test_watch_stops_when_the_student_lacks_study_rights(config):
    harness = build_harness(config)
    watcher, _, watchlist = build_watcher(harness, ["HIS2010"])

    watcher.run(max_cycles=3)

    entry = watchlist.all_entries()[0]
    assert entry.last_status is RowStatus.NO_STUDY_RIGHT
    assert entry.is_stopped


def test_lost_session_notifies_and_does_not_pretend_to_watch(config):
    harness = build_harness(config)
    harness.page.logged_in = False
    config.session.max_reprobe_attempts = 1
    watcher, channel, _ = build_watcher(harness, ["IN5170"])

    watcher.run(max_cycles=2)

    assert NotificationKind.SESSION_EXPIRED in [n.kind for n in channel.sent]


def test_unknown_status_never_speeds_up_polling(config):
    entry = WatchEntry(code=CourseCode("IN5170"), name="x", last_status=RowStatus.UNKNOWN)
    clock = FakeClock()
    decision = decide(
        entry,
        clock.now(),
        config.watch.tempo,
        config.watch.max_duration_days,
        previous_tempo=TempoClass.COLD,
    )
    assert decision.tempo is TempoClass.COLD


def test_declared_opening_time_pre_warms_before_it_opens(config):
    clock = FakeClock()
    entry = WatchEntry(
        code=CourseCode("IN5170"),
        name="x",
        last_status=RowStatus.NOT_OPEN_YET,
        opens_at=clock.now() + timedelta(minutes=1),
    )
    decision = decide(entry, clock.now(), config.watch.tempo, config.watch.max_duration_days)
    assert decision.tempo is TempoClass.BURST


def test_deadline_passed_keeps_a_slow_watch_because_drops_happen(config):
    clock = FakeClock()
    entry = WatchEntry(code=CourseCode("IN5020"), name="x", last_status=RowStatus.DEADLINE_PASSED)
    decision = decide(entry, clock.now(), config.watch.tempo, config.watch.max_duration_days)
    assert decision.tempo is TempoClass.COLD
    assert decision.interval_seconds == config.watch.tempo.cold_seconds


def test_second_watch_process_is_refused(config):
    harness = build_harness(config)
    lock = RunLock(harness.session_factory, harness.clock)
    lock.acquire("first")
    watcher, _, _ = build_watcher(harness, ["IN5170"])
    try:
        watcher.run(max_cycles=1)
    except Exception as error:
        assert "another autofag watch is running" in str(error)
    else:
        raise AssertionError("expected the second watcher to be refused")


def test_an_opening_time_is_read_as_local_time_not_utc():
    from autofag.init_flow import _parse_timestamp

    parsed = _parse_timestamp("2026-08-25 10:00")

    assert parsed is not None
    assert parsed.utcoffset() is not None
    assert parsed.strftime("%H:%M") == "10:00"


def test_an_interrupted_enroll_is_not_reported_as_a_seat(config):
    from autofag.models import CourseCode as Code

    harness = build_harness(config)
    harness.page.advance_to_takeable("IN5170")
    harness.page.lose_race_on_confirm = True
    watcher, channel, _ = build_watcher(harness, ["IN5170"])

    watcher.run(max_cycles=1)

    outcomes = [n for n in channel.sent if n.course_code == Code("IN5170")]
    assert outcomes, "brukeren må få vite hva som skjedde"
    assert not any("Påmeldt" in n.title for n in outcomes)
    assert harness.page.enrolled == []


def test_a_running_watch_drops_courses_removed_from_the_watchlist(config):
    from autofag.models import CourseCode

    harness = build_harness(config)
    watcher, _, watchlist = build_watcher(harness, ["IN5040", "IN5170"])

    watcher.run(max_cycles=1)
    watchlist.remove(CourseCode("IN5040"))
    watchlist.remove(CourseCode("IN5170"))
    watcher.run(max_cycles=3)

    assert harness.page.actions.count("search") == 1


def test_a_running_watch_picks_up_a_course_added_afterwards(config):
    from autofag.models import CourseCode, WatchEntry

    harness = build_harness(config)
    watcher, _, watchlist = build_watcher(harness, ["IN5040"])

    watcher.run(max_cycles=1)
    watchlist.upsert(WatchEntry(code=CourseCode("IN5170"), name="Models of concurrency"))
    watcher.run(max_cycles=2)

    observed = {
        entry.code.value for entry in watchlist.all_entries() if entry.last_status is not None
    }
    assert observed == {"IN5040", "IN5170"}

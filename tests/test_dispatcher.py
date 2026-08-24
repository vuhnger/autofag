from __future__ import annotations

import logging

from autofag.clock import FakeClock
from autofag.config import AppConfig
from autofag.models import CourseCode, Notification, NotificationKind, Severity
from autofag.notify.channels import RecordingChannel
from autofag.notify.dispatcher import NotificationDispatcher
from autofag.storage.db import create_memory_database
from autofag.storage.repos import DeliveryLog


def build(channels, fallback=None, clock=None, notify_config=None):
    clock = clock or FakeClock()
    _, session_factory = create_memory_database()
    return NotificationDispatcher(
        channels=channels,
        delivery_log=DeliveryLog(session_factory, clock),
        config=notify_config or AppConfig().notify,
        clock=clock,
        logger=logging.getLogger("test"),
        fallback=fallback,
    )


def notification(kind=NotificationKind.STATUS_VOCABULARY_MISS) -> Notification:
    return Notification(kind=kind, severity=Severity.INFO, title="t", body="b")


def available(code: str) -> Notification:
    return Notification(
        kind=NotificationKind.AVAILABLE,
        severity=Severity.CRITICAL,
        title=f"Ledig plass: {code}",
        body="b",
        course_code=CourseCode(code),
    )


def test_a_dead_channel_never_blocks_the_healthy_ones():
    dead = RecordingChannel("dead", healthy=False)
    alive = RecordingChannel("alive")
    dispatcher = build([dead, alive])

    results = dispatcher.dispatch(notification())

    assert {result.channel: result.delivered for result in results} == {
        "dead": False,
        "alive": True,
    }


def test_repeated_low_value_notifications_are_deduped():
    channel = RecordingChannel()
    dispatcher = build([channel])

    dispatcher.dispatch(notification())
    dispatcher.dispatch(notification())

    assert len(channel.sent) == 1


def test_one_notification_per_course_per_run_by_default():
    channel = RecordingChannel()
    clock = FakeClock()
    dispatcher = build([channel], clock=clock)

    for _ in range(5):
        dispatcher.dispatch(available("IN5170"))
        clock.advance(600)

    assert len(channel.sent) == 1


def test_the_cap_is_per_course_not_global():
    channel = RecordingChannel()
    dispatcher = build([channel])

    dispatcher.dispatch(available("IN5170"))
    dispatcher.dispatch(available("IN5020"))

    assert [n.course_code.value for n in channel.sent] == ["IN5170", "IN5020"]


def test_the_cap_can_be_raised():
    channel = RecordingChannel()
    clock = FakeClock()
    config = AppConfig().notify
    config.max_per_course_per_run = 3
    dispatcher = build([channel], clock=clock, notify_config=config)

    for _ in range(5):
        dispatcher.dispatch(available("IN5170"))
        clock.advance(600)

    assert len(channel.sent) == 3


def test_the_enrolment_outcome_always_gets_through():
    channel = RecordingChannel()
    dispatcher = build([channel])

    dispatcher.dispatch(available("IN5170"))
    dispatcher.dispatch(
        Notification(
            kind=NotificationKind.ENROLL_OUTCOME,
            severity=Severity.IMPORTANT,
            title="Påmeldt IN5170",
            body="b",
            course_code=CourseCode("IN5170"),
        )
    )

    assert [n.kind for n in channel.sent] == [
        NotificationKind.AVAILABLE,
        NotificationKind.ENROLL_OUTCOME,
    ]


def test_total_blackout_escalates_to_the_fallback():
    dead = RecordingChannel("dead", healthy=False)
    fallback = RecordingChannel("fallback")
    dispatcher = build([dead], fallback=fallback)

    dispatcher.dispatch(notification(NotificationKind.AVAILABLE))

    assert len(fallback.sent) == 1

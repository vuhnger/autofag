from __future__ import annotations

import logging

from autofag.clock import FakeClock
from autofag.config import AppConfig
from autofag.models import Notification, NotificationKind, Severity
from autofag.notify.channels import RecordingChannel
from autofag.notify.dispatcher import NotificationDispatcher
from autofag.storage.db import create_memory_database
from autofag.storage.repos import DeliveryLog


def build(channels, fallback=None):
    clock = FakeClock()
    _, session_factory = create_memory_database()
    return NotificationDispatcher(
        channels=channels,
        delivery_log=DeliveryLog(session_factory, clock),
        config=AppConfig().notify,
        clock=clock,
        logger=logging.getLogger("test"),
        fallback=fallback,
    )


def notification(kind=NotificationKind.STATUS_VOCABULARY_MISS) -> Notification:
    return Notification(kind=kind, severity=Severity.INFO, title="t", body="b")


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


def test_a_free_spot_is_never_deduped_away():
    channel = RecordingChannel()
    dispatcher = build([channel])

    dispatcher.dispatch(notification(NotificationKind.AVAILABLE))
    dispatcher.dispatch(notification(NotificationKind.AVAILABLE))

    assert len(channel.sent) == 2


def test_total_blackout_escalates_to_the_fallback():
    dead = RecordingChannel("dead", healthy=False)
    fallback = RecordingChannel("fallback")
    dispatcher = build([dead], fallback=fallback)

    dispatcher.dispatch(notification(NotificationKind.AVAILABLE))

    assert len(fallback.sent) == 1

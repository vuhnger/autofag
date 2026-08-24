from __future__ import annotations

import os

from autofag.clock import FakeClock, SystemClock
from autofag.daemon import RunningWatch, process_is_alive, running_watch, stop_process
from autofag.storage.db import create_memory_database
from autofag.storage.repos import RunLock


def _run_lock():
    clock = SystemClock()
    _, session_factory = create_memory_database()
    return RunLock(session_factory, clock)


def test_nothing_is_running_before_a_watch_starts():
    assert running_watch(_run_lock()) is None


def test_a_started_watch_is_reported_with_its_pid_and_host():
    lock = _run_lock()
    lock.acquire("run-1")

    active = running_watch(lock)

    assert isinstance(active, RunningWatch)
    assert active.pid == os.getpid()
    assert active.hostname


def test_a_released_watch_is_no_longer_reported():
    lock = _run_lock()
    lock.acquire("run-1")
    lock.release("run-1")

    assert running_watch(lock) is None


def test_releasing_by_pid_clears_the_run():
    lock = _run_lock()
    lock.acquire("run-1")

    lock.release_pid(os.getpid())

    assert running_watch(lock) is None


def test_stopping_a_process_that_is_already_gone_is_success():
    assert stop_process(999999, FakeClock()) is True


def test_a_dead_pid_is_not_alive():
    assert process_is_alive(999999) is False
    assert process_is_alive(os.getpid()) is True

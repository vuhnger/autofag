from __future__ import annotations

import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from autofag.clock import Clock
from autofag.storage.repos import RunLock

WATCH_LOG_FILENAME = "watch.log"


class DaemonError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RunningWatch:
    pid: int
    hostname: str


@dataclass(frozen=True, slots=True)
class StartedWatch:
    pid: int
    log_path: Path


def running_watch(run_lock: RunLock) -> RunningWatch | None:
    row = run_lock.active_run()
    if row is None:
        return None
    return RunningWatch(pid=row.pid, hostname=row.hostname)


def start_detached(arguments: list[str], data_dir: Path) -> StartedWatch:
    data_dir.mkdir(parents=True, exist_ok=True)
    log_path = data_dir / WATCH_LOG_FILENAME

    with log_path.open("ab") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "autofag.cli", *arguments],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            cwd=str(data_dir),
        )

    return StartedWatch(pid=process.pid, log_path=log_path)


def stop_process(pid: int, clock: Clock, timeout_seconds: float = 30.0) -> bool:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return True
    except PermissionError as error:
        raise DaemonError(f"mangler rettigheter til å stoppe pid {pid}") from error

    deadline = clock.monotonic() + timeout_seconds
    while clock.monotonic() < deadline:
        if not process_is_alive(pid):
            return True
        clock.sleep_until(clock.monotonic() + 0.5)

    return not process_is_alive(pid)


def process_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True

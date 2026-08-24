from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from autofag.config import TempoConfig
from autofag.models import NEEDS_HUMAN_STATUSES, RowStatus, TempoClass, WatchEntry

STOP_ENROLLED = "du har plass på undervisningen"
STOP_NEEDS_HUMAN = "krever at du gjør noe selv"
STOP_EXPIRED = "watchen din er utløpt"
STOP_MAX_DURATION = "maksimal overvåkingstid er nådd"


@dataclass(frozen=True, slots=True)
class TempoDecision:
    tempo: TempoClass
    interval_seconds: float | None
    reason: str

    @property
    def is_stopped(self) -> bool:
        return self.tempo is TempoClass.STOPPED


def decide(
    entry: WatchEntry,
    now: datetime,
    config: TempoConfig,
    max_duration_days: int,
    previous_tempo: TempoClass | None = None,
    watch_started_at: datetime | None = None,
) -> TempoDecision:
    if entry.stopped_reason:
        return _stopped(entry.stopped_reason)
    if entry.last_status is RowStatus.ENROLLED:
        return _stopped(STOP_ENROLLED)
    if entry.last_status in NEEDS_HUMAN_STATUSES:
        return _stopped(STOP_NEEDS_HUMAN)
    if entry.expires_at is not None and now >= entry.expires_at:
        return _stopped(STOP_EXPIRED)
    if watch_started_at is not None and now - watch_started_at >= timedelta(days=max_duration_days):
        return _stopped(STOP_MAX_DURATION)

    if entry.last_status is RowStatus.UNKNOWN:
        held = (
            previous_tempo if previous_tempo not in (None, TempoClass.STOPPED) else TempoClass.WARM
        )
        return TempoDecision(held, _interval_for(held, config), "ukjent status, holder tempoet")

    if _inside_burst_window(entry, now, config):
        return TempoDecision(TempoClass.BURST, config.burst_seconds, "åpningsvindu")

    if entry.last_status is RowStatus.TAKEABLE:
        return TempoDecision(TempoClass.HOT, config.hot_seconds, "plass er ledig nå")

    if _changed_recently(entry, now, config):
        return TempoDecision(TempoClass.HOT, config.hot_seconds, "statusen endret seg nylig")

    if entry.last_status is RowStatus.DEADLINE_PASSED:
        return TempoDecision(TempoClass.COLD, config.cold_seconds, "fristen har gått ut")

    return TempoDecision(TempoClass.WARM, config.warm_seconds, "stabil status")


def _stopped(reason: str) -> TempoDecision:
    return TempoDecision(TempoClass.STOPPED, None, reason)


def _interval_for(tempo: TempoClass, config: TempoConfig) -> float:
    return {
        TempoClass.BURST: config.burst_seconds,
        TempoClass.HOT: config.hot_seconds,
        TempoClass.WARM: config.warm_seconds,
        TempoClass.COLD: config.cold_seconds,
    }[tempo]


def _inside_burst_window(entry: WatchEntry, now: datetime, config: TempoConfig) -> bool:
    if entry.opens_at is None:
        return False
    starts = entry.opens_at - timedelta(minutes=config.burst_lead_minutes)
    ends = entry.opens_at + timedelta(minutes=config.burst_max_minutes)
    return starts <= now <= ends


def _changed_recently(entry: WatchEntry, now: datetime, config: TempoConfig) -> bool:
    if entry.last_status_change_at is None:
        return False
    return now - entry.last_status_change_at <= timedelta(minutes=config.hot_window_minutes)

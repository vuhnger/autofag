from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

COURSE_CODE_PATTERN = re.compile(r"^[A-ZÆØÅ0-9][A-ZÆØÅ0-9\-]{1,19}$")


class InvalidCourseCode(ValueError):
    pass


@dataclass(frozen=True, slots=True, order=True)
class CourseCode:
    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().upper()
        if not COURSE_CODE_PATTERN.match(normalized):
            raise InvalidCourseCode(f"not a course code: {self.value!r}")
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


class RowStatus(Enum):
    TAKEABLE = "takeable"
    DEADLINE_PASSED = "deadline_passed"
    NOT_OPEN_YET = "not_open_yet"
    NO_STUDY_RIGHT = "no_study_right"
    PREREQUISITES_MISSING = "prerequisites_missing"
    ENROLLED = "enrolled"
    UNKNOWN = "unknown"


TERMINAL_STATUSES = frozenset(
    {RowStatus.DEADLINE_PASSED, RowStatus.NO_STUDY_RIGHT, RowStatus.PREREQUISITES_MISSING}
)


@dataclass(frozen=True, slots=True)
class CourseRow:
    code: CourseCode
    name: str
    credits: str
    status: RowStatus
    status_text: str
    select_button_id: str | None
    term: str | None = None

    @property
    def is_takeable(self) -> bool:
        return self.status is RowStatus.TAKEABLE and self.select_button_id is not None


@dataclass(frozen=True, slots=True)
class SearchCriteria:
    course_code: str = ""
    course_name: str = ""
    subject: str = ""
    faculty: str = ""

    def is_empty(self) -> bool:
        return not any((self.course_code, self.course_name, self.subject, self.faculty))


@dataclass(frozen=True, slots=True)
class SearchResult:
    rows: tuple[CourseRow, ...]
    total_hits: int
    page_index: int
    has_next_page: bool

    def single_row_for(self, code: CourseCode) -> CourseRow | None:
        matching = [row for row in self.rows if row.code == code]
        if len(matching) != 1:
            return None
        return matching[0]


class TempoClass(Enum):
    BURST = "burst"
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"
    STOPPED = "stopped"


@dataclass(slots=True)
class WatchEntry:
    code: CourseCode
    name: str
    auto_enroll: bool = True
    opens_at: datetime | None = None
    expires_at: datetime | None = None
    last_status: RowStatus | None = None
    last_status_text: str = ""
    last_status_change_at: datetime | None = None
    stopped_reason: str | None = None

    @property
    def is_stopped(self) -> bool:
        return self.stopped_reason is not None


class EnrollOutcome(Enum):
    CONFIRMED = "confirmed"
    WAITLISTED = "waitlisted"
    FULL = "full"
    REJECTED = "rejected"
    UNVERIFIED = "unverified"
    ABORTED = "aborted"


@dataclass(frozen=True, slots=True)
class EnrollResult:
    code: CourseCode
    outcome: EnrollOutcome
    detail: str


class Severity(Enum):
    INFO = "info"
    IMPORTANT = "important"
    CRITICAL = "critical"


class NotificationKind(Enum):
    TEST = "test"
    AVAILABLE = "available"
    ENROLL_OUTCOME = "enroll_outcome"
    SESSION_EXPIRED = "session_expired"
    STATUS_VOCABULARY_MISS = "status_vocabulary_miss"
    BUDGET_EXHAUSTED = "budget_exhausted"
    NEEDS_MANUAL_CHECK = "needs_manual_check"


@dataclass(frozen=True, slots=True)
class Notification:
    kind: NotificationKind
    severity: Severity
    title: str
    body: str
    course_code: CourseCode | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)

    def dedupe_key(self) -> str:
        return f"{self.kind.value}:{self.course_code or '-'}:{self.title}"


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    channel: str
    delivered: bool
    detail: str = ""

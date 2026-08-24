from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from autofag.studentweb.components import ComponentMap


class ViewExpired(RuntimeError):
    pass


class SessionUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ViewAnchor:
    view_state: str
    components: ComponentMap
    anchored_at: datetime
    postback_count: int = 0

    def with_view_state(self, view_state: str | None) -> ViewAnchor:
        if view_state is None:
            return replace(self, postback_count=self.postback_count + 1)
        return replace(
            self, view_state=view_state, postback_count=self.postback_count + 1
        )

    def is_stale(self, now: datetime, max_postbacks: int, max_age_minutes: int) -> bool:
        if self.postback_count >= max_postbacks:
            return True
        age_seconds = (now - self.anchored_at).total_seconds()
        return age_seconds >= max_age_minutes * 60

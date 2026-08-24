from __future__ import annotations

from dataclasses import dataclass

from autofag.config import StatusVocabularyConfig
from autofag.models import RowStatus


@dataclass(frozen=True, slots=True)
class Classification:
    status: RowStatus
    matched_phrase: str | None

    @property
    def is_vocabulary_miss(self) -> bool:
        return self.status is RowStatus.UNKNOWN


class StatusClassifier:
    def __init__(self, config: StatusVocabularyConfig) -> None:
        self._ordered_phrases = [
            (status, phrase.casefold())
            for status, phrases in config.phrases.items()
            for phrase in phrases
        ]

    def classify(self, teaching_status_text: str) -> Classification:
        haystack = _normalize(teaching_status_text)
        if not haystack:
            return Classification(RowStatus.UNKNOWN, None)

        for status, phrase in self._ordered_phrases:
            if phrase in haystack:
                return Classification(status, phrase)

        return Classification(RowStatus.UNKNOWN, None)


def _normalize(text: str) -> str:
    return " ".join(text.split()).casefold()

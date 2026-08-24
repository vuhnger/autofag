from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator

from autofag.models import RowStatus


def default_config_path() -> Path:
    root = os.environ.get("XDG_CONFIG_HOME")
    base = Path(root) if root else Path.home() / ".config"
    return base / "autofag" / "config.yaml"


def default_data_dir() -> Path:
    root = os.environ.get("XDG_DATA_HOME")
    base = Path(root) if root else Path.home() / ".local" / "share"
    return base / "autofag"


class StudentwebConfig(BaseModel):
    base_url: str = "https://studentweb.uio.no/studentweb/"
    courses_path: str = "aktiveemner.jsf"
    transport: Literal["browser", "fake"] = "browser"
    fixtures_dir: Path | None = None
    request_timeout_seconds: float = 20.0
    connect_timeout_seconds: float = 10.0
    user_agent: str = "autofag (+https://github.com/vuhnger/autofag)"

    @field_validator("base_url")
    @classmethod
    def must_end_with_slash(cls, value: str) -> str:
        return value if value.endswith("/") else value + "/"

    @property
    def courses_url(self) -> str:
        return self.base_url + self.courses_path


class SelectorConfig(BaseModel):
    course_code_input_suffix: str = ":emnekode"
    course_name_input_suffix: str = ":emnenavn"
    subject_select_suffix: str = ":emnefag"
    faculty_select_suffix: str = ":emnefakultet"
    result_table_suffix: str = ":sokResultatDataTable"
    select_button_marker: str = "frittEmneVelgKnapp"
    search_update_marker: str = "frittSokResultat"
    hit_count_marker: str = "frittSokMsgTreff"
    confirm_form_marker: str = "leggTilEmneForm"
    teaching_section_labels: tuple[str, ...] = ("Undervisning", "Teaching")
    exam_section_labels: tuple[str, ...] = ("Eksamen", "Examination", "Eksamen/vurdering")
    confirm_forward_labels: tuple[str, ...] = ("neste", "next", "fortsett", "continue")
    confirm_final_labels: tuple[str, ...] = (
        "fullfør",
        "fullfor",
        "bekreft",
        "lagre",
        "meld deg",
        "meld meg",
        "finish",
    )
    confirm_negative_labels: tuple[str, ...] = (
        "avbryt",
        "nei",
        "lukk",
        "cancel",
        "ønsker ikke",
        "onsker ikke",
        "tilbake",
        "forrige",
        "trekk",
    )
    max_dialog_steps: int = 6
    header_label_class: str = "header"
    detail_toggle_class: str = "skalKunneTogglesContainer"
    paginator_next_class: str = "ui-paginator-next"
    view_state_marker: str = "javax.faces.ViewState"
    release_pattern: str = r"Studentweb\s+([0-9]+-[0-9.]+(?:\s+[0-9:]+)?)"
    login_markers: tuple[str, ...] = ("login.jsf", "velgInstitusjon.jsf")
    view_expired_markers: tuple[str, ...] = ("ViewExpiredException", "viewExpired")


class StatusVocabularyConfig(BaseModel):
    phrases: dict[RowStatus, tuple[str, ...]] = Field(
        default_factory=lambda: {
            RowStatus.TAKEABLE: ("du kan melde deg til undervisning",),
            RowStatus.DEADLINE_PASSED: (
                "fristen for å søke plass på undervisningen gikk ut",
                "fristen for å melde seg til undervisning gikk ut",
            ),
            RowStatus.NOT_OPEN_YET: ("du kan ikke velge undervisning dette semestret nå",),
            RowStatus.NO_STUDY_RIGHT: ("du har ikke studierett til emnet",),
            RowStatus.PREREQUISITES_MISSING: (
                "krav om forkunnskaper",
                "krav om forkunnskap",
            ),
            RowStatus.ENROLLED: (
                "du har plass på undervisningen",
                "du er meldt til undervisning",
                "du har allerede meldt deg til undervisning",
            ),
        }
    )


class EnrollVocabularyConfig(BaseModel):
    confirmed: tuple[str, ...] = (
        "du har plass på undervisningen",
        "du er meldt til undervisning",
        "undervisningsmelding er registrert",
        "meldingen er registrert",
    )
    waitlisted: tuple[str, ...] = ("venteliste",)
    full: tuple[str, ...] = (
        "emnet er fullt",
        "det er ikke flere ledige plasser",
        "ingen ledige plasser",
    )
    rejected: tuple[str, ...] = (
        "du har ikke studierett",
        "krav om forkunnskaper",
        "fristen",
    )


class BudgetConfig(BaseModel):
    requests_per_hour: int = 500
    min_seconds_between_requests: float = 1.0
    jitter_fraction: float = 0.2
    max_concurrent_requests: int = 1


class RetryConfig(BaseModel):
    max_attempts: int = 4
    initial_backoff_seconds: float = 2.0
    backoff_multiplier: float = 3.0
    max_backoff_seconds: float = 120.0
    retry_on_status: tuple[int, ...] = (429, 500, 502, 503, 504)


class SessionConfig(BaseModel):
    reanchor_after_postbacks: int = 200
    reanchor_after_minutes: int = 60
    keepalive_after_idle_minutes: int = 10
    reprobe_minutes: int = 5
    max_reprobe_attempts: int = 24


class TempoConfig(BaseModel):
    burst_seconds: float = 5.0
    hot_seconds: float = 30.0
    warm_seconds: float = 300.0
    cold_seconds: float = 1800.0
    burst_lead_minutes: int = 2
    burst_max_minutes: int = 20
    hot_window_minutes: int = 15


class WatchConfig(BaseModel):
    max_duration_days: int = 120
    tempo: TempoConfig = Field(default_factory=TempoConfig)

    def run_stale_after_seconds(self) -> float:
        return max(300.0, self.tempo.cold_seconds * 2 + 60.0)


class EnrollConfig(BaseModel):
    enabled: bool = True
    max_sequence_attempts: int = 2
    max_unverified_before_stop: int = 2


class AuthConfig(BaseModel):
    profile_dir: Path | None = None
    login_timeout_seconds: float = 600.0
    headless: bool = False
    signed_in_selector: str = 'a[href*="aktiveemner.jsf"]'


class NtfyConfig(BaseModel):
    enabled: bool = False
    server_url: str = "https://ntfy.sh"


class EmailConfig(BaseModel):
    enabled: bool = False
    host: str = ""
    port: int = 587
    use_starttls: bool = True
    username: str = ""
    sender: str = ""
    recipients: tuple[str, ...] = ()


class SmsConfig(BaseModel):
    enabled: bool = False
    api_base_url: str = "https://api.twilio.com"
    from_number: str = ""
    to_numbers: tuple[str, ...] = ()


class MacosConfig(BaseModel):
    enabled: bool = False
    sound: str = "Glass"


class NotifyConfig(BaseModel):
    ntfy: NtfyConfig = Field(default_factory=NtfyConfig)
    email: EmailConfig = Field(default_factory=EmailConfig)
    sms: SmsConfig = Field(default_factory=SmsConfig)
    macos: MacosConfig = Field(default_factory=MacosConfig)
    channel_timeout_seconds: float = 15.0
    dedupe_window_seconds: float = 300.0
    max_per_course_per_run: int = 1
    use_emoji: bool = True
    emoji: dict[str, str] = Field(
        default_factory=lambda: {
            "available": "🚨",
            "enroll_outcome": "✅",
            "needs_manual_check": "⚠️",
            "session_expired": "🔐",
            "budget_exhausted": "⏳",
            "status_vocabulary_miss": "❓",
            "test": "🔔",
        }
    )
    always_deliver_kinds: tuple[str, ...] = (
        "test",
        "enroll_outcome",
        "needs_manual_check",
        "session_expired",
        "budget_exhausted",
    )
    retry: RetryConfig = Field(default_factory=RetryConfig)


class StorageConfig(BaseModel):
    data_dir: Path | None = None
    database_filename: str = "autofag.db"

    def resolved_data_dir(self) -> Path:
        return self.data_dir or default_data_dir()

    def database_url(self) -> str:
        return f"sqlite:///{self.resolved_data_dir() / self.database_filename}"


class AppConfig(BaseModel):
    studentweb: StudentwebConfig = Field(default_factory=StudentwebConfig)
    selectors: SelectorConfig = Field(default_factory=SelectorConfig)
    status_vocabulary: StatusVocabularyConfig = Field(default_factory=StatusVocabularyConfig)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    retry: RetryConfig = Field(default_factory=RetryConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)
    watch: WatchConfig = Field(default_factory=WatchConfig)
    enroll: EnrollConfig = Field(default_factory=EnrollConfig)
    enroll_vocabulary: EnrollVocabularyConfig = Field(default_factory=EnrollVocabularyConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    notify: NotifyConfig = Field(default_factory=NotifyConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    secret_service_name: str = "autofag"

    def browser_profile_dir(self) -> Path:
        return self.auth.profile_dir or self.storage.resolved_data_dir() / "browser-profile"


def load_config(path: Path | None = None) -> AppConfig:
    resolved = path or default_config_path()
    if not resolved.exists():
        return AppConfig()

    raw: Any = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    if raw is None:
        return AppConfig()
    if not isinstance(raw, dict):
        raise ValueError(f"config must be a mapping: {resolved}")
    return AppConfig.model_validate(raw)


def save_config(config: AppConfig, path: Path | None = None) -> Path:
    resolved = path or default_config_path()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    payload = config.model_dump(mode="json", exclude_defaults=True)
    resolved.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), "utf-8")
    return resolved

from __future__ import annotations

import logging
from dataclasses import dataclass
from random import Random

import pytest

from autofag.auth.cookies import StaticCookies
from autofag.clock import FakeClock
from autofag.config import AppConfig
from autofag.storage.db import create_memory_database
from autofag.storage.repos import BudgetStore
from autofag.studentweb.components import ComponentMapScraper
from autofag.studentweb.session import StudentwebSession
from autofag.studentweb.status import StatusClassifier
from autofag.transport.fake import FakeStudentwebServer, default_courses
from autofag.transport.gate import StudentwebGate
from autofag.transport.retry import RetryPolicy


@dataclass(slots=True)
class Harness:
    server: FakeStudentwebServer
    session: StudentwebSession
    clock: FakeClock
    config: AppConfig
    session_factory: object


@pytest.fixture
def config() -> AppConfig:
    config = AppConfig()
    config.budget.min_seconds_between_requests = 0.0
    config.budget.jitter_fraction = 0.0
    config.retry.initial_backoff_seconds = 0.0
    return config


@pytest.fixture
def harness(config: AppConfig) -> Harness:
    return build_harness(config)


def build_harness(config: AppConfig, **server_kwargs) -> Harness:
    clock = FakeClock()
    _, session_factory = create_memory_database()
    server = FakeStudentwebServer(
        clock=clock, courses=default_courses(), **server_kwargs
    )
    gate = StudentwebGate(
        transport=server,
        budget_store=BudgetStore(session_factory, clock),
        retry=RetryPolicy(config.retry, Random(0)),
        clock=clock,
        logger=logging.getLogger("test"),
        config=config.studentweb,
        budget_config=config.budget,
        random=Random(0),
    )
    session = StudentwebSession(
        gate=gate,
        scraper=ComponentMapScraper(config.selectors),
        classifier=StatusClassifier(config.status_vocabulary),
        cookies=StaticCookies({"JSESSIONID": "test"}),
        clock=clock,
        logger=logging.getLogger("test"),
        config=config,
    )
    return Harness(
        server=server,
        session=session,
        clock=clock,
        config=config,
        session_factory=session_factory,
    )

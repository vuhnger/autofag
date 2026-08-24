from __future__ import annotations

import logging

from autofag.init_flow import InitWizard
from autofag.notify.channels import RecordingChannel
from autofag.notify.dispatcher import NotificationDispatcher
from autofag.presentation import RecordingPresenter
from autofag.prompts import ScriptedPrompter
from autofag.storage.repos import DeliveryLog, WatchlistRepository
from autofag.storage.secrets import InMemorySecretStore
from tests.conftest import build_harness


def build_wizard(harness, answers, dry_run=False):
    channel = RecordingChannel("macos")
    presenter = RecordingPresenter()

    def dispatcher_factory(names):
        return NotificationDispatcher(
            channels=[channel],
            delivery_log=DeliveryLog(harness.session_factory, harness.clock),
            config=harness.config.notify,
            clock=harness.clock,
            logger=logging.getLogger("test"),
        )

    wizard = InitWizard(
        session=harness.session,
        prompter=ScriptedPrompter(answers),
        presenter=presenter,
        watchlist=WatchlistRepository(harness.session_factory, harness.clock),
        secrets=InMemorySecretStore(),
        config=harness.config,
        clock=harness.clock,
        logger=logging.getLogger("test"),
        dispatcher_factory=dispatcher_factory,
        dry_run=dry_run,
    )
    return wizard, channel, presenter


def test_wizard_searches_studentweb_and_persists_the_selection(config):
    harness = build_harness(config)
    answers = ["IN5170", ["IN5170"], False, "", ["macos"], True, True]
    wizard, channel, presenter = build_wizard(harness, answers)

    outcome = wizard.run()

    assert [entry.code.value for entry in outcome.entries] == ["IN5170"]
    assert outcome.channels == ["macos"]
    assert outcome.started is True
    assert channel.sent, "the wizard must test-fire every configured channel"


def test_wizard_finds_courses_by_name_across_faculties(config):
    harness = build_harness(config)
    answers = ["samers", ["HIS2010"], False, "", ["macos"], True, True]
    wizard, _, presenter = build_wizard(harness, answers)

    outcome = wizard.run()

    assert [entry.code.value for entry in outcome.entries] == ["HIS2010"]


def test_wizard_marks_a_takeable_course_in_the_table(config):
    harness = build_harness(config)
    harness.page.advance_to_takeable("IN5170")
    answers = ["IN5170", ["IN5170"], False, "", ["macos"], True, True]
    wizard, _, presenter = build_wizard(harness, answers)

    wizard.run()

    rendered = [cell for _, rows in presenter.tables for row in rows for cell in row]
    assert "LEDIG NÅ" in rendered


def test_dry_run_turns_auto_enroll_off_for_every_entry(config):
    harness = build_harness(config)
    answers = ["IN5170", ["IN5170"], False, "", ["macos"], True, True]
    wizard, _, _ = build_wizard(harness, answers, dry_run=True)

    outcome = wizard.run()

    assert all(entry.auto_enroll is False for entry in outcome.entries)

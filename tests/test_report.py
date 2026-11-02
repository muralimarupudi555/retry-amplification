"""The verdict layer, including its refusal to publish a run it does not believe."""

from __future__ import annotations

from dataclasses import replace

import pytest

from retry_amplification.config import ScenarioConfig
from retry_amplification.harness import run_scenario
from retry_amplification.report import Report, build_report


def test_a_naive_lossy_run_is_flagged(dsn):
    report = build_report(ScenarioConfig(messages=2000, ack_loss=0.4, seed=2, dsn=dsn))
    assert report.silent_double_apply
    assert report.measurement_valid


def test_an_idempotent_run_is_not(dsn):
    report = build_report(ScenarioConfig(handler="idempotent", messages=2000,
                                         ack_loss=0.4, seed=2, dsn=dsn))
    assert not report.silent_double_apply
    assert report.result.exactly_once


def test_predictions_are_met(dsn):
    report = build_report(ScenarioConfig(messages=4000, ack_loss=0.3, seed=4, dsn=dsn))
    assert report.amplification_agrees
    assert report.corruption_agrees


def test_a_tampered_result_fails_the_apparatus_check(dsn):
    """The guard has to actually fire, so here is a run that lies about its attempts."""
    result = run_scenario(ScenarioConfig(messages=500, ack_loss=0.5, seed=6, dsn=dsn))
    result.stats.attempts = result.config.messages  # claim no retries happened at all
    assert not Report(result=result).measurement_valid


def test_a_budgeted_run_is_exempt_from_the_attempt_check(dsn):
    """It stops early on purpose, so missing the series is the expected behaviour."""
    config = ScenarioConfig(messages=500, ack_loss=0.6, retry_policy="budgeted",
                            retry_budget=20, seed=6, dsn=dsn)
    report = build_report(config)
    assert not report.amplification_agrees
    assert report.measurement_valid


def test_ledger_cost_share_is_zero_without_a_ledger(dsn):
    report = build_report(ScenarioConfig(messages=500, ack_loss=0.3, seed=1, dsn=dsn))
    assert report.ledger_cost_share == 0.0


def test_report_dict_carries_both_measurements_and_both_predictions(dsn):
    payload = build_report(ScenarioConfig(messages=500, ack_loss=0.3,
                                          seed=1, dsn=dsn)).as_dict()
    for key in ("amplification", "corruption", "predicted_amplification",
                "predicted_corruption", "final_balance", "overapplied"):
        assert key in payload


def test_unapplied_is_detected_when_the_handler_keeps_failing(dsn):
    config = ScenarioConfig(messages=1000, ack_loss=0.0, handler_failure=0.6,
                            max_attempts=2, seed=9, dsn=dsn)
    report = build_report(config)
    assert report.unapplied
    assert report.result.final_balance < config.messages


def test_predicted_corruption_for_an_idempotent_run_is_one(dsn):
    config = ScenarioConfig(handler="idempotent", messages=500, ack_loss=0.5, dsn=dsn)
    assert build_report(config).predicted_corruption == pytest.approx(1.0)


def test_replacing_the_config_does_not_change_a_frozen_result(dsn):
    result = run_scenario(ScenarioConfig(messages=500, ack_loss=0.2, seed=1, dsn=dsn))
    other = replace(result, final_balance=result.final_balance + 10)
    assert other.final_balance == result.final_balance + 10
    assert result.final_balance != other.final_balance

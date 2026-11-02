"""Whole scenarios, where the two measurements have to agree with each other."""

from __future__ import annotations

import pytest

from retry_amplification import theory
from retry_amplification.config import ScenarioConfig
from retry_amplification.harness import median_corruption, repeat_scenario, run_scenario


def test_a_lossless_run_applies_everything_exactly_once(dsn):
    result = run_scenario(ScenarioConfig(messages=500, ack_loss=0.0, dsn=dsn))
    assert result.final_balance == 500
    assert result.exactly_once
    assert result.overapplied == 0


def test_a_lossy_naive_run_overapplies(small):
    result = run_scenario(small)
    assert result.overapplied > 0
    assert not result.exactly_once


def test_a_lossy_idempotent_run_does_not(small):
    config = ScenarioConfig(**{**small.as_dict(), "handler": "idempotent"}, dsn=small.dsn)
    result = run_scenario(config)
    assert result.final_balance == config.messages
    assert result.exactly_once


def test_the_ledger_skips_exactly_what_the_naive_handler_would_have_overapplied(dsn):
    """Two runs of the same delivery, counted from opposite ends.

    The broker is seeded identically, so both handlers see the same sequence of
    redeliveries. What the naive handler adds in excess, the ledger declines to add.
    """
    fields = dict(messages=500, ack_loss=0.4, seed=99, dsn=dsn)
    naive = run_scenario(ScenarioConfig(handler="naive", **fields))
    idempotent = run_scenario(ScenarioConfig(handler="idempotent", **fields))
    assert idempotent.skipped == naive.overapplied


def test_idempotency_does_not_reduce_amplification(dsn):
    """The ledger fixes the data and does nothing at all about the load."""
    fields = dict(messages=500, ack_loss=0.4, seed=99, dsn=dsn)
    naive = run_scenario(ScenarioConfig(handler="naive", **fields))
    idempotent = run_scenario(ScenarioConfig(handler="idempotent", **fields))
    assert idempotent.amplification == pytest.approx(naive.amplification)


def test_corruption_is_read_from_the_balance_not_from_the_broker(small):
    """These are independent instruments and the test treats them as such."""
    result = run_scenario(small)
    assert result.corruption == pytest.approx(result.final_balance / small.messages)


def test_measured_amplification_matches_the_series(dsn):
    config = ScenarioConfig(messages=4000, ack_loss=0.5, seed=5, dsn=dsn)
    result = run_scenario(config)
    assert theory.agrees(result.amplification, theory.predicted_amplification(config))


def test_measured_corruption_matches_the_series(dsn):
    config = ScenarioConfig(messages=4000, ack_loss=0.5, seed=5, dsn=dsn)
    result = run_scenario(config)
    assert theory.agrees(result.corruption, theory.predicted_corruption(config))


def test_a_run_is_reproducible_from_its_seed(dsn):
    config = ScenarioConfig(messages=500, ack_loss=0.4, seed=1234, dsn=dsn)
    assert run_scenario(config).final_balance == run_scenario(config).final_balance


def test_repeats_use_different_seeds(dsn):
    config = ScenarioConfig(messages=500, ack_loss=0.4, seed=1234, dsn=dsn)
    results = repeat_scenario(config, repeats=3)
    assert len({r.config.seed for r in results}) == 3
    assert 1.0 < median_corruption(results) < 2.0


def test_handler_failure_pushes_corruption_below_amplification(dsn):
    config = ScenarioConfig(messages=2000, ack_loss=0.2, handler_failure=0.3,
                            seed=8, dsn=dsn)
    result = run_scenario(config)
    assert result.corruption < result.amplification


def test_a_retry_budget_cuts_attempts(dsn):
    fields = dict(messages=500, ack_loss=0.6, seed=3, dsn=dsn)
    free = run_scenario(ScenarioConfig(retry_policy="immediate", **fields))
    budgeted = run_scenario(ScenarioConfig(retry_policy="budgeted",
                                           retry_budget=50, **fields))
    assert budgeted.stats.attempts < free.stats.attempts
    assert budgeted.stats.retries_refused > 0

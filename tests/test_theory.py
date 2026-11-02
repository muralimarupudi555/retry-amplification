"""The series, checked against things that must be true of it.

These tests do not re-implement the formula and compare, which would only prove the
formula equals itself. They assert properties: limits, monotonicity, the identity that
makes corruption and amplification the same number, and the one condition that separates
them.
"""

from __future__ import annotations

import pytest

from retry_amplification import theory
from retry_amplification.config import ScenarioConfig


def test_no_loss_means_one_attempt():
    assert theory.expected_attempts_per_message(0.0, 5) == pytest.approx(1.0)


def test_attempts_rise_with_loss():
    values = [theory.expected_attempts_per_message(p, 5) for p in (0.1, 0.3, 0.5, 0.7)]
    assert values == sorted(values)


def test_attempts_rise_with_the_cap():
    values = [theory.expected_attempts_per_message(0.5, r) for r in (1, 2, 5, 10)]
    assert values == sorted(values)


def test_capped_series_stays_under_the_uncapped_limit():
    for p in (0.1, 0.5, 0.9):
        assert theory.expected_attempts_per_message(p, 8) < theory.uncapped_attempts_per_message(p)


def test_uncapped_limit_is_one_over_success():
    assert theory.uncapped_attempts_per_message(0.75) == pytest.approx(4.0)


def test_a_large_cap_approaches_the_limit():
    assert theory.expected_attempts_per_message(0.5, 40) == pytest.approx(2.0, rel=1e-9)


def test_corruption_equals_amplification_without_handler_failure():
    """The identity the repository is built on: one number, read twice."""
    config = ScenarioConfig(handler="naive", ack_loss=0.4, handler_failure=0.0)
    assert theory.predicted_corruption(config) == pytest.approx(
        theory.predicted_amplification(config)
    )


def test_handler_failure_separates_them():
    """A failure before the effect costs an attempt and applies nothing."""
    config = ScenarioConfig(handler="naive", ack_loss=0.2, handler_failure=0.3)
    assert theory.predicted_corruption(config) < theory.predicted_amplification(config)


def test_handler_failure_alone_can_push_corruption_below_one():
    """Attempts amplify while effects go missing: the two move in opposite directions."""
    config = ScenarioConfig(handler="naive", ack_loss=0.0, handler_failure=0.5,
                            max_attempts=5)
    assert theory.predicted_amplification(config) > 1.0
    assert theory.predicted_corruption(config) < 1.0


def test_idempotent_handler_is_predicted_to_apply_once_whatever_happens():
    for p in (0.0, 0.3, 0.9):
        config = ScenarioConfig(handler="idempotent", ack_loss=p)
        assert theory.predicted_corruption(config) == 1.0


def test_unacknowledged_rate_falls_as_the_cap_rises():
    values = [theory.predicted_unacknowledged_rate(0.5, r) for r in (1, 2, 4, 8)]
    assert values == sorted(values, reverse=True)


def test_the_cap_trades_one_against_the_other():
    """Raising the cap cannot improve both numbers, which is why there is no good cap."""
    low_attempts = theory.expected_attempts_per_message(0.5, 3)
    high_attempts = theory.expected_attempts_per_message(0.5, 9)
    low_unacked = theory.predicted_unacknowledged_rate(0.5, 3)
    high_unacked = theory.predicted_unacknowledged_rate(0.5, 9)
    assert high_attempts > low_attempts
    assert high_unacked < low_unacked


def test_retry_probability_combines_both_causes():
    assert theory.retry_probability(0.5, 0.5) == pytest.approx(0.75)


def test_agreement_band_is_relative():
    assert theory.agrees(1.02, 1.00, tolerance=0.05)
    assert not theory.agrees(1.30, 1.00, tolerance=0.05)

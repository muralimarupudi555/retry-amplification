"""A scenario that cannot produce a trustworthy measurement should not start."""

from __future__ import annotations

import pytest

from retry_amplification.config import ConfigError, ScenarioConfig


def test_defaults_are_valid():
    assert ScenarioConfig().handler == "naive"


@pytest.mark.parametrize("handler", ["naive", "idempotent"])
def test_both_handlers_accepted(handler):
    assert ScenarioConfig(handler=handler).handler == handler


def test_unknown_handler_refused():
    with pytest.raises(ConfigError, match="handler must be one of"):
        ScenarioConfig(handler="eventually")


def test_unknown_policy_refused():
    with pytest.raises(ConfigError, match="retry_policy must be one of"):
        ScenarioConfig(retry_policy="hope")


def test_total_ack_loss_refused():
    """At p = 1 nothing ever completes, so the run measures the cap, not the delivery."""
    with pytest.raises(ConfigError, match="no message ever completes"):
        ScenarioConfig(ack_loss=1.0)


def test_negative_ack_loss_refused():
    with pytest.raises(ConfigError):
        ScenarioConfig(ack_loss=-0.1)


def test_tiny_batch_refused():
    """Corruption is reported as a rate and a rate needs a sample behind it."""
    with pytest.raises(ConfigError, match="sampling error"):
        ScenarioConfig(messages=20)


def test_zero_attempts_refused():
    with pytest.raises(ConfigError, match="max_attempts"):
        ScenarioConfig(max_attempts=0)


def test_budgeted_policy_needs_a_budget():
    with pytest.raises(ConfigError, match="extra steps"):
        ScenarioConfig(retry_policy="budgeted", retry_budget=0)


def test_budgeted_policy_accepts_a_budget():
    assert ScenarioConfig(retry_policy="budgeted", retry_budget=100).retry_budget == 100


def test_config_is_frozen():
    config = ScenarioConfig()
    with pytest.raises(Exception):
        config.ack_loss = 0.9  # type: ignore[misc]


def test_as_dict_round_trips_through_the_constructor():
    config = ScenarioConfig(handler="idempotent", ack_loss=0.4, messages=900)
    assert ScenarioConfig(**config.as_dict()).as_dict() == config.as_dict()

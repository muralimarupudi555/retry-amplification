"""Scenario configuration, validated on construction."""

from __future__ import annotations

import os
from dataclasses import dataclass

HANDLERS = ("naive", "idempotent")
RETRY_POLICIES = ("immediate", "exponential_backoff", "budgeted")

MIN_MESSAGES = 500

DEFAULT_DSN = os.environ.get(
    "RETRY_AMPLIFICATION_DSN",
    "postgresql://postgres:postgres@127.0.0.1:5433/postgres",
)


class ConfigError(ValueError):
    """Raised when a scenario would produce a measurement that cannot be trusted."""


@dataclass(frozen=True)
class ScenarioConfig:
    """One delivery run: how lossy the acknowledgements are and how the worker responds."""

    handler: str = "naive"
    retry_policy: str = "immediate"
    ack_loss: float = 0.25
    handler_failure: float = 0.0
    messages: int = 2000
    max_attempts: int = 5
    retry_budget: int = 0
    backoff_base_ms: float = 1.0
    seed: int = 20260219
    dsn: str = DEFAULT_DSN

    def __post_init__(self) -> None:
        if self.handler not in HANDLERS:
            raise ConfigError(f"handler must be one of {HANDLERS}, got {self.handler!r}")
        if self.retry_policy not in RETRY_POLICIES:
            raise ConfigError(
                f"retry_policy must be one of {RETRY_POLICIES}, got {self.retry_policy!r}"
            )
        if not 0.0 <= self.ack_loss < 1.0:
            raise ConfigError(
                f"ack_loss={self.ack_loss} must be in [0, 1). At 1 every acknowledgement "
                "is lost, so no message ever completes and the run measures the retry "
                "cap rather than the delivery."
            )
        if not 0.0 <= self.handler_failure < 1.0:
            raise ConfigError(f"handler_failure={self.handler_failure} must be in [0, 1)")
        if self.messages < MIN_MESSAGES:
            raise ConfigError(
                f"messages={self.messages} is below {MIN_MESSAGES}. Corruption is "
                "reported as a rate, and a rate over a few hundred samples carries more "
                "sampling error than the differences this repository reports."
            )
        if self.max_attempts < 1:
            raise ConfigError(f"max_attempts={self.max_attempts} must be at least 1")
        if self.retry_budget < 0:
            raise ConfigError(f"retry_budget={self.retry_budget} cannot be negative")
        if self.retry_policy == "budgeted" and self.retry_budget <= 0:
            raise ConfigError(
                "the budgeted policy needs a retry_budget above zero, otherwise it is "
                "the immediate policy with extra steps"
            )
        if self.backoff_base_ms < 0:
            raise ConfigError("backoff_base_ms cannot be negative")

    def as_dict(self) -> dict:
        return {
            "handler": self.handler, "retry_policy": self.retry_policy,
            "ack_loss": self.ack_loss, "handler_failure": self.handler_failure,
            "messages": self.messages, "max_attempts": self.max_attempts,
            "retry_budget": self.retry_budget,
            "backoff_base_ms": self.backoff_base_ms, "seed": self.seed,
        }

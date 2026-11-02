"""An at-least-once broker, small enough to read in one sitting.

A real broker is a network service with a visibility timeout, a redelivery policy and an
operations manual. None of that changes the mechanism under test here, which is what a
handler does when the same message arrives twice; ADR-001 argues the case. What this does
provide is the one thing a real broker will not: an acknowledgement loss rate that is a
number you set rather than a number you wait for.

The loss is injected on the acknowledgement path, after the handler has returned. That
placement is the whole experiment. A message whose ack is lost has already done its work,
and the broker cannot tell that apart from a message that was never processed at all.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class DeliveryStats:
    """What the broker saw, as opposed to what the handler did."""

    messages: int = 0
    attempts: int = 0
    acknowledged: int = 0
    unacknowledged: int = 0
    handler_failures: int = 0
    retries_refused: int = 0
    attempts_per_message: list[int] = field(default_factory=list)

    @property
    def amplification(self) -> float:
        return self.attempts / self.messages if self.messages else 0.0

    @property
    def unacknowledged_rate(self) -> float:
        return self.unacknowledged / self.messages if self.messages else 0.0

    def as_dict(self) -> dict:
        return {
            "messages": self.messages, "attempts": self.attempts,
            "acknowledged": self.acknowledged, "unacknowledged": self.unacknowledged,
            "handler_failures": self.handler_failures,
            "retries_refused": self.retries_refused,
            "amplification": round(self.amplification, 4),
            "unacknowledged_rate": round(self.unacknowledged_rate, 4),
            "max_attempts_seen": max(self.attempts_per_message, default=0),
        }


class HandlerFailed(Exception):
    """Raised by a handler that could not finish, before its effect landed."""


@dataclass
class RetryBudget:
    """A shared allowance of retries across the batch.

    This is the only mechanism in this repository that reduces total attempts, and it does
    it by refusing to retry rather than by waiting longer. The refused messages are
    counted, because the cost has to appear somewhere: a budget does not make failures
    cheaper, it makes them visible.
    """

    allowance: int
    spent: int = 0

    def take(self) -> bool:
        if self.spent >= self.allowance:
            return False
        self.spent += 1
        return True


class Broker:
    """Deliver each message until it is acknowledged or the policy stops trying."""

    def __init__(self, ack_loss: float, max_attempts: int, seed: int,
                 budget: RetryBudget | None = None,
                 on_backoff: Callable[[int], None] | None = None,
                 backoff_base_ms: float = 0.0) -> None:
        self.ack_loss = ack_loss
        self.max_attempts = max_attempts
        self.rng = random.Random(seed)
        self.budget = budget
        self.on_backoff = on_backoff
        self.backoff_base_ms = backoff_base_ms

    def deliver(self, message_ids: list[str],
                handler: Callable[[str, int], None]) -> DeliveryStats:
        """Run every message to acknowledgement, exhaustion, or refusal."""
        stats = DeliveryStats(messages=len(message_ids))

        for message_id in message_ids:
            attempts = 0
            acknowledged = False

            while attempts < self.max_attempts:
                attempts += 1
                stats.attempts += 1

                try:
                    handler(message_id, attempts)
                except HandlerFailed:
                    stats.handler_failures += 1
                else:
                    # The effect has landed. Only the acknowledgement is in doubt now, and
                    # a lost one is indistinguishable from work that never happened.
                    if self.rng.random() >= self.ack_loss:
                        acknowledged = True
                        break

                if attempts >= self.max_attempts:
                    break
                if self.budget is not None and not self.budget.take():
                    stats.retries_refused += 1
                    break
                if self.on_backoff is not None:
                    self.on_backoff(attempts)

            stats.attempts_per_message.append(attempts)
            if acknowledged:
                stats.acknowledged += 1
            else:
                stats.unacknowledged += 1

        return stats

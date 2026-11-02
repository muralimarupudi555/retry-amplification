"""The broker, tested without a database.

Delivery accounting is arithmetic and deserves to be tested as arithmetic. These use a
handler that records what it was given rather than one that writes anything, so a failure
here is unambiguously the broker's.
"""

from __future__ import annotations

import pytest

from retry_amplification.broker import Broker, HandlerFailed, RetryBudget


def collector():
    seen: list[tuple[str, int]] = []

    def handler(message_id: str, attempt: int) -> None:
        seen.append((message_id, attempt))

    return seen, handler


def test_no_loss_means_one_attempt_each():
    seen, handler = collector()
    stats = Broker(ack_loss=0.0, max_attempts=5, seed=1).deliver(["a", "b", "c"], handler)
    assert stats.attempts == 3
    assert stats.acknowledged == 3
    assert stats.unacknowledged == 0
    assert [attempt for _, attempt in seen] == [1, 1, 1]


def test_total_loss_exhausts_the_cap():
    """The broker is allowed to be driven past what the config would permit."""
    seen, handler = collector()
    stats = Broker(ack_loss=1.0, max_attempts=4, seed=1).deliver(["a"], handler)
    assert stats.attempts == 4
    assert stats.unacknowledged == 1
    assert [attempt for _, attempt in seen] == [1, 2, 3, 4]


def test_attempt_numbers_are_passed_to_the_handler():
    seen, handler = collector()
    Broker(ack_loss=1.0, max_attempts=3, seed=1).deliver(["x"], handler)
    assert seen == [("x", 1), ("x", 2), ("x", 3)]


def test_amplification_is_attempts_over_messages():
    _, handler = collector()
    stats = Broker(ack_loss=1.0, max_attempts=3, seed=1).deliver(["a", "b"], handler)
    assert stats.attempts == 6
    assert stats.amplification == pytest.approx(3.0)


def test_a_failing_handler_is_retried_and_counted():
    calls = {"n": 0}

    def flaky(message_id: str, attempt: int) -> None:
        calls["n"] += 1
        if attempt < 3:
            raise HandlerFailed(message_id)

    stats = Broker(ack_loss=0.0, max_attempts=5, seed=1).deliver(["a"], flaky)
    assert calls["n"] == 3
    assert stats.handler_failures == 2
    assert stats.acknowledged == 1


def test_a_handler_that_always_fails_is_never_acknowledged():
    def always(message_id: str, attempt: int) -> None:
        raise HandlerFailed(message_id)

    stats = Broker(ack_loss=0.0, max_attempts=3, seed=1).deliver(["a"], always)
    assert stats.unacknowledged == 1
    assert stats.handler_failures == 3


def test_a_budget_stops_retries_and_says_so():
    _, handler = collector()
    budget = RetryBudget(allowance=2)
    stats = Broker(ack_loss=1.0, max_attempts=10, seed=1,
                   budget=budget).deliver(["a", "b", "c"], handler)
    # The first message spends both tokens and is then refused; the other two are
    # refused on their first retry. Five attempts in total, three messages stopped by
    # the budget rather than by the cap. Refusals count messages denied, not tokens
    # spent, and the two differ whenever one message consumes the whole allowance.
    assert stats.attempts == 5
    assert stats.retries_refused == 3
    assert budget.spent == 2


def test_an_exhausted_budget_refuses_everything_after_it():
    _, handler = collector()
    stats = Broker(ack_loss=1.0, max_attempts=10, seed=1,
                   budget=RetryBudget(allowance=0)).deliver(["a", "b"], handler)
    assert stats.attempts == 2
    assert stats.retries_refused == 2


def test_the_budget_is_not_spent_when_the_cap_already_stopped_the_message():
    """A message that hit its cap must not also be billed for a retry it never made."""
    _, handler = collector()
    budget = RetryBudget(allowance=100)
    Broker(ack_loss=1.0, max_attempts=2, seed=1, budget=budget).deliver(["a"], handler)
    assert budget.spent == 1


def test_backoff_is_called_once_per_retry_not_per_attempt():
    waits: list[int] = []
    _, handler = collector()
    Broker(ack_loss=1.0, max_attempts=4, seed=1,
           on_backoff=waits.append).deliver(["a"], handler)
    # Four attempts, three gaps between them.
    assert waits == [1, 2, 3]


def test_backoff_is_not_called_when_nothing_is_retried():
    waits: list[int] = []
    _, handler = collector()
    Broker(ack_loss=0.0, max_attempts=4, seed=1,
           on_backoff=waits.append).deliver(["a"], handler)
    assert waits == []


def test_the_same_seed_gives_the_same_delivery():
    _, first = collector()
    _, second = collector()
    messages = [f"m{i}" for i in range(200)]
    a = Broker(ack_loss=0.5, max_attempts=5, seed=42).deliver(messages, first)
    b = Broker(ack_loss=0.5, max_attempts=5, seed=42).deliver(messages, second)
    assert a.attempts == b.attempts
    assert a.attempts_per_message == b.attempts_per_message


def test_different_seeds_give_different_deliveries():
    _, first = collector()
    _, second = collector()
    messages = [f"m{i}" for i in range(200)]
    a = Broker(ack_loss=0.5, max_attempts=5, seed=1).deliver(messages, first)
    b = Broker(ack_loss=0.5, max_attempts=5, seed=2).deliver(messages, second)
    assert a.attempts != b.attempts

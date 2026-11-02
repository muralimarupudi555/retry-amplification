"""What the numbers should be, derived before anything was measured.

A worker takes a message, runs a handler, and acknowledges. Two things can send it round
again. The handler can fail before its effect lands, with probability f. Or the effect can
land and the acknowledgement can be lost, with probability p, in which case the broker has
no way of knowing the work was done and delivers it again. A worker retries until the
broker sees an acknowledgement or the attempt cap R is reached.

Write q for the chance an attempt leads to another one::

    q = f + (1 - f) * p

The number of attempts a message takes is then a truncated geometric variable and its
expectation is a finite series::

    attempts per message = 1 + q + q^2 + ... + q^(R-1)

Two quantities come out of that one expression, which is the point of this repository.

**Amplification** is the series itself. Every attempt is a real delivery, a real
connection, a real query. At q = 0.5 with five attempts allowed, a queue carrying a
thousand messages a second is handing its workers nearly two thousand.

**Corruption** is the share of those attempts whose effect actually lands, (1 - f) times
the series. For a handler that is not idempotent, every landed effect applies again: the
balance moves twice, the email goes twice, the charge goes twice.

When f is zero the two are the same number. The load multiplier and the data damage are
not two problems; they are one number read twice. They separate only when the handler
fails before its effect lands, which is the one failure mode a retry is actually safe for.

Uncapped, the series converges to 1 / (1 - q). An unbounded retry loop against a
half-failing dependency doubles the load rather than exploding: the damage is bounded by
the failure rate, not by patience.
"""

from __future__ import annotations

from retry_amplification.config import ScenarioConfig

# Measured rates come from a finite number of messages, so they carry sampling error. This
# band is wide enough to absorb it at the sample sizes used here and narrow enough that a
# real disagreement with the series would fail.
AGREEMENT_TOLERANCE = 0.05


def retry_probability(ack_loss: float, handler_failure: float = 0.0) -> float:
    """Chance that one attempt leads to another, from either cause."""
    return handler_failure + (1.0 - handler_failure) * ack_loss


def expected_attempts_per_message(ack_loss: float, max_attempts: int,
                                  handler_failure: float = 0.0) -> float:
    """The truncated geometric series: the load multiplier."""
    q = retry_probability(ack_loss, handler_failure)
    if q <= 0:
        return 1.0
    return sum(q**k for k in range(max_attempts))


def uncapped_attempts_per_message(ack_loss: float, handler_failure: float = 0.0) -> float:
    """The limit as the attempt cap is removed: one over the success probability."""
    q = retry_probability(ack_loss, handler_failure)
    if q >= 1.0:
        return float("inf")
    return 1.0 / (1.0 - q)


def predicted_amplification(config: ScenarioConfig) -> float:
    """Attempts per message, which is what everything downstream of the worker sees."""
    return expected_attempts_per_message(
        config.ack_loss, config.max_attempts, config.handler_failure
    )


def predicted_corruption(config: ScenarioConfig) -> float:
    """How many times the average message's effect is applied.

    For an idempotent handler this is one, whatever the retries do, because the ledger
    makes every application after the first a no-op. For a naive handler it is the share
    of attempts that reach the effect, which is the amplification less the attempts the
    handler threw away before touching anything.
    """
    if config.handler == "idempotent":
        return 1.0
    return (1.0 - config.handler_failure) * predicted_amplification(config)


def predicted_unacknowledged_rate(ack_loss: float, max_attempts: int,
                                  handler_failure: float = 0.0) -> float:
    """Share of messages that exhaust the cap without the broker seeing an ack.

    Every one of those attempts applied; only the acknowledgement never arrived. A real
    broker redelivers these after the visibility timeout, so this is not a loss rate so
    much as a queue that will not drain. Raising the cap lowers it and raises
    amplification, which is the trade the cap actually makes.
    """
    return retry_probability(ack_loss, handler_failure) ** max_attempts


def agrees(measured: float, predicted: float,
           tolerance: float = AGREEMENT_TOLERANCE) -> bool:
    if predicted <= 0:
        return measured <= tolerance
    return abs(measured - predicted) / predicted <= tolerance

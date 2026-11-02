"""Run one scenario end to end and record both of its outcomes.

Two numbers come back from every run and they are deliberately measured by different
means. Amplification is counted by the broker, which knows how many times it handed a
message over. Corruption is read out of the database afterwards, from the account balance,
which knows nothing about brokers and cannot be talked into agreeing.

That separation is the point. If the two agree, they agree because the mechanism is real.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass

import psycopg

from retry_amplification.broker import Broker, DeliveryStats, RetryBudget
from retry_amplification.config import ScenarioConfig
from retry_amplification.handlers import Handler, ensure_schema, ledger_size, read_balance


@dataclass(frozen=True)
class RunResult:
    """One scenario: what the broker counted and what the database ended up holding."""

    config: ScenarioConfig
    stats: DeliveryStats
    final_balance: int
    applies: int
    skipped: int
    ledger_rows: int
    wall_seconds: float
    attempt_p50_ms: float
    attempt_p99_ms: float

    @property
    def corruption(self) -> float:
        """Applications per message, read from the balance rather than from the broker."""
        return self.final_balance / self.config.messages if self.config.messages else 0.0

    @property
    def amplification(self) -> float:
        return self.stats.amplification

    @property
    def overapplied(self) -> int:
        """Units of money that exist because of retries and should not."""
        return self.final_balance - self.config.messages

    @property
    def exactly_once(self) -> bool:
        return self.final_balance == self.config.messages

    def as_dict(self) -> dict:
        return {
            "config": self.config.as_dict(),
            "delivery": self.stats.as_dict(),
            "final_balance": self.final_balance,
            "expected_balance": self.config.messages,
            "overapplied": self.overapplied,
            "corruption": round(self.corruption, 4),
            "amplification": round(self.amplification, 4),
            "exactly_once": self.exactly_once,
            "applies": self.applies, "skipped": self.skipped,
            "ledger_rows": self.ledger_rows,
            "wall_seconds": round(self.wall_seconds, 4),
            "attempt_p50_ms": round(self.attempt_p50_ms, 4),
            "attempt_p99_ms": round(self.attempt_p99_ms, 4),
        }


def _percentile(ordered: list[float], q: float) -> float:
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, max(0, int(round(q * (len(ordered) - 1)))))
    return ordered[index]


def run_scenario(config: ScenarioConfig) -> RunResult:
    """Deliver `messages` messages under the scenario's policy and read the damage."""
    ensure_schema(config.dsn)
    message_ids = [f"m-{i:07d}" for i in range(config.messages)]
    budget = RetryBudget(config.retry_budget) if config.retry_policy == "budgeted" else None

    timings: list[float] = []

    def backoff(attempt: int) -> None:
        # Exponential, capped at the eighth doubling so a long run stays runnable. The
        # cap matters for wall clock and not at all for attempt counts, which is the
        # finding E4 exists to make.
        if config.backoff_base_ms <= 0:
            return
        time.sleep(config.backoff_base_ms * (2 ** min(attempt - 1, 8)) / 1000.0)

    with psycopg.connect(config.dsn) as conn:
        handler = Handler(
            conn=conn, idempotent=config.handler == "idempotent",
            handler_failure=config.handler_failure, seed=config.seed,
        )

        def timed(message_id: str, attempt: int) -> None:
            started = time.perf_counter()
            try:
                handler(message_id, attempt)
            finally:
                timings.append((time.perf_counter() - started) * 1000.0)

        broker = Broker(
            ack_loss=config.ack_loss, max_attempts=config.max_attempts,
            seed=config.seed, budget=budget,
            on_backoff=backoff if config.retry_policy == "exponential_backoff" else None,
            backoff_base_ms=config.backoff_base_ms,
        )
        started = time.perf_counter()
        stats = broker.deliver(message_ids, timed)
        wall = time.perf_counter() - started

    ordered = sorted(timings)
    return RunResult(
        config=config, stats=stats,
        final_balance=read_balance(config.dsn),
        applies=handler.applies, skipped=handler.skipped,
        ledger_rows=ledger_size(config.dsn), wall_seconds=wall,
        attempt_p50_ms=_percentile(ordered, 0.50),
        attempt_p99_ms=_percentile(ordered, 0.99),
    )


def repeat_scenario(config: ScenarioConfig, repeats: int = 3) -> list[RunResult]:
    """Run the same scenario on different seeds, because these are sampled quantities."""
    results = []
    for index in range(repeats):
        seeded = ScenarioConfig(**{**config.as_dict(), "seed": config.seed + index * 101,
                                   "dsn": config.dsn})
        results.append(run_scenario(seeded))
    return results


def median_corruption(results: list[RunResult]) -> float:
    return statistics.median(r.corruption for r in results)


def median_amplification(results: list[RunResult]) -> float:
    return statistics.median(r.amplification for r in results)

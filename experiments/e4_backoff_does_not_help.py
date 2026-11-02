"""E4. Exponential backoff does not reduce retry amplification. It reschedules it.

This is the experiment that changes what someone does on Monday.

When a dependency starts failing and the load on it doubles, the reflex is to add backoff.
Backoff is genuinely useful: it stops a thundering herd arriving in lockstep and it gives
a struggling dependency quiet gaps to recover in. What it does not do is reduce the number
of attempts, because the series in theory.py has no time in it. A message that needs four
attempts needs four attempts whether they arrive in four milliseconds or four minutes.

Three policies, identical acknowledgement loss, identical seed:

- **immediate** retries as fast as it can.
- **exponential_backoff** waits longer between each attempt.
- **budgeted** allows a fixed number of retries across the whole batch and then stops.

The attempt counts for the first two should be the same number. Only the third should
move, and it moves by abandoning messages, which is the honest shape of the trade: a
budget does not make failure cheaper, it makes failure visible and bounded. That is also
what a circuit breaker does, with the accounting done per dependency instead of per batch.
"""

from __future__ import annotations

import json
from pathlib import Path

from retry_amplification.config import DEFAULT_DSN, ScenarioConfig
from retry_amplification.harness import run_scenario

OUT = Path(__file__).resolve().parent.parent / "docs" / "experiments"
MESSAGES = 2000
ACK_LOSS = 0.5
BUDGET = 400


def main() -> None:
    policies = [
        ("immediate", dict(retry_policy="immediate")),
        ("exponential_backoff",
         dict(retry_policy="exponential_backoff", backoff_base_ms=1.0)),
        ("budgeted", dict(retry_policy="budgeted", retry_budget=BUDGET)),
    ]

    rows = []
    for name, extra in policies:
        config = ScenarioConfig(handler="naive", ack_loss=ACK_LOSS, messages=MESSAGES,
                                seed=20260219, dsn=DEFAULT_DSN, **extra)
        run = run_scenario(config)
        rows.append({
            "policy": name,
            "attempts": run.stats.attempts,
            "amplification": round(run.amplification, 4),
            "wall_seconds": round(run.wall_seconds, 3),
            "overapplied": run.overapplied,
            "unacknowledged": run.stats.unacknowledged,
            "unacknowledged_rate": round(run.stats.unacknowledged_rate, 4),
            "retries_refused": run.stats.retries_refused,
        })
        print(f"  {name:20} {run.stats.attempts:6} attempts  "
              f"{run.amplification:5.3f}x  {run.wall_seconds:7.2f}s  "
              f"+{run.overapplied:5} units  "
              f"{run.stats.unacknowledged_rate:6.2%} never acked")

    immediate, backoff, budgeted = rows
    attempts_match = immediate["attempts"] == backoff["attempts"]
    corruption_match = immediate["overapplied"] == backoff["overapplied"]
    backoff_is_slower = backoff["wall_seconds"] > immediate["wall_seconds"] * 2
    budget_cuts_attempts = budgeted["attempts"] < immediate["attempts"]
    budget_abandons_messages = (
        budgeted["unacknowledged"] > immediate["unacknowledged"])

    payload = {
        "experiment": "e4_backoff_does_not_help",
        "messages": MESSAGES, "ack_loss": ACK_LOSS, "retry_budget": BUDGET,
        "rows": rows,
        "backoff_attempts_identical": attempts_match,
        "backoff_corruption_identical": corruption_match,
        "backoff_is_slower": backoff_is_slower,
        "backoff_slowdown": round(
            backoff["wall_seconds"] / immediate["wall_seconds"], 2),
        "budget_cuts_attempts": budget_cuts_attempts,
        "budget_abandons_messages": budget_abandons_messages,
        "attempts_saved_by_budget": immediate["attempts"] - budgeted["attempts"],
        "messages_abandoned_by_budget": (
            budgeted["unacknowledged"] - immediate["unacknowledged"]),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "e4.json").write_text(json.dumps(payload, indent=2) + "\n")

    print()
    print(f"backoff ran the identical number of attempts: {attempts_match}")
    print(f"backoff caused the identical corruption:      {corruption_match}")
    print(f"backoff took {payload['backoff_slowdown']}x as long to do it")
    print(f"the budget removed {payload['attempts_saved_by_budget']} attempts "
          f"by abandoning {payload['messages_abandoned_by_budget']} messages")


if __name__ == "__main__":
    main()

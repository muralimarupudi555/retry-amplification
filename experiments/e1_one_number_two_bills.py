"""E1. Corruption and amplification are the same number read twice.

Sweep the acknowledgement loss rate and run the same seeded delivery past both handlers.
Three things should fall out, and only the third is in any doubt before the run:

1. The naive handler's balance inflates, and the inflation is the attempt count.
2. The idempotent handler's balance is exactly the message count at every loss rate.
3. The idempotent handler's attempt count is identical to the naive one's, because a
   ledger changes what an attempt does and not how many there are.

The third is the one worth running the experiment for. Idempotency is widely understood
as the fix for at-least-once delivery, and it is - for the data. The load it does nothing
about at all, and a service that adds a ledger and keeps falling over has usually been
sold the ledger as a fix for both.
"""

from __future__ import annotations

import json
from pathlib import Path

from retry_amplification import theory
from retry_amplification.config import DEFAULT_DSN, ScenarioConfig
from retry_amplification.harness import run_scenario

OUT = Path(__file__).resolve().parent.parent / "docs" / "experiments"
ACK_LOSS = (0.0, 0.1, 0.25, 0.4, 0.5, 0.6, 0.75)
MESSAGES = 4000


def main() -> None:
    rows = []
    for ack_loss in ACK_LOSS:
        shared = dict(ack_loss=ack_loss, messages=MESSAGES, seed=20260219, dsn=DEFAULT_DSN)
        naive = run_scenario(ScenarioConfig(handler="naive", **shared))
        idem = run_scenario(ScenarioConfig(handler="idempotent", **shared))
        rows.append({
            "ack_loss": ack_loss,
            "predicted_attempts": round(
                theory.expected_attempts_per_message(ack_loss, 5), 4),
            "naive_attempts": round(naive.amplification, 4),
            "idempotent_attempts": round(idem.amplification, 4),
            "naive_balance": naive.final_balance,
            "idempotent_balance": idem.final_balance,
            "naive_corruption": round(naive.corruption, 4),
            "idempotent_corruption": round(idem.corruption, 4),
            "overapplied": naive.overapplied,
            "ledger_skipped": idem.skipped,
            "unacknowledged_rate": round(naive.stats.unacknowledged_rate, 4),
        })
        print(f"  p={ack_loss:4.2f}  naive {naive.final_balance:6} "
              f"idempotent {idem.final_balance:6}  "
              f"attempts {naive.amplification:5.3f}/{idem.amplification:5.3f}")

    identical_attempts = all(
        abs(r["naive_attempts"] - r["idempotent_attempts"]) < 0.02 for r in rows)
    ledger_catches_exactly = all(r["ledger_skipped"] == r["overapplied"] for r in rows)
    idempotent_always_exact = all(r["idempotent_balance"] == MESSAGES for r in rows)

    payload = {
        "experiment": "e1_one_number_two_bills",
        "messages": MESSAGES, "max_attempts": 5, "rows": rows,
        "identical_attempts": identical_attempts,
        "ledger_catches_exactly": ledger_catches_exactly,
        "idempotent_always_exact": idempotent_always_exact,
        "worst_inflation": max(r["naive_corruption"] for r in rows),
        "worst_overapplied": max(r["overapplied"] for r in rows),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "e1.json").write_text(json.dumps(payload, indent=2) + "\n")

    print()
    print(f"idempotent balance exact at every loss rate: {idempotent_always_exact}")
    print(f"ledger skips exactly what naive overapplies:  {ledger_catches_exactly}")
    print(f"attempt counts identical across handlers:     {identical_attempts}")
    print(f"worst inflation {payload['worst_inflation']:.3f}x, "
          f"{payload['worst_overapplied']} units that should not exist")


if __name__ == "__main__":
    main()

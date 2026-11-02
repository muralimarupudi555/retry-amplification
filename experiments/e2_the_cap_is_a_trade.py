"""E2. The attempt cap does not reduce damage. It chooses which damage you get.

The obvious response to E1 is to turn the retries down. So sweep the cap at a fixed
acknowledgement loss rate and watch both consequences at once.

Raising the cap raises amplification and the units that should not exist. Lowering it
raises the share of messages the broker never sees acknowledged - and those messages
already applied, so a real broker will redeliver them after the visibility timeout and
apply them again, outside the window this harness watches. There is no setting that
improves both, because they are the same series read from opposite ends.

The second half of the sweep is the payoff. Run the identical caps past the idempotent
handler and the data column stops moving entirely: the cap goes back to being an
operational decision about load, which is the only kind of decision it should ever have
been.
"""

from __future__ import annotations

import json
from pathlib import Path

from retry_amplification import theory
from retry_amplification.config import DEFAULT_DSN, ScenarioConfig
from retry_amplification.harness import run_scenario

OUT = Path(__file__).resolve().parent.parent / "docs" / "experiments"
CAPS = (1, 2, 3, 5, 8, 12)
ACK_LOSS = 0.5
MESSAGES = 4000


def main() -> None:
    rows = []
    for cap in CAPS:
        shared = dict(ack_loss=ACK_LOSS, max_attempts=cap, messages=MESSAGES,
                      seed=20260219, dsn=DEFAULT_DSN)
        naive = run_scenario(ScenarioConfig(handler="naive", **shared))
        idem = run_scenario(ScenarioConfig(handler="idempotent", **shared))
        rows.append({
            "max_attempts": cap,
            "attempts_per_message": round(naive.amplification, 4),
            "predicted_attempts": round(
                theory.expected_attempts_per_message(ACK_LOSS, cap), 4),
            "naive_balance": naive.final_balance,
            "overapplied": naive.overapplied,
            "idempotent_balance": idem.final_balance,
            "unacknowledged_rate": round(naive.stats.unacknowledged_rate, 4),
            "predicted_unacknowledged": round(
                theory.predicted_unacknowledged_rate(ACK_LOSS, cap), 4),
        })
        print(f"  cap {cap:2}  attempts {naive.amplification:5.3f}  "
              f"naive {naive.final_balance:6} (+{naive.overapplied:5})  "
              f"idempotent {idem.final_balance:6}  "
              f"never acked {naive.stats.unacknowledged_rate:6.4f}")

    attempts = [r["attempts_per_message"] for r in rows]
    unacked = [r["unacknowledged_rate"] for r in rows]
    no_cap_wins_twice = attempts == sorted(attempts) and unacked == sorted(
        unacked, reverse=True)
    idempotent_flat = len({r["idempotent_balance"] for r in rows}) == 1

    payload = {
        "experiment": "e2_the_cap_is_a_trade",
        "ack_loss": ACK_LOSS, "messages": MESSAGES, "rows": rows,
        "no_cap_improves_both": no_cap_wins_twice,
        "idempotent_balance_is_flat_across_caps": idempotent_flat,
        "cheapest_cap_overapplied": rows[0]["overapplied"],
        "cheapest_cap_unacknowledged": rows[0]["unacknowledged_rate"],
        "dearest_cap_overapplied": rows[-1]["overapplied"],
        "dearest_cap_unacknowledged": rows[-1]["unacknowledged_rate"],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "e2.json").write_text(json.dumps(payload, indent=2) + "\n")

    print()
    print(f"every cap trades one cost for the other:   {no_cap_wins_twice}")
    print(f"idempotent balance unmoved by the cap:     {idempotent_flat}")
    print(f"cap 1: {rows[0]['overapplied']} extra units but "
          f"{rows[0]['unacknowledged_rate']:.1%} never acknowledged")
    print(f"cap 12: {rows[-1]['overapplied']} extra units and "
          f"{rows[-1]['unacknowledged_rate']:.1%} never acknowledged")


if __name__ == "__main__":
    main()

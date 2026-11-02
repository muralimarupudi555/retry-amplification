"""E3. The ledger is not free, and this is the bill.

E1 and E2 make the ledger look like an unambiguous win, which is a good reason to go
looking for its price.

The first version of this experiment measured the price by running the two handlers and
comparing median attempt latency. That was wrong twice over. It pooled two operations
whose costs differ by a factor of three - performing an application and declining one -
so as the loss rate rose and declines came to dominate the mix, the ledger appeared to get
*cheaper* the harder it was working. And once the paths were separated, a 0.15ms
difference between two whole runs turned out to sit inside the run-to-run drift of a
two-core box: six paired runs gave overheads between 6% and 52%.

So the cost is measured where it actually lives, at the statement level, with the three
operations interleaved inside one connection so that drift lands on all of them equally.
Split-half is the apparatus check, and it is applied to the ratio rather than to the raw
timings. The raw timings do drift - by around a sixth over three thousand samples - but
they drift together, including the plain update that never touches the ledger table, so
the drift is the machine rather than the mechanism. A paired measurement claims a ratio,
so the ratio is what has to hold still, and the absolute drift is reported beside it to
show why that is the right thing to check.

The decomposition is then checked against a real delivery. Per-operation costs and the
attempt mix predict the handler time of a full run, and the prediction is compared with
the time that run actually took. Parts that cannot reconstruct the whole are not parts.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import psycopg

from retry_amplification.config import DEFAULT_DSN, ScenarioConfig
from retry_amplification.handlers import ensure_schema
from retry_amplification.harness import run_scenario

OUT = Path(__file__).resolve().parent.parent / "docs" / "experiments"
SAMPLES = 3000
INSERT = ("INSERT INTO ra_applied (key) VALUES (%s) "
          "ON CONFLICT (key) DO NOTHING RETURNING key")
UPDATE = "UPDATE ra_account SET balance = balance + 1 WHERE id = 1"
# The decomposition has to survive the noise it was built to dodge, but not by much: it
# is reconstructing a sum of thousands of sub-millisecond operations from three medians.
RECONSTRUCTION_TOLERANCE = 0.20


def p50(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[len(ordered) // 2] if ordered else 0.0


def microbenchmark(dsn: str) -> dict:
    """Time the three operations interleaved, so drift cannot favour one of them."""
    ensure_schema(dsn)
    plain: list[float] = []
    ledgered: list[float] = []
    declined: list[float] = []

    def timed(fn) -> float:
        started = time.perf_counter()
        fn()
        return (time.perf_counter() - started) * 1000.0

    with psycopg.connect(dsn) as conn:
        def apply_plain() -> None:
            with conn.transaction():
                conn.execute(UPDATE)

        def apply_ledgered(key: str) -> None:
            with conn.transaction():
                claimed = conn.execute(INSERT, (key,)).fetchone()
                if claimed is not None:
                    conn.execute(UPDATE)

        for index in range(SAMPLES):
            key = f"bench-{index}"
            plain.append(timed(apply_plain))
            ledgered.append(timed(lambda k=key: apply_ledgered(k)))
            # The same key again: this is the path a redelivery takes.
            declined.append(timed(lambda k=key: apply_ledgered(k)))

    half = SAMPLES // 2
    halves = {
        name: [p50(v[:half]), p50(v[half:])]
        for name, v in (("plain", plain), ("ledgered", ledgered),
                        ("declined", declined))
    }
    overhead_halves = [halves["ledgered"][i] / halves["plain"][i] - 1.0 for i in (0, 1)]
    decline_halves = [halves["declined"][i] / halves["ledgered"][i] for i in (0, 1)]
    return {
        "samples": SAMPLES,
        "plain_apply_ms": round(p50(plain), 4),
        "ledgered_apply_ms": round(p50(ledgered), 4),
        "declined_ms": round(p50(declined), 4),
        "split_half": {name: [round(a, 4), round(b, 4)] for name, (a, b) in halves.items()},
        "overhead_halves": [round(v, 4) for v in overhead_halves],
        "decline_share_halves": [round(v, 4) for v in decline_halves],
        "overhead_drift": round(abs(overhead_halves[0] - overhead_halves[1]), 4),
        "timing_drift": round(
            max(abs(a - b) / max(a, b) for a, b in halves.values()), 4),
    }


def main() -> None:
    bench = microbenchmark(DEFAULT_DSN)
    plain = bench["plain_apply_ms"]
    ledgered = bench["ledgered_apply_ms"]
    declined = bench["declined_ms"]
    overhead = ledgered / plain - 1.0
    decline_share = declined / ledgered

    timing_drift = bench["timing_drift"]
    overhead_drift = bench["overhead_drift"]

    print(f"  plain apply      {plain:7.4f} ms")
    print(f"  ledgered apply   {ledgered:7.4f} ms   ({overhead:+.1%})")
    print(f"  declined apply   {declined:7.4f} ms   "
          f"({decline_share:.3f} of a performed one)")
    print(f"  raw timings drifted {timing_drift:.1%} across the halves, "
          f"all three together")
    print(f"  the overhead itself moved {overhead_drift:.3f}: "
          f"{bench['overhead_halves'][0]:+.1%} then "
          f"{bench['overhead_halves'][1]:+.1%}")
    print()

    # Reconstruct a real run from the three numbers above.
    config = ScenarioConfig(handler="idempotent", ack_loss=0.5, messages=4000,
                            seed=20260219, dsn=DEFAULT_DSN)
    run = run_scenario(config)
    predicted_ms = run.applies * ledgered + run.skipped * declined
    measured_ms = run.wall_seconds * 1000.0
    reconstruction_error = abs(measured_ms - predicted_ms) / predicted_ms

    print(f"  a real run: {run.applies} applications, {run.skipped} declined")
    print(f"  predicted handler time {predicted_ms:8.1f} ms")
    print(f"  measured wall time     {measured_ms:8.1f} ms "
          f"({reconstruction_error:+.1%})")

    payload = {
        "experiment": "e3_what_the_ledger_costs",
        "microbenchmark": bench,
        "apply_overhead": round(overhead, 4),
        "decline_share_of_apply": round(decline_share, 4),
        "timing_drift": timing_drift,
        "overhead_drift": overhead_drift,
        "apparatus_stable": overhead_drift < 0.10,
        "reconstruction": {
            "applies": run.applies, "declined": run.skipped,
            "predicted_ms": round(predicted_ms, 1),
            "measured_ms": round(measured_ms, 1),
            "error": round(reconstruction_error, 4),
            "holds": reconstruction_error < RECONSTRUCTION_TOLERANCE,
        },
        "ledger_rows": run.ledger_rows,
        "ledger_rows_per_message": round(run.ledger_rows / config.messages, 4),
        "attempts": run.stats.attempts,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "e3.json").write_text(json.dumps(payload, indent=2) + "\n")

    print()
    print(f"apparatus stable: {payload['apparatus_stable']}, "
          f"decomposition reconstructs the run: {payload['reconstruction']['holds']}")
    print(f"ledger holds {payload['ledger_rows_per_message']:.3f} rows per message "
          f"while absorbing {run.stats.attempts} attempts")


if __name__ == "__main__":
    main()

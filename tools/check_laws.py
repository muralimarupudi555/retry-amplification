"""Re-derive the series from theory.py and check the recorded measurements against it.

The timings in this repository are not reproducible on another machine, and the attempt
counts are sampled, so neither can be asserted as a fixed value in a test. What can be
asserted is the relationship they have to obey. This script re-computes the geometric
series for every row of every sweep and fails if a recorded measurement has drifted away
from it, which keeps the published numbers checkable on hardware that has never run them.

It is also the check that catches the most embarrassing possible failure: a sweep whose
numbers were edited by hand to look better. Run it against tampered data and it exits 1.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from retry_amplification import theory  # noqa: E402

EXPERIMENTS = ROOT / "docs" / "experiments"
TOLERANCE = theory.AGREEMENT_TOLERANCE


def load(name: str) -> dict:
    path = EXPERIMENTS / name
    if not path.exists():
        raise SystemExit(f"missing {path.relative_to(ROOT)}, run `make bench` first")
    return json.loads(path.read_text())


def check_e1(problems: list[str]) -> None:
    data = load("e1.json")
    cap = data["max_attempts"]
    for row in data["rows"]:
        p = row["ack_loss"]
        predicted = theory.expected_attempts_per_message(p, cap)
        for handler in ("naive", "idempotent"):
            measured = row[f"{handler}_attempts"]
            if not theory.agrees(measured, predicted, TOLERANCE):
                problems.append(
                    f"E1 p={p}: {handler} attempts {measured} is not within "
                    f"{TOLERANCE:.0%} of the series {predicted:.4f}"
                )
        # The identity the repository is named for.
        if not theory.agrees(row["naive_corruption"], row["naive_attempts"], 0.01):
            problems.append(
                f"E1 p={p}: corruption {row['naive_corruption']} and amplification "
                f"{row['naive_attempts']} should be the same number"
            )
        if row["idempotent_balance"] != data["messages"]:
            problems.append(
                f"E1 p={p}: idempotent balance {row['idempotent_balance']} is not the "
                f"message count {data['messages']}"
            )
        if row["ledger_skipped"] != row["overapplied"]:
            problems.append(
                f"E1 p={p}: the ledger declined {row['ledger_skipped']} applications "
                f"but the naive handler overapplied {row['overapplied']}"
            )


def check_e2(problems: list[str]) -> None:
    data = load("e2.json")
    p = data["ack_loss"]
    for row in data["rows"]:
        cap = row["max_attempts"]
        predicted_attempts = theory.expected_attempts_per_message(p, cap)
        if not theory.agrees(row["attempts_per_message"], predicted_attempts, TOLERANCE):
            problems.append(
                f"E2 cap={cap}: attempts {row['attempts_per_message']} is not within "
                f"{TOLERANCE:.0%} of the series {predicted_attempts:.4f}"
            )
        predicted_unacked = theory.predicted_unacknowledged_rate(p, cap)
        # A count, checked against a band whose width comes from the sample size. A flat
        # relative tolerance here fails runs that are behaving perfectly: see ADR-003.
        trials = data["messages"] * data["repeats"]
        observed = row["unacknowledged_count"]
        if not theory.count_agrees(observed, trials, predicted_unacked):
            low, high = theory.binomial_band(trials, predicted_unacked)
            problems.append(
                f"E2 cap={cap}: {observed} unacknowledged out of {trials} is outside "
                f"[{low:.1f}, {high:.1f}], the band the series allows"
            )
    attempts = [r["attempts_per_message"] for r in data["rows"]]
    unacked = [r["unacknowledged_rate"] for r in data["rows"]]
    if attempts != sorted(attempts):
        problems.append("E2: attempts must rise with the cap")
    if unacked != sorted(unacked, reverse=True):
        problems.append("E2: unacknowledged share must fall as the cap rises")


def check_e4(problems: list[str]) -> None:
    data = load("e4.json")
    immediate, backoff, budgeted = data["rows"]
    if immediate["attempts"] != backoff["attempts"]:
        problems.append(
            f"E4: backoff ran {backoff['attempts']} attempts against immediate's "
            f"{immediate['attempts']}; the series has no time in it, so these must match"
        )
    if immediate["overapplied"] != backoff["overapplied"]:
        problems.append("E4: backoff must not change how much is overapplied")
    if budgeted["attempts"] >= immediate["attempts"]:
        problems.append("E4: a budget that does not cut attempts is not a budget")
    if budgeted["unacknowledged"] <= immediate["unacknowledged"]:
        problems.append(
            "E4: a budget cuts attempts by abandoning messages, so its unacknowledged "
            "count has to rise; one that does not is not accounting for what it dropped"
        )


def main() -> int:
    problems: list[str] = []
    check_e1(problems)
    check_e2(problems)
    check_e4(problems)

    if problems:
        print("law check failed:\n", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        print(
            f"\n{len(problems)} problem(s). A recorded measurement no longer obeys the "
            "series it was derived from. Re-run `make bench`, and if the problem "
            "survives, the mechanism changed and the prose needs to change with it.",
            file=sys.stderr,
        )
        return 1

    print("law check passed: every recorded sweep still obeys the geometric series")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

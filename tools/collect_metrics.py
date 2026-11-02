"""Read the experiment outputs and write the single file every document is checked against.

Nothing in this repository quotes a figure that does not pass through here. The anchors
are phrases rather than bare digits, because a checker looking for "3.066" is satisfied by
a sentence that has gone stale around it, and one looking for "5" matches half the page.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPERIMENTS = ROOT / "docs" / "experiments"
OUT = ROOT / "docs" / "metrics.json"

CHECKED_DOCUMENTS = (
    "README.md",
    "docs/adr/ADR-001-an-in-process-broker.md",
    "docs/adr/ADR-002-two-measurements-that-were-wrong.md",
    "docs/adr/ADR-003-the-series-as-the-apparatus-check.md",
    "docs/adr/ADR-004-what-verify-rechecks.md",
    "docs/adr/ADR-005-what-this-cannot-measure.md",
)


def load(name: str) -> dict:
    path = EXPERIMENTS / name
    if not path.exists():
        raise SystemExit(
            f"missing {path.relative_to(ROOT)}. Run `make bench` first: the documents are "
            "checked against measurements, so there is nothing to check until the "
            "measurements exist."
        )
    return json.loads(path.read_text())


def count_tests() -> int:
    out = subprocess.run(
        ["python3", "-m", "pytest", "--collect-only", "-q"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    ).stdout
    for line in reversed(out.splitlines()):
        if "test" in line and "collected" in line:
            return int(line.split()[0])
    return sum(1 for line in out.splitlines() if "::" in line)


def count_commits() -> int:
    out = subprocess.run(["git", "rev-list", "--count", "HEAD"],
                         cwd=ROOT, capture_output=True, text=True, check=False)
    return int(out.stdout.strip() or 0)


def main() -> None:
    e1, e2, e3, e4 = (load(f"e{i}.json") for i in (1, 2, 3, 4))

    e1_worst = max(e1["rows"], key=lambda r: r["naive_corruption"])
    e2_cheapest, e2_dearest = e2["rows"][0], e2["rows"][-1]
    immediate, backoff, budgeted = e4["rows"]

    metrics = {
        "e1_messages": e1["messages"],
        "e1_worst_inflation": e1["worst_inflation"],
        "e1_worst_overapplied": e1["worst_overapplied"],
        "e1_worst_ack_loss": e1_worst["ack_loss"],
        "e1_mid_inflation": next(
            r["naive_corruption"] for r in e1["rows"] if r["ack_loss"] == 0.5),
        "e1_mid_overapplied": next(
            r["overapplied"] for r in e1["rows"] if r["ack_loss"] == 0.5),

        "e2_cheapest_cap": e2_cheapest["max_attempts"],
        "e2_cheapest_unacknowledged": e2_cheapest["unacknowledged_rate"],
        "e2_dearest_cap": e2_dearest["max_attempts"],
        "e2_dearest_overapplied": e2_dearest["overapplied"],
        "e2_dearest_unacknowledged": e2_dearest["unacknowledged_rate"],
        "e2_repeats": e2["repeats"],
        "e2_dearest_unacknowledged_count": e2_dearest["unacknowledged_count"],

        "e3_apply_overhead": e3["apply_overhead"],
        "e3_decline_share": e3["decline_share_of_apply"],
        "e3_overhead_drift": e3["overhead_drift"],
        "e3_reconstruction_error": e3["reconstruction"]["error"],
        "e3_ledger_rows_per_message": e3["ledger_rows_per_message"],
        "e3_attempts_absorbed": e3["attempts"],

        "e4_attempts": immediate["attempts"],
        "e4_backoff_attempts": backoff["attempts"],
        "e4_backoff_slowdown": e4["backoff_slowdown"],
        "e4_budget_attempts": budgeted["attempts"],
        "e4_attempts_saved": e4["attempts_saved_by_budget"],
        "e4_messages_abandoned": e4["messages_abandoned_by_budget"],
        "e4_budget_unacknowledged": budgeted["unacknowledged_rate"],
        "e4_immediate_unacknowledged": immediate["unacknowledged_rate"],

        "tests": count_tests(),
        "commits": count_commits(),
    }

    display = {
        "e1_worst_inflation": f"{metrics['e1_worst_inflation']:.3f}",
        "e1_worst_ack_loss": f"{metrics['e1_worst_ack_loss']:.2f}",
        "e1_mid_inflation": f"{metrics['e1_mid_inflation']:.3f}",
        "e2_cheapest_unacknowledged": f"{metrics['e2_cheapest_unacknowledged']:.1%}",
        "e2_dearest_unacknowledged": f"{metrics['e2_dearest_unacknowledged']:.3%}",
        "e3_apply_overhead": f"{metrics['e3_apply_overhead']:.0%}",
        "e3_decline_share": f"{metrics['e3_decline_share']:.2f}",
        "e3_overhead_drift": f"{metrics['e3_overhead_drift']:.3f}",
        "e3_reconstruction_error": f"{metrics['e3_reconstruction_error']:.1%}",
        "e3_ledger_rows_per_message": f"{metrics['e3_ledger_rows_per_message']:.3f}",
        "e4_backoff_slowdown": f"{metrics['e4_backoff_slowdown']:.2f}",
        "e4_budget_unacknowledged": f"{metrics['e4_budget_unacknowledged']:.1%}",
        "e4_immediate_unacknowledged": f"{metrics['e4_immediate_unacknowledged']:.1%}",
    }
    for key, value in metrics.items():
        display.setdefault(key, str(value))

    anchors = {
        "e1_messages": ["{} messages"],
        "e1_worst_inflation": ["inflates the balance {}x", "{}x"],
        "e1_worst_overapplied": ["{} units that should not exist"],
        "e1_worst_ack_loss": ["{} of acknowledgements lost"],
        "e1_mid_inflation": ["half the acknowledgements lost, {}x"],
        "e1_mid_overapplied": ["{} units of money"],
        "e2_cheapest_cap": ["a cap of {}"],
        "e2_cheapest_unacknowledged": ["{} of messages never acknowledged"],
        "e2_dearest_cap": ["raising it to {}"],
        "e2_dearest_overapplied": ["buys {} units"],
        "e2_dearest_unacknowledged": ["down to {}"],
        "e2_repeats": ["pooled over {} seeds"],
        "e2_dearest_unacknowledged_count": ["{} messages out of"],
        "e3_apply_overhead": ["costs {} on the apply path"],
        "e3_decline_share": ["{} of the cost of performing one"],
        "e3_overhead_drift": ["moved {} between halves"],
        "e3_reconstruction_error": ["reconstructs it to within {}"],
        "e3_ledger_rows_per_message": ["{} rows per message"],
        "e3_attempts_absorbed": ["absorbing {} attempts"],
        "e4_attempts": ["{} attempts"],
        "e4_backoff_attempts": ["the same {} attempts"],
        "e4_backoff_slowdown": ["{}x as long"],
        "e4_budget_attempts": ["down to {} attempts"],
        "e4_attempts_saved": ["removes {} attempts"],
        "e4_messages_abandoned": ["abandoning {} messages"],
        "e4_budget_unacknowledged": ["{} never acknowledged"],
        "e4_immediate_unacknowledged": ["from {} never acknowledged"],
        "tests": ["{} tests"],
        "commits": ["{} commits"],
    }

    OUT.write_text(json.dumps({
        "metrics": metrics, "display": display, "anchors": anchors,
        "checked_documents": list(CHECKED_DOCUMENTS),
    }, indent=2) + "\n")
    print(f"collected {len(metrics)} metrics into {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

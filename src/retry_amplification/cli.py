"""Command line entry point.

Exit code 4 is the one worth having. It does not say the queue is slow or the worker is
unhealthy, both of which a dashboard would already say. It says money moved twice and
nothing anywhere raised an error, which is the failure mode that reaches a customer before
it reaches an engineer.

Exit code 5 protects the rest. The attempt count is a geometric series by construction, so
a run that misses it is not describing the system it claims to, and the tool refuses to
print a corruption figure rather than publishing one.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from retry_amplification.config import HANDLERS, RETRY_POLICIES, ConfigError, ScenarioConfig
from retry_amplification.report import Report, build_report

EXIT_EXACTLY_ONCE = 0
EXIT_EFFECTS_MISSING = 1
EXIT_BAD_CONFIG = 2
EXIT_INTERNAL_ERROR = 3
EXIT_SILENT_DOUBLE_APPLY = 4
EXIT_MEASUREMENT_INVALID = 5


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="retry-amplification",
        description="Measure what at-least-once delivery costs a handler that is "
                    "not idempotent.",
    )
    parser.add_argument("--handler", choices=HANDLERS, default="naive")
    parser.add_argument("--retry-policy", choices=RETRY_POLICIES, default="immediate")
    parser.add_argument("--ack-loss", type=float, default=0.25)
    parser.add_argument("--handler-failure", type=float, default=0.0)
    parser.add_argument("--messages", type=int, default=2000)
    parser.add_argument("--max-attempts", type=int, default=5)
    parser.add_argument("--retry-budget", type=int, default=0)
    parser.add_argument("--backoff-base-ms", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=20260219)
    parser.add_argument("--dsn", default=None)
    parser.add_argument("--json", action="store_true")
    return parser


def classify(report: Report) -> int:
    if not report.measurement_valid:
        return EXIT_MEASUREMENT_INVALID
    if report.silent_double_apply:
        return EXIT_SILENT_DOUBLE_APPLY
    if report.unapplied:
        return EXIT_EFFECTS_MISSING
    return EXIT_EXACTLY_ONCE


def render(report: Report) -> str:
    config, result = report.config, report.result
    lines = [
        f"{config.handler} handler, {config.retry_policy} retries, "
        f"{config.messages} messages, {config.ack_loss:.0%} of acks lost, "
        f"up to {config.max_attempts} attempts",
        "",
        f"{'reading':<32}{'measured':>12}{'predicted':>12}",
        "-" * 56,
        f"{'attempts per message':<32}{result.amplification:>12.3f}"
        f"{report.predicted_amplification:>12.3f}",
        f"{'applications per message':<32}{result.corruption:>12.3f}"
        f"{report.predicted_corruption:>12.3f}",
        f"{'never acknowledged':<32}{result.stats.unacknowledged_rate:>12.4f}"
        f"{report.predicted_unacknowledged:>12.4f}",
        "-" * 56,
        f"{'balance expected':<32}{config.messages:>12}",
        f"{'balance found':<32}{result.final_balance:>12}",
        f"{'units that should not exist':<32}{result.overapplied:>12}",
        f"{'median attempt':<32}{result.attempt_p50_ms:>11.3f} ms",
        f"{'p99 attempt':<32}{result.attempt_p99_ms:>11.3f} ms",
    ]
    if config.handler == "idempotent":
        lines.append(f"{'ledger rows written':<32}{result.ledger_rows:>12}")
        lines.append(f"{'applications skipped by ledger':<32}{result.skipped:>12}")

    if report.silent_double_apply:
        lines += [
            "",
            f"{result.overapplied} units of money exist that should not. No attempt "
            "raised an error, no delivery was dropped, and every component reported "
            "success.",
            f"Attempts were amplified {result.amplification:.3f}x and every one of them "
            "applied, because the handler keeps no record of what it has already done.",
        ]
    if report.unapplied:
        lines += [
            "",
            f"{-result.overapplied} messages never applied at all: the attempt cap was "
            "reached while the handler was still failing.",
        ]
    if not report.measurement_valid:
        lines += [
            "",
            f"measured amplification {result.amplification:.3f} does not match the "
            f"series prediction {report.predicted_amplification:.3f}: this run is not "
            "describing the system it claims to and its corruption figure should not "
            "be used",
        ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        fields = dict(
            handler=args.handler, retry_policy=args.retry_policy, ack_loss=args.ack_loss,
            handler_failure=args.handler_failure, messages=args.messages,
            max_attempts=args.max_attempts, retry_budget=args.retry_budget,
            backoff_base_ms=args.backoff_base_ms, seed=args.seed,
        )
        if args.dsn:
            fields["dsn"] = args.dsn
        config = ScenarioConfig(**fields)
    except ConfigError as exc:
        print(f"invalid scenario: {exc}", file=sys.stderr)
        return EXIT_BAD_CONFIG

    try:
        report = build_report(config)
    except Exception as exc:  # noqa: BLE001
        print(f"measurement failed to complete: {exc}", file=sys.stderr)
        return EXIT_INTERNAL_ERROR

    print(json.dumps(report.as_dict(), indent=2) if args.json else render(report))
    return classify(report)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

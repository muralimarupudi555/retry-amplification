"""Turn a run into a verdict, and check the apparatus while doing it.

Every report re-derives the two predictions from theory.py and compares them to what was
measured. A run whose amplification disagrees with the series is not a system behaving
surprisingly; it is a harness that is not doing what it says, and the report says so
rather than publishing a corruption figure nobody should trust.
"""

from __future__ import annotations

from dataclasses import dataclass

from retry_amplification import theory
from retry_amplification.config import ScenarioConfig
from retry_amplification.harness import RunResult


@dataclass(frozen=True)
class Report:
    """One scenario, its predictions, and whether they were met."""

    result: RunResult

    @property
    def config(self) -> ScenarioConfig:
        return self.result.config

    @property
    def predicted_amplification(self) -> float:
        return theory.predicted_amplification(self.config)

    @property
    def predicted_corruption(self) -> float:
        return theory.predicted_corruption(self.config)

    @property
    def predicted_unacknowledged(self) -> float:
        return theory.predicted_unacknowledged_rate(
            self.config.ack_loss, self.config.max_attempts, self.config.handler_failure
        )

    @property
    def amplification_agrees(self) -> bool:
        return theory.agrees(self.result.amplification, self.predicted_amplification)

    @property
    def corruption_agrees(self) -> bool:
        return theory.agrees(self.result.corruption, self.predicted_corruption)

    @property
    def measurement_valid(self) -> bool:
        """The broker's own counting must match the series it was built from.

        This is checked before any corruption claim is made. A budgeted policy stops early
        by design, so its attempt count is expected to fall short of the series and is
        exempt; its corruption claim rests on the balance alone.
        """
        if self.config.retry_policy == "budgeted":
            return True
        return self.amplification_agrees

    @property
    def silent_double_apply(self) -> bool:
        return self.result.overapplied > 0

    @property
    def unapplied(self) -> bool:
        return self.result.overapplied < 0

    @property
    def ledger_cost_share(self) -> float:
        """Share of the ledger table that exists only because of retries."""
        rows = self.result.ledger_rows
        return 0.0 if rows == 0 else 1.0 - (self.config.messages / rows)

    def as_dict(self) -> dict:
        return {
            **self.result.as_dict(),
            "predicted_amplification": round(self.predicted_amplification, 4),
            "predicted_corruption": round(self.predicted_corruption, 4),
            "predicted_unacknowledged_rate": round(self.predicted_unacknowledged, 4),
            "amplification_agrees": self.amplification_agrees,
            "corruption_agrees": self.corruption_agrees,
            "measurement_valid": self.measurement_valid,
            "silent_double_apply": self.silent_double_apply,
        }


def build_report(config: ScenarioConfig) -> Report:
    from retry_amplification.harness import run_scenario

    return Report(result=run_scenario(config))

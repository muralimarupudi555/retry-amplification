"""Exit codes, because they are the interface a pipeline actually uses."""

from __future__ import annotations

import json

import pytest

from retry_amplification.cli import (
    EXIT_BAD_CONFIG,
    EXIT_EFFECTS_MISSING,
    EXIT_EXACTLY_ONCE,
    EXIT_SILENT_DOUBLE_APPLY,
    main,
)


def test_an_idempotent_run_exits_zero(dsn, capsys):
    code = main(["--handler", "idempotent", "--ack-loss", "0.5",
                 "--messages", "1000", "--dsn", dsn])
    assert code == EXIT_EXACTLY_ONCE
    assert "units that should not exist" in capsys.readouterr().out


def test_a_naive_lossy_run_exits_four(dsn, capsys):
    code = main(["--handler", "naive", "--ack-loss", "0.5",
                 "--messages", "1000", "--dsn", dsn])
    assert code == EXIT_SILENT_DOUBLE_APPLY
    assert "should not" in capsys.readouterr().out


def test_a_naive_lossless_run_exits_zero(dsn):
    assert main(["--handler", "naive", "--ack-loss", "0.0",
                 "--messages", "1000", "--dsn", dsn]) == EXIT_EXACTLY_ONCE


def test_effects_missing_exits_one(dsn):
    code = main(["--ack-loss", "0.0", "--handler-failure", "0.6",
                 "--max-attempts", "2", "--messages", "1000", "--dsn", dsn])
    assert code == EXIT_EFFECTS_MISSING


def test_a_bad_scenario_exits_two(dsn, capsys):
    assert main(["--ack-loss", "1.0", "--dsn", dsn]) == EXIT_BAD_CONFIG
    assert "invalid scenario" in capsys.readouterr().err


def test_a_tiny_batch_exits_two(dsn):
    assert main(["--messages", "10", "--dsn", dsn]) == EXIT_BAD_CONFIG


def test_json_output_parses(dsn, capsys):
    main(["--handler", "idempotent", "--messages", "500", "--json", "--dsn", dsn])
    payload = json.loads(capsys.readouterr().out)
    assert payload["exactly_once"] is True
    assert payload["config"]["handler"] == "idempotent"


def test_the_report_names_the_number_of_units_that_should_not_exist(dsn, capsys):
    main(["--handler", "naive", "--ack-loss", "0.5", "--messages", "1000", "--dsn", dsn])
    out = capsys.readouterr().out
    assert "units of money exist that should not" in out


def test_an_unreachable_database_exits_three(capsys):
    code = main(["--messages", "500", "--dsn",
                 "postgresql://postgres@127.0.0.1:1/postgres"])
    assert code == 3
    assert "failed to complete" in capsys.readouterr().err


@pytest.mark.parametrize("policy", ["immediate", "exponential_backoff"])
def test_both_free_policies_run(dsn, policy):
    code = main(["--retry-policy", policy, "--handler", "idempotent",
                 "--ack-loss", "0.3", "--messages", "500",
                 "--backoff-base-ms", "0.1", "--dsn", dsn])
    assert code == EXIT_EXACTLY_ONCE

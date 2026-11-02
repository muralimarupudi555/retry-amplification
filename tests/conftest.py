"""Shared fixtures.

Tests that need a database take `dsn`. There is no skip-if-unavailable guard: a test suite
that quietly passes with half its tests skipped is worse than one that fails, because the
green tick means something different from one machine to the next. `docker compose up -d`
or the CI service container is a precondition, and the failure says so.
"""

from __future__ import annotations

import pytest

from retry_amplification.config import DEFAULT_DSN, ScenarioConfig
from retry_amplification.handlers import ensure_schema


@pytest.fixture(scope="session")
def dsn() -> str:
    return DEFAULT_DSN


@pytest.fixture
def clean_db(dsn: str) -> str:
    ensure_schema(dsn)
    return dsn


@pytest.fixture
def small(dsn: str) -> ScenarioConfig:
    """A scenario small enough to run in a test and large enough to mean something."""
    return ScenarioConfig(messages=500, ack_loss=0.25, seed=7, dsn=dsn)

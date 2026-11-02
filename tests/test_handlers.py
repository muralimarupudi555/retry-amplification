"""The two handlers, against a real database.

The ledger's behaviour is a property of PostgreSQL's unique index, not of the Python
around it, so these run against the real thing. A fake that returns what the code expects
would prove nothing about the mechanism being relied on.
"""

from __future__ import annotations

import psycopg
import pytest

from retry_amplification.broker import HandlerFailed
from retry_amplification.handlers import Handler, ledger_size, read_balance


@pytest.fixture
def conn(clean_db: str):
    with psycopg.connect(clean_db) as connection:
        yield connection


def test_a_clean_database_starts_at_zero(clean_db: str):
    assert read_balance(clean_db) == 0
    assert ledger_size(clean_db) == 0


def test_the_naive_handler_applies_every_time(conn, clean_db: str):
    handler = Handler(conn=conn, idempotent=False)
    for _ in range(4):
        handler("same-key", 1)
    assert read_balance(clean_db) == 4
    assert handler.applies == 4


def test_the_idempotent_handler_applies_once_per_key(conn, clean_db: str):
    handler = Handler(conn=conn, idempotent=True)
    for attempt in range(1, 5):
        handler("same-key", attempt)
    assert read_balance(clean_db) == 1
    assert handler.applies == 1
    assert handler.skipped == 3


def test_the_idempotent_handler_still_applies_different_keys(conn, clean_db: str):
    handler = Handler(conn=conn, idempotent=True)
    for index in range(5):
        handler(f"key-{index}", 1)
    assert read_balance(clean_db) == 5
    assert ledger_size(clean_db) == 5


def test_the_ledger_records_one_row_per_key_not_per_attempt(conn, clean_db: str):
    handler = Handler(conn=conn, idempotent=True)
    for _ in range(10):
        handler("k", 1)
    assert ledger_size(clean_db) == 1


def test_a_failing_handler_raises_before_applying(conn, clean_db: str):
    handler = Handler(conn=conn, idempotent=False, handler_failure=1.0, seed=3)
    with pytest.raises(HandlerFailed):
        handler("k", 1)
    assert read_balance(clean_db) == 0


def test_a_failing_idempotent_handler_leaves_no_ledger_row(conn, clean_db: str):
    """The key must not be claimed by an attempt whose effect never landed.

    If it were, the retry would find the key present, skip the work, and the effect
    would never happen. That is a worse bug than the double apply, because nothing
    downstream ever raises.
    """
    handler = Handler(conn=conn, idempotent=True, handler_failure=1.0, seed=3)
    with pytest.raises(HandlerFailed):
        handler("k", 1)
    assert ledger_size(clean_db) == 0
    assert read_balance(clean_db) == 0


def test_the_ledger_and_the_balance_move_together(conn, clean_db: str):
    handler = Handler(conn=conn, idempotent=True)
    for index in range(20):
        handler(f"k{index}", 1)
        handler(f"k{index}", 2)
    assert ledger_size(clean_db) == read_balance(clean_db) == 20


def test_handler_failure_is_seeded_and_reproducible(conn):
    first = Handler(conn=conn, idempotent=False, handler_failure=0.5, seed=11)
    second = Handler(conn=conn, idempotent=False, handler_failure=0.5, seed=11)

    def outcomes(handler):
        results = []
        for index in range(30):
            try:
                handler(f"seeded-{index}", 1)
            except HandlerFailed:
                results.append(False)
            else:
                results.append(True)
        return results

    assert outcomes(first) == outcomes(second)

"""Two handlers for the same job, differing only in whether they remember.

The job is the smallest thing a payments system does: move an amount into an account. The
naive handler moves it. The idempotent handler writes the message's key into a ledger
first and moves the amount only if that write was the one that created the row.

The ledger insert and the balance update share a transaction. Without that, a crash
between them produces exactly the bug the ledger was added to prevent, and in the worse
direction: the key is recorded, so the retry is skipped, and the effect never lands at
all. Silent double-application is bad; silent non-application is worse, because nothing
downstream ever notices.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

import psycopg

from retry_amplification.broker import HandlerFailed

SCHEMA = """
DROP TABLE IF EXISTS ra_applied;
DROP TABLE IF EXISTS ra_account;
CREATE TABLE ra_account (id int PRIMARY KEY, balance bigint NOT NULL DEFAULT 0);
CREATE TABLE ra_applied (
    key text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO ra_account (id, balance) VALUES (1, 0);
"""


def ensure_schema(dsn: str) -> None:
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(SCHEMA)


def read_balance(dsn: str) -> int:
    with psycopg.connect(dsn, autocommit=True) as conn:
        row = conn.execute("SELECT balance FROM ra_account WHERE id = 1").fetchone()
    return int(row[0]) if row else 0


def ledger_size(dsn: str) -> int:
    with psycopg.connect(dsn, autocommit=True) as conn:
        row = conn.execute("SELECT count(*) FROM ra_applied").fetchone()
    return int(row[0]) if row else 0


@dataclass
class Handler:
    """Applies one unit per message, with or without a memory of having done so."""

    conn: psycopg.Connection
    idempotent: bool
    handler_failure: float = 0.0
    seed: int = 0
    applies: int = 0
    skipped: int = 0

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed + 977)

    def __call__(self, message_id: str, attempt: int) -> None:
        if self.handler_failure > 0 and self._rng.random() < self.handler_failure:
            # Failure before the effect. This is the retry a retry policy is actually for,
            # and it is the only one that costs nothing but a round trip.
            raise HandlerFailed(message_id)

        if self.idempotent:
            self._apply_once(message_id)
        else:
            self._apply(message_id)

    def _apply(self, message_id: str) -> None:
        with self.conn.transaction():
            self.conn.execute("UPDATE ra_account SET balance = balance + 1 WHERE id = 1")
        self.applies += 1

    def _apply_once(self, message_id: str) -> None:
        """Claim the key and move the money in one transaction, or do neither.

        ON CONFLICT DO NOTHING with RETURNING is the whole mechanism: the row comes back
        only to the insert that created it, so exactly one attempt per key reaches the
        update, and the database decides which one rather than the application.
        """
        with self.conn.transaction():
            claimed = self.conn.execute(
                "INSERT INTO ra_applied (key) VALUES (%s) "
                "ON CONFLICT (key) DO NOTHING RETURNING key",
                (message_id,),
            ).fetchone()
            if claimed is None:
                self.skipped += 1
                return
            self.conn.execute("UPDATE ra_account SET balance = balance + 1 WHERE id = 1")
        self.applies += 1

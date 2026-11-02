# ADR-005: What this cannot measure

**Status.** Accepted. This is the document to read before quoting any figure from here.

## The easy case is the one that was measured

The handler's effect and the ledger live in the same PostgreSQL, so they share a
transaction. That is what makes the ledger airtight: the key is claimed and the money
moves together, or neither happens.

Most real double-apply bugs are not like this. The effect is a charge at a payment
provider, an email through a third party, a webhook to a customer, a write to a different
database. None of those join your transaction, and no amount of local bookkeeping makes
them. The honest versions of this problem need the provider's own idempotency key, or an
outbox, and both change the shape of the solution considerably.

So the measurement here is of the mechanism in its most favourable setting. It says what
at-least-once delivery costs a handler that is not idempotent, and it demonstrates that a
transactional ledger removes that cost. It does not say that a ledger is available to you.

## Independent loss is not how acknowledgements are lost

The model assumes each acknowledgement is lost independently with a fixed probability.
Real loss is correlated: a partition, a rolling restart or a leader election loses a burst
of them together and then none for an hour.

Correlated loss leaves the *mean* amplification roughly alone - the series depends on the
loss rate, not its arrangement in time. What it changes is everything about the tail. The
same mean concentrated into ninety seconds is the difference between a dependency
absorbing an extra third of load and a dependency falling over, and a queue whose depth
was fine on average. Every figure here describes a steady state that a real incident does
not have.

## The attempts are serial

One connection, one message at a time. A real worker pool runs attempts concurrently, and
a redelivery can land on a different worker while the first is still running. The ledger
is designed for that case - the unique index decides the winner rather than the
application - but designed for is not measured in. Write contention on hot keys, lock
waits, and the behaviour of two workers racing on the same row are all absent.

This is the largest gap, and it is where the next version of this repository goes.

## The ledger grows forever and this does not prune it

It holds **1.000 rows per message** while **absorbing 7699 attempts**, which is the good
news: storage scales with traffic, not with failure.

The bad news is not measured here at all. A ledger has to be pruned, and the retention
window has to outlast the longest redelivery the broker can produce - including a message
stuck in a dead-letter queue that someone replays next week. Prune to a window shorter
than that and the hole reopens silently, in exactly the circumstances the ledger exists
for, with no error anywhere. The failure looks identical to having no ledger at all.

## The clocks

Wall-clock figures are handler time. There is no broker and no network in them, so nothing
here should be read as end-to-end latency. E4's slowdown is a ratio between two policies
measured the same way, which survives the omission; E3's absolute milliseconds do not
travel off this machine and are reported as ratios for that reason.

## The cap is not the end of the message

When a message exhausts its attempt cap here, the harness stops. A real broker returns it
to the queue after the visibility timeout and delivers it again, possibly for days. So
**49.6% of messages never acknowledged** at the lowest cap is not a measurement of
messages lost. It is a measurement of work that already happened, is about to happen
again, and is outside the window this harness watches. Lowering the cap moves corruption
out of the measurement, not out of the system.

## What is left standing

The series, the identity between amplification and corruption for a handler with no
memory, the fact that a ledger changes what an attempt does and not how many there are,
and the fact that backoff reschedules attempts rather than removing them. Those are
properties of the arithmetic and they survive every gap above.

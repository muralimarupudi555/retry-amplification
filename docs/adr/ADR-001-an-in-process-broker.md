# ADR-001: An in-process broker, and why that is enough

**Status.** Accepted.

## The decision

Delivery is simulated by about eighty lines in `src/retry_amplification/broker.py` rather
than by Kafka, SQS or RabbitMQ. The handler and its ledger run against a real PostgreSQL.

The split is deliberate and it is not a convenience. One half of this system is being
measured and the other half is being *supplied*, and they are not the same half.

## What is actually under test

The claim is about what a handler does when the same message arrives twice. Everything
upstream of that is a mechanism for producing a second arrival. A real broker produces one
through a visibility timeout, a consumer group rebalance, a network partition, or an
operator replaying a dead-letter queue. Each of those is a different story and all of them
end at the same place: the handler sees a message it has already seen.

So the broker here does the one thing the experiments need. It delivers, it watches for an
acknowledgement, and it delivers again if one does not arrive. The loss is injected after
the handler returns, which is the entire point of the exercise - a message whose
acknowledgement was lost has already done its work, and nothing downstream can tell that
apart from a message that was never processed.

## What a real broker would have cost

An acknowledgement loss rate of `0.5` is not a setting any broker exposes. Getting one out
of real infrastructure means a fault injector, a proxy that drops packets, or a long wait
for a rare event, and every one of those adds a second thing that can be wrong. When the
corruption figure came out strange it would not be clear whether the handler misbehaved or
the fault injector did.

Here the loss rate is an argument. The sweep in E1 runs seven of them in a few minutes,
and each one is exactly the number it says it is.

## What is given up

Three things, and they are named again in ADR-005 because they bound what the numbers
mean.

Ordering, partitioning and consumer-group semantics are absent. A real redelivery can
arrive on a different worker, which is the case the ledger has to survive and which this
harness never produces. The ledger survives it because PostgreSQL's unique index decides
the winner, not the application - but that is an argument, not a measurement.

Network and broker latency are absent, so the wall-clock figures in E3 and E4 are handler
time rather than end-to-end time. E4's ratio survives this, because both policies pay the
same missing latency.

The attempts are serial. A real worker pool would run them concurrently, and the ledger
would then face genuine write contention on the same key. That is a real gap and it is
where the next version of this repository should go.

## Why the database is real

The ledger's correctness is a property of `INSERT ... ON CONFLICT DO NOTHING RETURNING`
and the unique index under it. That is the mechanism being relied on, so it is the
mechanism being exercised. A dictionary with a lock around it would pass every test here
and tell the reader nothing about whether the technique works.

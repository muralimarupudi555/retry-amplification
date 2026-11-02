# ADR-002: Two measurements that were wrong, and what they were replaced with

**Status.** Accepted. Both errors are preserved here because the corrections are the most
useful thing in the repository.

## The first: a median over two different operations

E3 asks what the idempotency ledger costs. The first version answered it by running both
handlers and comparing the median time per attempt.

The numbers came back saying the ledger's overhead fell from `+24%` at no acknowledgement
loss to `+2%` at half - that the ledger got *cheaper* the more work it was doing. That is
not a surprising result, it is an impossible one, and the only honest response to an
impossible result is to assume the instrument is broken.

It was. The idempotent handler has two paths with very different costs. Performing an
application does an insert and an update. Declining one does an insert that conflicts and
stops, which costs **0.33 of the cost of performing one**. As the loss rate climbs,
declines come to dominate the attempt mix, so a median taken over all attempts drifts
towards the cheaper path. The median was tracking the mix, not the cost.

The paths are timed separately now, in `handlers.py`, and the mix is reported beside them.

## The second: a difference smaller than the noise around it

Separating the paths produced an overhead that still would not sit still: six paired runs
of four thousand messages gave figures between `+6%` and `+52%`. The difference being
measured is about a seventh of a millisecond, and the run-to-run drift of a two-core
container with a live database is the same size.

Averaging more runs was the obvious fix and the wrong one, because the drift is not
independent between runs - the machine gets slower and faster in stretches, so more
samples of the same stretch buy nothing.

The measurement moved down a level instead. The three operations are now timed inside one
connection with the iterations interleaved, so a slow stretch lands on all three equally.
The ledger **costs 30% on the apply path**.

### The check that goes with it

Pairing is a claim that the *ratio* holds still even when the timings do not, and that
claim has to be tested rather than assumed. E3 splits its samples in half and reports both
halves. The raw timings do drift across them - including the plain update that never
touches the ledger table, which is how you can tell the drift is the machine rather than
the mechanism. The overhead itself **moved 0.039 between halves**, and the experiment
fails if it moves by more than `0.10`.

### The check that goes beyond it

Three medians that cannot reconstruct a real run are three medians of nothing. E3 predicts
the handler time of a full delivery from its per-operation costs and the measured attempt
mix, and **reconstructs it to within 5.0%**.

## What both have in common

Neither was caught by a test. Both were caught by a number that was the wrong shape - an
overhead that fell as the work rose, and a figure that would not repeat. Tests check the
things you thought of. Looking at a result and asking whether it could possibly be true is
what catches the rest.

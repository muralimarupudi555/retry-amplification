# ADR-003: The series is the apparatus check, and its tolerance comes from the sample size

**Status.** Accepted.

## The decision

`theory.py` is written before any measurement and is never fitted to one. Every experiment
re-derives its prediction from it and compares, and `tools/check_laws.py` repeats that
comparison against the committed results on every `make verify`.

This gives the repository something that survives leaving the machine it was measured on.
Timings do not travel - a reader's laptop will produce different milliseconds and should.
The relationship between acknowledgement loss, attempt count and application count is
arithmetic, and it holds anywhere.

## Why the series comes first

An attempt count fitted to data is a curve fit, and a curve fit through a handful of
points agrees with almost anything. A series derived from a stated model of the failure -
an acknowledgement lost independently with probability `p`, a handler that fails before
its effect with probability `f`, a cap of `R` - makes a prediction that can be wrong. E1
through E4 are attempts to make it wrong.

It also forces the model's assumptions into the open. Independence is the big one: real
acknowledgement loss arrives in correlated bursts during a partition, not as independent
coin flips, and ADR-005 says what that does to these numbers.

## The tolerance, and the version of it that was wrong

The first law check compared every measured quantity to its prediction with a flat
relative tolerance. That works for the attempt count, which is an average over thousands
of messages and lands within a few percent every time.

It fails badly for the unacknowledged share. At a cap of eight the series predicts about
sixteen unacknowledged messages in four thousand, and the standard deviation of that count
is four. A run behaving exactly as the model says lands anywhere between eight and
twenty-four - a fifty percent relative error that means nothing at all. The check duly
failed on a seed that was perfectly correct.

Before changing anything, the broker was run across forty seeds to establish it was not
actually biased. It was not: the pooled rate matched the series to within two percent at
every cap. The failing seed was a `+3.4` standard deviation sample and nothing more.

Two things changed as a result.

**The experiment pools.** E2's unacknowledged counts are **pooled over 5 seeds**, because
one sample of a rare event is an estimate whose spread is a quarter of its own size.

**The check uses a band, not a percentage.** `theory.binomial_band` returns the interval a
count should fall in, with a width built from the sample size and the rate. Rare events
get a wide band, common events get a narrow one, and both are checked at the same
confidence.

The band is four standard deviations wide. Not for elegance: with six rare-event checks on
every verify, a three-sigma band fails a correct build often enough that people learn to
re-run it, and a check people re-run until it passes is not a check.

## The irony, recorded deliberately

This repository's own configuration refuses a batch under five hundred messages on the
grounds that a rate needs a sample behind it. The first law check then compared a count of
sixteen against a flat percentage. Knowing the principle and applying it in one place is
not the same as applying it everywhere, which is the argument for having a check that runs
without being asked.

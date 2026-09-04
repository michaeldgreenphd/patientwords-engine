# Handoff: trace-chain pace revision (2026-07-24, overnight session)

For the 13:00 UTC Routine cycle — fold into the digest and `decisions_pending`.

## What happened

Neuronpedia began sustained 429 throttling of hosted graph generation at
2026-07-23 ~21:50 UTC. Since then every circuit-trace window (the workflow's
~70-minute trace-step timeout) completes only **~20 traces** — ~4 dialect
baselines or ~10 2panel pairs — versus 30-50 before. Runs die by timeout or
429-retry exhaustion; every window's partials commit cleanly, the overnight
session chains continuations (~85-minute check-ins), nothing is lost. The
jlens lane is deliberately held idle until the trace backfill completes:
cross-lane concurrency against the hosted API is what triggered the first
429 cascade.

## Coverage as of 05:55 UTC Friday

- Floor `dialects_20260723T001434Z`: baselines 1-17 + 26-30 landed; 18-25
  fired (pending); 31-50 to chain (~28 baselines ≈ 7 windows remaining).
- `pairs_20260714T135150Z`: 1-50 landed; 51-100 running.
- Untouched: `pairs_20260715T132350Z` (11), `pairs_20260716T133552Z` (8),
  `pairs_20260707T221438Z` (16), stragglers ~27 across ten stems (screening
  check needed before firing 1-pair chunks), and the three 100-pair batches
  `pairs_20260717T132235Z` / `20260718T133020Z` / `20260719T132706Z`.

## Revised weekend expectation (tell the owner in the digest)

At the throttled pace the FULL backfill (~412 pairs + 28 baselines ≈ 48
windows) completes mid-next-week, not Saturday. Revised plan, no owner
action needed:

1. Floor + `135150Z` + mid-batches + stragglers complete by ~Saturday.
2. `17T/18T/19T` batches absorb every remaining window through Sunday
   (~150-200 of their 300 pairs at current pace; faster if throttling lifts).
3. **Sunday full republish ships as promised** with everything landed, the
   un-traced tail disclosed as pending rows (the site's em-dash states).
4. The nightly cycle auto-republishes as the tail lands Mon-Tue; lens
   backfill resumes after the trace lane clears.

## Discipline notes for the cycle

- Two circuit-trace entries are typically active (one running + one pending,
  chained with `--ignore-settle` on Actions-confirmed-terminal basis each
  time — basis recorded in every journal note).
- Overnight fires used `--no-git` + dashboard revert; earlier fires on
  2026-07-23 went through fire_trigger's own git publish (queue-view-only
  dashboard writes) — disclose in the cycle per the standing flag.
- Everything in the queue is $0. No paid fires planned.

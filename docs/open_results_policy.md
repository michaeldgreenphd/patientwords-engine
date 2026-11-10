# Open-results policy

In force from 2026-11-10 (owner direction of that date). This is the current rule for
what the project shares and what its analyses read. It replaces the publication hold
of 2026-10-09 and 2026-11-08; the hold's records stay where they are as history
([History](#history)). The code is `scripts/results_policy.py`; the declared metadata
is `data/results_policy/policy.v1.json`. Paths are relative to the engine root.

## The rule

A result is shared when its artifact is intact and no named restriction applies. It
does not have to be confirmatory, clinically reviewed, statistically significant or
favourable to the hypothesis. Whether a result enters a statistic is a different
decision, taken by a named membership rule and recorded in a versioned snapshot.

Six facts are decided independently for every `trace_out/<stem>[__<suffix>]/batch_summary*.json` part:

| Fact | Values | Decided from |
|---|---|---|
| Execution state | `completed`, `partial`, `empty`, `completion_not_recorded`, `unreadable` | the part's own `completed`, `_partial` and `results` |
| Artifact integrity | `recorded_match`, `unrecorded`, `changed_since_recorded`, `malformed`, `unreadable` | bytes against any recorded sha256 (the study pin and the append-only ledger) |
| Evidence class | `registered_cohort`, `exploratory_post_registration`, `exploratory_hand_authored`, `exploratory_third_party_source`, `unclassified` | the stimulus class and the model cohort declared in the policy file |
| Clinical review | `domain_review_pending`, `owner_read_equivalence_and_domain_review_pending` | the stimulus class |
| Visibility | `public`, or `restricted` with a named reason | integrity and the restrictions below; the Tier B seal per row |
| Analysis membership | eligible or not, with the reason, for each membership | the membership rules below |

A completed run with a zero or opposite-direction effect is a completed result. A part
that is absent from a manifest is not defective; it is only outside the membership that
pins that manifest. Missing provenance is recorded as missing.

## Memberships

| Membership | Purpose | Admits |
|---|---|---|
| `study-interim/1` (default) | analysis | Every stimulus family except the hand-authored sets (generated study batches, sentinels, translation arms, curated subsets); every declared model cohort except the 2026-10-09 additions; hosted and activation-patching parts as they are; a CPU-logits part only when `data/publication_release/logits_parts.json` lists the sha256 of its bytes. This is the rule the collectors applied from 2026-10-09, so the published statistics keep their inputs. Each collector then keeps the families it analyses (`paired_stats_rigor.py`, for example, keeps generated study batches only). |
| `exploratory-open/1` | analysis | Every intact part of every declared model cohort on the same stimulus families, no pin. A separately declared exploratory analysis with its own multiple-testing family. Its outputs go to their own files and replace nothing. |
| `public-display/1` | display | Every intact part with no named restriction, hand-authored sets included. The results catalogue reads with this rule. |

Hand-authored sets (`agscen_`) are in no analysis membership: they are examples with
equivalence and domain review pending.

Two refusals hold in every membership, the default one included. A part whose bytes differ
from a recorded sha256 (the pin or the ledger) is not read. A part whose own `graph_model`
names a model that no cohort declares is listed in the catalogue and enters no analysis, so
a new model cannot join a statistic by landing. The second refusal is new on 2026-11-10: the
earlier rule only excluded named models. No part on disk that day was affected by either
(the old gate and the default gate agree on all 1,235 parts).

`Gate(root)` uses the default membership. `Gate(root, membership=...)` selects another.
Every collector counts and prints each part it did not read, by reason; the collector and
the gallery exporter also print the membership and policy version in force. `scripts/publication_hold.py` remains as the import path older callers
use; it holds no rule.

## What stays restricted

Each restriction has a reason, a responsible role and a release condition in the policy
file. The loader refuses a policy in which one is missing.

| Restriction | Scope | Decided by | Released by |
|---|---|---|---|
| Sealed Tier B holdout | row | `scripts/tierb_split.py` `sealed_pair` | the owner's explicit unseal instruction for the endpoint |
| Redistribution-limited text (`pabharvest_`) | stimulus class | the policy file | a recorded licence review |
| Artifact integrity | part | `scripts/results_policy.py` | restoring the recorded bytes, or landing a new part; a recorded hash is never rewritten |
| Uncalibrated clinical mass | field | `scripts/feature_models.py` | a demonstrated calibration |

Private or identifiable material (physician ratings under `data/verification/`, the
private rating app) is outside `trace_out/` and is not read by anything here.

A stimulus family without a row-export entry in the policy (dialect sets, sentinels,
steering runs and others) is listed in the catalogue with counts and hashes and no
rows. That is a scope limit of policy version `open-results/1`, stated in each run's
`rows_reason`; adding a `stimulus_classes` entry in a reviewed pull request lifts it.

## The catalogue and the snapshots

**The results catalogue** (`scripts/export_results_catalogue.py`) is the public record
that changes whenever a run lands. It lists every run directory with the six facts, the
per-run counts of negative, zero and positive effects, partial and empty parts, and
row-level results for the stimulus classes the policy exports. It is not a sample and
selects nothing. Sealed rows are counted and never written. The site publishes it under
`data/results_catalogue/`; the publish chain regenerates it, so a new part becomes
public without anyone approving it individually. With `--record` the exporter appends
the sha256 of each part it reads for the first time to
`data/results_policy/part_ledger.v1.json`, under a lock so overlapping exports cannot
drop each other's entries. A part that already differs from its pin is not recorded.
A part whose bytes later differ from its
record is refused by every membership and listed as `changed_since_recorded`. The ledger
cannot show a change made before a part was first recorded; git history is the record for
that.

**Analysis snapshots** (`scripts/results_snapshot.py`, files under
`data/analysis_snapshots/`) are immutable once they land. A snapshot fixes one
membership at one commit: every admitted part with its sha256 (hosted parts included),
the policy version, the exclusions with counts, the models and correction families, and
per-model row denominators with rows at sealed pairs excluded (the catalogue's
pair-level rule). `create` refuses an existing id, inputs that are not committed
(untracked parts included), and a second snapshot of a membership that does not name
the current one with `--supersedes`. A correction or an extension is a new id that says
what changed. Snapshots read the committed policy file whatever `PW_RESULTS_POLICY`
says.

A snapshot records the published statistics files as they stood: the sha256 of each,
and the generation time and engine commit the file states for itself. It does not
recompute them and does not claim they reproduce from its parts. Two reasons they may
not: a statistics file can predate a part, and the collector also takes rows from the
site's gallery payload (recorded as `inputs.site_payload`). `--recomputed-statistics`
records a field-by-field comparison with a file the operator has just recomputed.

`verify` exits 1 when a recorded part is missing or has different bytes, when a
snapshot file changed or is not in the index, and, for the current snapshot of a
membership, when the membership rule, the pinned manifest or a recorded input file
differs from the record. A superseded snapshot reports those differences without
failing. `tests/test_results_catalogue.py` runs it over every committed snapshot.

## What did not change on 2026-11-10

The published statistics. The default membership reproduces the previous rule: the
collector at the commit before this policy and the collector reading through the policy
module write byte-identical output from the same inputs
([migration record](open_results_migration_20261110.md)).

`analysis_pin` in the policy file states the one remaining control and its release
condition: statistics change only through a versioned snapshot. `auto_advance` is
false, so the Routine does not advance the study pin. Advancing it is
`scripts/publication_release.py --release` (optionally `--models`), followed by a new
snapshot in the same change. A scoped advance only adds entries. No advance rewrites a
recorded hash: if a pinned or ledger-recorded part's committed bytes differ, the command
refuses. Setting `auto_advance` to true, or changing
`default_membership`, is a one-line reviewed edit; the migration record shows what the
statistics would become.

## Preview route

`PW_RESULTS_POLICY=/path/to/candidate.json` makes every collector read a candidate
policy file. Every process that loads the policy while the variable is set writes one line
naming that file to stderr, from the loader itself, so no collector can read a candidate
policy silently. It is for offline previews and tests. The pin advance and the snapshot
tool ignore it and read the committed policy.
`scripts/open_results_migration.py` uses it to compute the comparison in a temporary
directory.

## Adding things

- A model: its results are visible in the catalogue at the next publish whether or not it
  is declared. It joins a statistic only after it is added to a cohort in the policy file
  and a membership admits that cohort; until then every analysis gate skips it and says so.
- A stimulus family: add a `stimulus_classes` entry with its evidence class, review
  status and whether rows are exported. `tests/test_results_policy.py` checks the
  entries against the sidecars' own `status` fields.
- A restriction: add it with its reason, responsible role and release condition.
- A collector that pools `trace_out/` parts into a published number: read through
  `Gate` and print its report. `tests/test_publication_hold.py` shows the pattern.

## History

- 2026-10-09: three post-registration models were added and a backfill of the original
  models began. To keep published numbers from moving while parts landed, the
  collectors skipped the three models by name and read a CPU-logits part only when an
  owner-written manifest listed it (`docs/model_matrix.md`,
  `docs/prereg_divergence_log.md`; commits `bc89b50b6`, `65a286920`). The manifest
  listed 409 parts and was not advanced afterwards.
- 2026-11-08: hand-authored `agscen_` pairs were refused by stem in every collector
  (`23d06d701`).
- 2026-11-10: the owner asked for useful exploratory results to be shared promptly, with
  claim eligibility, artifact integrity, data restrictions and visibility kept
  separate. On that day the hold was keeping 284 of 1,235 parts out of everything the
  publish chain wrote: 93 gap-fill parts of six original models, 78 parts of two new
  models, and 113 parts of the hand-authored sets. None was defective.

The benefit the hold was introduced for is kept by the default membership and the
snapshots. Dated briefs, coordination notes and handoffs that describe the hold are
records of their dates and are not rewritten.

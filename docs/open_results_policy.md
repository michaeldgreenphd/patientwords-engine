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
| `study-interim/1` (default) | analysis | Study batches; every model cohort except the 2026-10-09 additions; hosted and activation-patching parts as they are; a CPU-logits part only when `data/publication_release/logits_parts.json` lists the sha256 of its bytes. This is the rule the collectors applied from 2026-10-09, so the published statistics keep their inputs. |
| `exploratory-open/1` | analysis | Every intact part on a study batch, all model cohorts, no pin. A separately declared exploratory analysis with its own multiple-testing family. Its outputs go to their own files and replace nothing. |
| `public-display/1` | display | Every intact part with no named restriction, hand-authored sets included. The results catalogue reads with this rule. |

Hand-authored sets (`agscen_`) are in no analysis membership: they are examples with
equivalence and domain review pending.

`Gate(root)` uses the default membership. `Gate(root, membership=...)` selects another.
A collector prints the membership and policy it used and counts every part it did not
read, by reason. `scripts/publication_hold.py` remains as the import path older callers
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
`data/results_policy/part_ledger.v1.json`. A part whose bytes later differ from its
record is refused everywhere and listed as `changed_since_recorded`.

**Analysis snapshots** (`scripts/results_snapshot.py`, files under
`data/analysis_snapshots/`) are immutable. A snapshot fixes one membership at one
commit: every admitted part with its sha256 (hosted parts included), the policy
version, the exclusions with counts, the models and correction families, per-model row
denominators with sealed rows excluded, and the hashes of the published statistics
files. `create` refuses an existing id. A correction or an extension is a new id that
names what it supersedes and says what changed. `verify` fails when a recorded input is
missing or different.

## What did not change on 2026-11-10

The published statistics. The default membership reproduces the previous rule: the
collector at the commit before this policy and the collector reading through the policy
module write byte-identical output from the same inputs
([migration record](open_results_migration_20261110.md)).

`analysis_pin` in the policy file states the one remaining control and its release
condition: statistics change only through a versioned snapshot. `auto_advance` is
false, so the Routine does not advance the study pin. Advancing it is
`scripts/publication_release.py --release` (optionally `--models`), followed by a new
snapshot in the same change. Setting `auto_advance` to true, or changing
`default_membership`, is a one-line reviewed edit; the migration record shows what the
statistics would become.

## Preview route

`PW_RESULTS_POLICY=/path/to/candidate.json` makes every collector read a candidate
policy file. Each collector prints `policy file overridden: <path>` when it is set, so
an override is visible in the run's output. It is for offline previews and tests.
`scripts/open_results_migration.py` uses it to compute the comparison in a temporary
directory.

## Adding things

- A model: add it to a cohort in the policy file. It is visible in the catalogue at the
  next publish. It joins a statistic only when a membership admits its cohort.
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

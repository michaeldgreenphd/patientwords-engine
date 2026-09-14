# Design note — a portable framework for evaluating clinical AI framing sensitivity

Status: design document, 2026-09-14, owner-commissioned. Nothing here is
implemented beyond the three data contracts under `docs/framework/` and the
test that keeps them consistent (`tests/test_framework_schemas.py`). The
sequence in §7 is the order of implementation; each step is its own pull
request. The framing-dimension registry (§4) is the owner's: this note fixes
its structure and leaves its content to domain expertise.

## 1. What this is for

Health systems are deploying conversational assistants that answer the same
clinical situation for a patient and for a clinician, and the study has shown
that the two framings do not get the same answer. The framework turns that
study into a repeatable evaluation a deploying organisation can run against
any model it is considering or already running, plus a way to bring its own
recorded conversations in and measure the same effect on them. Everything the
study measures today (next-token behaviour, advice urgency tiers, drift over
time) becomes a probe in a catalogue that new interpretability tools join
without changing the rest.

Scope boundary, unchanged from the study: measurement only. Nothing here
produces medical advice.

## 2. What exists, and what each part becomes

Verified against the repository on 2026-09-14.

| Today | In the framework |
|---|---|
| `scripts/advice_eval.py`: build-stimuli, elicit (append-only JSONL, per-record sha256 chain), judge (rubric tiers and flags in `data/advice_rubric.*.json`), analyze | The behavioural layer, unchanged in method, packaged so it runs outside this repository's CI |
| `data/advice_providers.json` registry: nine providers, each an OpenAI-compatible or vendor endpoint with its consumer default, plus `manual_ui` for hand-captured product transcripts (`import-manual-responses`) | The model-environment adapter. Already model-agnostic for text in, text out |
| `scripts/logits_eval.py` (CPU, bfloat16, `HF_IDS`) and the hosted Neuronpedia path for gemma-2-2b; interp-engine float32 as the reference | The mechanistic layer: probes that need weights or a hosted graph service |
| Paired statistics (`paired_stats_rigor.py`, phrase-clustered bootstrap), judge agreement, retrace consistency | The analysis layer, with one required change for transcripts: the bootstrap cluster becomes the conversation, not the stimulus or phrase (§3.1) |
| The drift sentinel (Tue/Fri, `drift_series.json`) | The monitoring pattern for a deployed model |
| `scripts/seal_check.py` (holdout phrases never leave the sealed set) | The pattern for the transcript privacy guard (§5) |
| `docs/advice_multiturn_design.md` (B6, designed, not implemented) | The multi-turn protocol the transcript import needs anyway |

Two things do not exist and are the substance of the work: a transcript
import with a counterfactual step (§3) and the explicit framework of
differences with a probe catalogue (§4).

## 3. Transcript import and the counterfactual step

### 3.1 Why a counterfactual is required

A recorded conversation has one framing. The study's measurement is a
difference between two framings of the same situation, so a transcript alone
cannot yield it. The import therefore does three things per assistant turn:

1. **Judge the turn as it is** with the existing rubric (tier and flags).
   This is the observational reading. It re-elicits nothing from the model
   under test, but the rubric judge is itself a model call: `advice_eval.py`
   resolves a judge provider from the registry, meters its spend, and calls
   it once per unjudged turn. A deployment therefore needs judge credentials
   and a budget for this step, or uses human coding
   (`scripts/advice_human_coding.py`) in its place; the framework reports
   which, and the judge model version, with every tier.
2. **Classify the user turn on each framing dimension** (§4): by rule, by
   judge, or by a human, recorded with method and annotator.
3. **Produce the counterfactual pair**: rewrite the user turn to the other
   value of a dimension (for register, the existing patient-to-clinical
   translation step and its reverse), then re-elicit **both** the original
   turn and the rewritten turn from the same model, in one run, under one
   pinned environment (model version, request settings, system prompt,
   sampling), with the same preceding context, and judge both replies. The
   difference between those two judged replies is the framing effect. The
   captured reply is never one arm of that pair: it was produced at another
   time under settings the capture may not record, so comparing it with a
   fresh counterfactual would confound framing with drift. This is how
   `advice_eval.py`'s `elicit` already works (both arms in one run); the
   captured reply stays the observational reading, and its judged tier
   against the re-elicited original's is reported separately as a drift
   check. "The same model" is a precondition, not an aspiration: a record whose `source.model` is null (a manual or UI capture
   that did not record it) is imported for the observational path only and
   its counterfactual is reported as `not_comparable: model_unidentified`,
   never run against a configured default, which would confound model drift
   with framing. `source.model_version`, when the capture had it, is
   recorded beside the re-elicitation's own version string so a mismatch is
   visible in the pair record.

Step 3 makes each turn a paired measurement in the form the study already
analyses, with one change to the analysis: the unit of clustering. The
existing advice analysis keys cells and bootstrap clusters on a single
stimulus id; turns within one conversation are correlated, so the transcript
analysis keeps `conversation_id` and `turn_id` as separate keys, reports
per-turn effects, and resamples conversations, not turns, in the bootstrap.
Collapsing a conversation to one cell would lose the per-turn effects;
treating turns as independent would narrow the interval. Step 2's
classification also serves the observational analysis across conversations,
as a covariate.

Constraints carried over from the study: the counterfactual rewrite is
recorded in full (input, output, rewriter model version, sha256), the
re-elicitation goes through the same hash-chained archive as every other
elicitation, and a turn that cannot be rewritten (the rewriter refuses, or a
human rejects the rewrite as changing the situation) is recorded as such,
never dropped.

### 3.2 The transcript format

`docs/framework/transcript.schema.json`, draft 0.1, one conversation per
line of a `.jsonl` file. The parts that matter:

- **`deidentification.status`** allows only `deidentified` and `synthetic`.
  There is no `identified` value, so identified material cannot validate
  and the importer refuses it before reading a single turn. For a
  `deidentified` record the schema requires `method`, `reviewed_by` (a role,
  never a name) and `reviewed_utc` to be present, so the audit evidence
  cannot be omitted; they may be null only for `synthetic`.
- **`source`** records the deploying system, product, configured model and
  the exact model version the capture saw, and how it was captured
  (`api_log`, `ui_export`, `manual`). This is the same provenance the elicit
  archive keeps for API calls.
- **`speaker_roles.user_is`** (`patient`, `caregiver`, `clinician`,
  `unknown`) records which side of the study's contrast the conversation
  sits on, for matching across conversations.
- **`turns[]`** are role, text and optional timestamp. Non-text content is
  counted in `attachments_omitted`, never silently dropped.
- **`annotations.framing[]`** holds per-turn classifications keyed on a
  dimension id from the registry, with the method and annotator that made
  them and an optional confidence.
- **`provenance.text_sha256`** is the sha256 of the canonical JSON of
  `turns` (sorted keys, no whitespace, UTF-8, the elicit chain's
  `canonical_json`), so later edits to the text are detectable. The bundled
  example carries its real digest and the test recomputes it.
- `additionalProperties` is false at every level. A field the schema does
  not name cannot ride along, which is how a stray identifier is kept out.

`docs/framework/example_transcript.jsonl` is a synthetic record with
placeholder text; the test validates it against the schema and runs the
import-time checks below on it.

### 3.3 Import-time checks the schema cannot express

The schema constrains shapes and types. The importer additionally refuses a
record when any of these fail, and says which: `turn_id` values must be
unique; `conversation_id` must be unique across the input file and the
existing transcript store (a repeat with the same `text_sha256` is an
idempotent duplicate, skipped and reported; a repeat with a different digest
is a conflict, refused); an assistant turn's `reply_to`, when given, must
name an earlier user turn; every framing annotation must resolve to exactly one turn whose
role is `user` and must name a dimension and value declared in the
registry; at most one annotation per turn and dimension (two classifications
of one turn on one dimension would leave the counterfactual step with
contradictory sources); every `*_utc` stamp must parse as a real UTC
instant, not only match the pattern; `text_sha256` must equal the digest of
the turns as received. Every turn carries `attachments_omitted`, an explicit
zero when nothing was dropped, so non-text content is always reported. A
record that fails is reported, never partially imported, and an annotation
that cannot be resolved is never dropped silently. Which user turn an assistant turn answers is decided by rule, never by
guess: an explicit `reply_to` wins; otherwise the immediately preceding
turn, only if it is a user turn. An assistant turn that cannot be paired
that way (consecutive assistant turns, a tool-mediated exchange, a reply
with no preceding user turn) is judged observationally but is ineligible for
the counterfactual step, reported as `unpaired_reply`. Two further
per-turn ineligibilities come from `attachments_omitted`: a user turn with a
positive count cannot be reproduced from text, so its pair is
`attachments_omitted`; an assistant turn with a positive count is judged as
`incomplete_reply`, since the judge does not see the whole answer. The
reference implementations are `semantic_problems`, `file_problems`,
`reply_pairs` and `counterfactual_ineligibility` in
`tests/test_framework_schemas.py`; the importer (§7 step 4) adopts them.

### 3.4 Target tokens for the mechanistic probes

The study's stimulus pairs carry a clinical target token, and every probe
except the advice tier reads a probability or an activation at that token.
An imported turn has none. The probe catalogue therefore declares each
probe's `inputs`: `pair_text` (every pair has it), `response_text` (the two
re-elicited replies; a pair whose re-elicitation was refused or failed on
either arm lacks it, and the advice-tier probe is then reported as
unavailable by name rather than judging a missing reply), or `pair_text`
plus `target_token`. A pair derived from a transcript lacks the target until a
target-selection rule assigns one and persists it in the pair record (the
rule is an owner decision: a judge-chosen token, a rule over the rewritten
turn, or a human choice, each recorded with method and annotator like a
framing annotation). Until then the probes that list `target_token` are
reported as unavailable for that pair. They are never run with a null
target: `scripts/logits_eval.py` returns a null `language_penalty` in that
case, which would read as a measurement.

## 4. The framework of differences

`docs/framework/framing_dimensions.draft.json` is the registry. It has two
lists and one vocabulary.

**Dimensions.** Each is one way the same situation can be framed differently
by a patient and by a clinician. An entry declares its `values`, how a turn
is classified on it (`detection.methods` from rule, judge, human, with a
judge prompt reference), how its counterfactual is produced
(`counterfactual.method` and an explicit list of `contrasts`, each a named
source-to-target pair; every contrast is generated and reported under its
own key, and a value listed in `no_contrast` is classified and judged but
not re-elicited), and which probes can measure its effect (`probes`, ids
from the second list). For `register`, the two contrasts are colloquial to
clinical and clinical to colloquial; `mixed` has no contrast until the owner
defines one, and the registry says so. The first entry is `register`,
colloquial against clinical wording, the study's founding contrast, wired to
every probe in use. The second is a placeholder showing the full shape of an
entry. The content of this list is owner-authored: which differences matter
clinically, where the boundary between values lies so that a human and a
judge would agree, and what counts as a faithful rewrite. That is domain
expertise and belongs in the data file, never in code, the same rule the
study applies to medical vocabulary.

**Probes.** Each is one interpretability or behavioural measurement: id,
what it needs from the environment (`requires`), what it needs from the pair
(`inputs`, §3.4), where it is implemented, what it emits, and its status. The six in the file are the measurements the study already makes,
with the attribution graph split in two: the served graph (available for
any model the hosted service traces, features untagged) and clinical
feature mass (meaningful only where a transcoder source set tags the
features; gemma-2-2b today, per `AGENTS.md`).
A new tool joins by adding an entry and one adapter that reads a pair and
writes a record; nothing else changes, and the dimension entries say which
tools apply to which difference.

**`requires` levels.** `text_io` (any model, API or product UI), `logits`
(the probability of an explicit target token on both sides: open weights,
or an API that scores a named target), `logprobs_topn` (an API returning
only its top-N logprobs, which is not enough: the target may be absent, and
a probe run there reports a named censored result for that side, never a
probability), `activations` (open weights run locally), `hosted_graph` (a hosted attribution service serves graphs for
the model), `hosted_graph_tagged` (that plus a transcoder source set, so
features carry tags), and `hosted_lens` (a hosted lens endpoint serves
readouts for the model; the J-lens probe calls Neuronpedia and uses no local
weights, so it is a hosted capability discovered per model, not a local
one). This is what makes the framework honest about
portability: every dimension gets the `text_io` probes everywhere, and the
mechanistic probes exactly where the model environment allows them. A report
states which level each number came from.

The three probes that read `batch_summary` files carry a `completeness`
rule: a summary with `completed` false, or fewer results than
`pairs_requested`, is rejected and a missing-index record is emitted per
absent pair before any analysis. `run_batch` truncates `results` on a
mid-batch failure with no per-pair error record (`AGENTS.md`), so a
consumer that reads the surviving prefix as the cohort would be biased
without knowing it.

The test keeps the registry consistent: unique ids, every probe a dimension
names exists, every probe's `requires` is a declared level, every contrast
runs between two distinct declared values, and every value either has a
contrast or is listed as having none.

## 5. Privacy as a design constraint

Both repositories are public. Imported conversations are never committed to
either; the framework's data directory for transcripts is outside the
repository. A guard in the spirit of `seal_check.py` enforces that, and it
must catch the accidental case, not only the well-formed one: a
conversation pasted as plain text, a CSV export, or a single turn matches
neither the record digest nor the schema's shape. The guard therefore keeps
a private index of every imported turn's normalised text (case-folded,
whitespace-collapsed; hashed in fixed-length shingles, and as a whole-turn
hash for every turn, so a turn shorter than the shingle window is still
matched by its whole text and the index reveals nothing) and scans every staged file's text for any shingle hit, refusing
the commit and naming the file; whole-record digests and schema-shaped
content are refused as well; and a path policy refuses any file under the
transcript data directory or any `.jsonl` that validates as a transcript.
The index lives with the transcripts, outside both repositories. De-identification is a precondition of import, enforced by
the schema (§3.2), and the counterfactual step sends de-identified text only.
Which model environments may receive that text is the deploying
organisation's decision: the adapter layer makes local open-weight models a
first-class choice for the case where no external provider may see it, and
the report records which environment each measurement used.

## 6. Where it runs

The behavioural layer becomes a pip-installable package with a command-line
entry point and no dependency on this repository's push-to-run CI, so a
health system runs it inside its own environment. This repository's CI lanes
become one deployment of it, not the definition.

Host harness: the recommendation is to wrap the package as tasks and a
scorer on an existing open evaluation harness rather than maintain provider
adapters alone; Inspect (UK AI Safety Institute) is the closest fit in
structure (model-agnostic providers, task/solver/scorer, evaluation logs).
Its current provider list and log format are to be verified against its
documentation in step 2 before any code depends on them; if they do not
fit, the standalone package still works on its own.

Reporting: the same facts the site publishes today, plus a mapping from each
framework output (framing-sensitivity estimate with its direction and
interval, tier-downgrade rate, judge agreement, drift series, and the
`requires` level of every number) to the items in the assurance frameworks
health systems already use. Candidates, each to be checked for its current
version before being cited: the NIST AI Risk Management Framework and its
generative-AI profile, ONC HTI-1 decision-support transparency, the
Coalition for Health AI assurance work, WHO's 2024 guidance on large
multimodal models in health, and the TRIPOD-LLM reporting guideline.

## 7. Sequence

Each step is one pull request with its own tests; none touches a trigger
file.

1. **Contracts** (this note): transcript schema, dimension and probe
   registry, consistency test. Owner fills the dimension list.
2. **Package extraction**: the behavioural layer (stimuli, elicit, judge,
   analyze) as an installable package with a `no-reelicitation` mode that
   reads a transcript file and judges assistant turns without calling the
   model under test (the judge model, or human coding, is still required
   and declared). Acceptance: the existing advice families re-run through
   the package reproduce the published tier counts.
3. **Harness wrapping**: tasks and a scorer on the chosen harness; verify
   its provider list against the registry. Acceptance: one family runs end
   to end on the harness with matching numbers.
4. **Counterfactual import**: the import-time checks of §3.3 and the
   model-identity precondition of §3.1, per-turn classification, rewrite per
   declared contrast, re-elicitation, paired output keyed on conversation
   and turn with the target-token rule of §3.4 applied or the target-needing
   probes marked unavailable, conversation-level clustering in the analysis;
   the privacy guard with its shingle index and path policy. Acceptance: the synthetic example
   produces a paired record with full provenance, a record failing any §3.3
   check is refused with the reason, and the guard refuses a commit
   containing a transcript.
5. **Probe adapters**: the five existing measurements behind the probe
   interface, `requires` enforced. Acceptance: each dimension's probe list
   runs where its level allows and reports "not available at this level"
   where it does not.
6. **Reporting and mapping**: the assurance-framework mapping and the drift
   sentinel as the monitoring story.

## 8. Decisions for the owner

- The dimension list (§4): which differences, their values, their
  boundaries, and the faithful-rewrite rule for each.
- The host harness (§6): an existing one, or the standalone package alone.
- Whether the framework is a third repository or a package inside this one.
  A third repository keeps the public-data rule simple and lets the engine
  remain the study; the package can still be developed here first.
- The name.

## 9. Open questions

- Multi-turn context for the counterfactual (§3.1): re-eliciting one turn
  with the original preceding turns holds everything else fixed, but the
  original turns were themselves framed; whether to rewrite the whole
  history or one turn is a per-dimension choice and belongs in the registry.
- Judge validity on real transcripts: the rubric was validated on stimuli;
  the judge-agreement measurement should be repeated on imported turns
  before any transcript number is published.
- Which probes can run on an API that returns logprobs but not activations,
  and whether their numbers are comparable to the local ones (the bfloat16
  limitation in `AGENTS.md` applies).

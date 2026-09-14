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
| Paired statistics (`paired_stats_rigor.py`, phrase-clustered bootstrap), judge agreement, retrace consistency | The analysis layer, reused as is |
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
   This is the observational reading and needs no model call.
2. **Classify the user turn on each framing dimension** (§4): by rule, by
   judge, or by a human, recorded with method and annotator.
3. **Produce the counterfactual turn**: rewrite the user turn to the other
   value of a dimension (for register, the existing patient-to-clinical
   translation step and its reverse), re-elicit from the same model with the
   same preceding context, and judge the reply. The difference between the
   two judged replies is the framing effect for that turn, on that model,
   in that conversation.

Step 3 makes the imported conversation a paired measurement in exactly the
form the study already analyses, so the paired statistics apply without
change. Step 2's classification also serves the observational analysis
across conversations, as a covariate.

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
  and the importer refuses it before reading a single turn. `method`,
  `reviewed_by` (a role, never a name) and `reviewed_utc` record how the
  de-identification was done and confirmed.
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
- **`provenance.text_sha256`** is a hash over the canonical JSON of `turns`,
  so later edits to the text are detectable, as with the elicit chain.
- `additionalProperties` is false at every level. A field the schema does
  not name cannot ride along, which is how a stray identifier is kept out.

`docs/framework/example_transcript.jsonl` is a synthetic record with
placeholder text; the test validates it against the schema and checks that
its annotations name a declared dimension and value.

## 4. The framework of differences

`docs/framework/framing_dimensions.draft.json` is the registry. It has two
lists and one vocabulary.

**Dimensions.** Each is one way the same situation can be framed differently
by a patient and by a clinician. An entry declares its `values`, how a turn
is classified on it (`detection.methods` from rule, judge, human, with a
judge prompt reference), how its counterfactual is produced
(`counterfactual.rewrite_to` and `method`), and which probes can measure its
effect (`probes`, ids from the second list). The first entry is `register`,
colloquial against clinical wording, the study's founding contrast, wired to
every probe in use. The second is a placeholder showing the full shape of an
entry. The content of this list is owner-authored: which differences matter
clinically, where the boundary between values lies so that a human and a
judge would agree, and what counts as a faithful rewrite. That is domain
expertise and belongs in the data file, never in code, the same rule the
study applies to medical vocabulary.

**Probes.** Each is one interpretability or behavioural measurement: id,
what it needs (`requires`), where it is implemented, what it emits, and its
status. The five in the file are the measurements the study already makes.
A new tool joins by adding an entry and one adapter that reads a pair and
writes a record; nothing else changes, and the dimension entries say which
tools apply to which difference.

**`requires` levels.** `text_io` (any model, API or product UI), `logits`
(open weights or an API that returns logprobs), `activations` (open weights
run locally), `hosted_graph` (a hosted attribution service with a
transcoder set for the model). This is what makes the framework honest about
portability: every dimension gets the `text_io` probes everywhere, and the
mechanistic probes exactly where the model environment allows them. A report
states which level each number came from.

The test keeps the registry consistent: unique ids, every probe a dimension
names exists, every probe's `requires` is a declared level, every
counterfactual target is a declared value.

## 5. Privacy as a design constraint

Both repositories are public. Imported conversations are never committed to
either; the framework's data directory for transcripts is outside the
repository, and a guard in the spirit of `seal_check.py` refuses any commit
whose content matches a transcript record (by `text_sha256` and by the
schema's shape). De-identification is a precondition of import, enforced by
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
   analyze) as an installable package with a `judge-only` mode that reads a
   transcript file and judges assistant turns with no model call. Acceptance:
   the existing advice families re-run through the package reproduce the
   published tier counts.
3. **Harness wrapping**: tasks and a scorer on the chosen harness; verify
   its provider list against the registry. Acceptance: one family runs end
   to end on the harness with matching numbers.
4. **Counterfactual import**: per-turn classification, rewrite,
   re-elicitation, paired output; the privacy guard. Acceptance: the
   synthetic example produces a paired record with full provenance, and the
   guard refuses a commit containing it.
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

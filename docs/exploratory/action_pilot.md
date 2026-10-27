# First assisted action-label pass

This implements the owner's authorized **10 existing synthetic challenges followed by
R01–R04**, at most one generation request per item and **$1 gross API spend for the
whole pass**. It is assistance for reviewing explicit actions, not a classifier
accuracy estimate, clinical validation or an equity finding. No API execution or
new model result is claimed by this implementation PR. Owner answers stay outside
Git and are never sent to the annotator. No more family labeling is required here.

## Fixed inputs and compatibility

`data/action_annotations/assisted_pass.v1.json` records original archive, record,
text, contract and request hashes, plus the preparation-plan receipt. It adds the
four text hashes and all 14 request hashes to the prior identifiers-only preparation;
source texts and requests are unchanged. Provisional grouping IDs are joins, not
validated case families. Ten authored synthetic challenges and four archived,
model-generated responses keep distinct origins. Neither is patient testimony.
The model sees only the existing rubric/schema/instruction and response text.

`action_pilot_inputs.prepare` checks archive bytes and hash chain, report count/head,
stimulus joins, selected response hashes and the current seal before producing the
frozen requests. Missing, altered or sealed inputs refuse, with no repair/substitution.
The synthetic-only `action_annotations` and Messages replay CLI keep their gates.
No physician bundle, questions, instructions, established endpoint, Jev judge or
existing measurement is modified. This namespace has no frontend consumer and no
`batch_summary` filenames. There is no publication or deployment step.

The synthetic key is not an independent gold standard; preliminary owner labels
are incomplete. Valid JSON and literal spans do not establish correct/exhaustive
labels. A structurally invalid challenge stops the pass; disagreement with an
unadjudicated key does not silently discard a challenge or certify the model.

## Admission and budget

Only `fire_trigger.py` may create/change `action-annotate.json`, after this PR lands.
The workflow has only a trigger-file push event, main/owner/first-attempt/creation
checks, and one per-ref concurrency group with cancellation disabled. Park has no
provider access or output commit. The paid pass accepts the fixed plan and named
initial/recovery nonces only (the one recovery is described below);
nonce reuse remains forbidden even after resolve/expiry/eviction. A failed admission
also consumes that reservation identity: do not repair and replay it automatically.

The worker verifies the event's before/after and clean checkout, a single fire commit
whose parent is `expected_commit` and whose only changes are trigger/journal, live
remote main equality, and the existing journal/digest/ref/push/daily-budget gate.
A rebase after main advances refuses instead of silently executing new code.
It rejects the last 35 minutes of a UTC day, has a 30-minute campaign deadline,
20-second count deadlines and 120-second generation deadlines, with a 45-minute job
timeout for setup and artifact preservation. These are limits, not runtime forecasts.

The existing stricter $2 daily operational ceiling remains. No $50 override is
created. For this pilot, the $200 monthly allocation is checked conservatively:
max(dashboard lifetime, sum of all historical sidecar costs across providers), plus
current-month reservations and unresolved older reservations, plus this $1. This
intentionally overcounts; unknown costs or malformed records refuse. It assumes the
repository's CI-only accounting, not an account-wide provider billing audit, and does
not retrofit monthly enforcement into other lanes. No credit reduces gross spend.

The dated `price.v1.json` expires after 2026-11-02. Its sources are the official
[model pricing/context specification](https://platform.claude.com/docs/en/models/haiku-5-5/overview)
and [free token-count endpoint](https://platform.claude.com/docs/en/build-with-claude/token-counting),
checked 2026-10-26. It preserves the merged Haiku 5.5 request profile and API version.
Account access and actual returned metadata remain untested until the authorized run.

All 14 free token-count requests precede generation. Counts are estimates: their
higher-rate total with capped outputs must fit $1, but they do not weaken admission.
Before **every** paid call, remaining funds must cover a full 1,000,000-token input
at $0.50/M plus 8,192 output tokens at $2.50/M: **$0.52048**. Calls run serially and
actual reported usage is priced before another begins. This bounds a next request
under the documented model/rates without assuming byte length equals token count.
It does not guarantee all 14 complete within $1. Price changes, unsupported usage,
nonstandard billing dimensions or unknown charges stop continuation. Costs are
published-rate calculations, before credits, not invoice-verified totals.
The [Messages usage fields](https://platform.claude.com/docs/en/api/messages/create)
are checked separately: standard speed/tier and global routing only, with zero
cache/tool/thinking counts. Output details are not added to output tokens again.

## Records and recovery

Every generation attempt writes/syncs its exact request and start record before
sending. It then saves raw response bytes (including received partial bodies),
request ID, timestamps, transport outcome and derived annotation. An unknown
charge stays null and retains the full reservation; no retries, fallback or resume.
Not-attempted IDs remain listed. Source/model metadata never enters provider prompts.
A SIGKILL or runner loss can leave just a start/progress snapshot; never infer zero.

The always-run artifact step uploads the external run directory as
`action-pilot-<run_id>-1`, retained 90 days. The always-run cost step stages only
`data/action_annotations/runs/action_<run_id>.report.json`, preserving the artifact
report hash and excluding annotation items. It uses the existing clean-worktree
publisher with collision refusal, so unrelated source outputs and operational files
are not pushed. A failed upload/push is a blocker: inspect the actual job/artifact,
harvest promptly into durable local storage, and keep the journal unresolved until
all expected evidence is recovered. GitHub artifact retention is not permanent
archival. A missing upload is not successful preservation.

`ledger_update.py` alone folds the new additive cost namespace. It refuses the
entire update before writes if any new-format cost is unknown/unreconciled; null
never falls through the legacy zero default. Known failed calls can still have
costs. No automatic journal resolve, refund or reservation release is implemented.
Do not alter unknown historical receipts; reconcile them through a reviewed,
evidence-backed follow-up if necessary. The Routine remains the sole committer of
its dashboard. There is no change to existing sidecar interpretation.

## Local verification and later execution

Offline preparation, writing only a NEW external directory:

```bash
python -m scripts.action_pilot prepare --out /tmp/pw-action-prepared-new
python -m pytest -q tests/test_action_pilot.py tests/test_action_annotation_transport.py \
  tests/test_action_annotation_reply.py tests/test_ledger_update.py tests/test_fire_trigger.py
python -m ruff check .
```

The tests inject transports and synthetic archives, including real temporary Git
ref/reservation checks. They make no provider calls. The existing full suite and
workflow YAML/actionlint checks also apply before pushing. Local success is not
hosted execution or independent PR review.

After owner merge and final review, use a clean, current-main operational checkout.
Recheck remote head, queue, exact merged code, price validity and account availability;
do not fire while another paid run's accounting is uncertain. Create the harmless
park using the tool (never add trigger JSON by hand), wait for its terminal no-op,
then set `expected_commit` to the new current main SHA. Generate a local params file
with `mode: run`, the plan SHA from `action_pilot_inputs.PLAN_SHA256`, `max_spend:
"1.00"`, `expected_commit` and `_nonce: assisted-actions-20261025`. Run the tool's dry
run first and inspect its output, then the same authorized fire. **Do not replace
this with workflow dispatch or local API execution.** Exact fire commands belong in
the post-merge handoff because the required code/main SHA does not exist yet.

After the single pass, inspect terminal jobs, raw captures, missing items, usage,
annotation validity and sidecar landing; preserve artifacts locally and report
cost/limitations. Re-park through the tool only after harvesting; resolve only on
terminal evidence. Any scale-up, retry or publication is a separate decision.

The first live fire (Actions run `40320384841`, 2026-10-26) was refused before
transport construction: the worker passed `refs/heads/main` to the budget gate,
while `fire_trigger.py` journals `main`. The worker now passes the short name
after enforcing its exact main-ref identity; the regression uses the writer's
real `fire_ref` result. This fixes admission without relaxing branch binding.
That failed fire made no API call and produced no result/cost artifact. Its
reservation and consumed nonce remain unchanged. No replay, refund or completed
pilot is inferred from this correction.

On 2026-10-26 the owner explicitly requested fixing Anthropic and running it again,
while leaving Jev untouched for their OpenRouter repair. The one authorized fresh
attempt uses `assisted-actions-20261026-recovery-1`, with the **same 14 request
hashes, model, plan, price receipt and $1 gross cap**. The original plan's historical
`execution_status` is not rewritten; run receipts establish actual outcomes.

`data/action_annotations/recovery_20261026.v1.json` records the original run URL,
fire/source commits, saved refusal-log and worker hashes, and the exact retained
journal reservation. The worker pins the receipt hash and admits recovery only
with that unchanged original paid entry followed by exactly one new paid entry.
A removed/edited/resolved/evicted original entry, missing receipt, different nonce,
duplicate or third paid attempt refuses. The existing trigger writer still rejects
every reused nonce. The new artifact and additive cost receipt include a `recovery`
object linking the original failure; no existing consumer or output field changes.

The original $1 continues to count alongside the new $1. Both daily and monthly
gates remain in force; any refusal stops execution without raising a ceiling.
This reviewed receipt attests this particular pre-transport failure, not a generic
inference that an absent artifact means no spend. It authorizes no future recovery.
No original run, journal entry, sidecar or source artifact is overwritten.

After this recovery change is reviewed and owner-merged, use the new nonce in a
fresh tool-generated fire after rechecking the actual queue/accounting and current
main. This lane is already initialized: do not repeat the initial park step above
or resolve the old failure to make room. Retain the original failed entry unresolved.
Do not invoke `resolve` merely to clear the older missing-artifact failure.
Re-park through the tool after terminal harvesting;
if the journal's active slots are full, wait for expiry rather than evicting a hold.
This owner request authorizes the new run; it does not authorize agent merging or
bypassing review. No further paid attempt is allowed if this recovery stops.

## Quote-only correction after the first response

Recovery run `40344924588` passed source/budget admission and all 14 count requests.
Its first generation (s01) returned HTTP 200 but an invalid annotation:
`evidence_span_mismatch`. Both proposed ranges were `[0,60)` in a 55-code-point
source; the quoted evidence and condition occur at `[0,55)` and `[26,54)`.
The worker stopped: zero accepted annotations, 13 items unattempted, including all
four archived responses. Its additive receipt is
`data/action_annotations/runs/action_40344924588.report.json`; reported usage costs
$0.0002326 at the pinned published rates, not an invoice-verified total. Raw bytes
and historical records are not repaired or relabeled by the following correction.

`scripts/action_quote_annotations.py` adds a **separate provider contract**,
`data/action_annotations/annotation_quotes.v1.schema.json`. The provider copies
quotations and supplies `schema_version: patientwords.action-quotes/1`, without
numeric offsets. The normalizer requires evidence to occur exactly once in the
original source, then timing/condition quotations exactly once within that evidence.
It counts overlapping occurrences, preserves case/whitespace/Unicode and derives
zero-based, end-exclusive Unicode-code-point positions. Missing, empty or ambiguous
matches refuse; no fuzzy matching, first-match selection or context expansion.
Longer contextual quotations can distinguish otherwise repeated phrases.

The resulting object passes every existing `annotation.v1.schema.json` and rubric
constraint. Categories, stance, actor, status, missing/null rules and negation/context
requirements are unchanged. `rubric_quotes.v1.json` changes only the version and
span-format instruction. Literal correspondence still cannot establish correct or
exhaustive action labels, clinical appropriateness, or health-equity findings.

`interpret_reply(..., response_format="patientwords.action-quotes/1")` explicitly
selects this route and emits interpretation version 2, retaining provider proposal,
raw-body hash, normalization implementation/schema identities and normalized result.
Failures keep raw provenance and no accepted annotation. The default remains the
unchanged numeric-span version 1: old replies are never automatically repaired or
reinterpreted as quote-only. Transport/model/stop/usage checks remain shared.

`data/action_annotations/quote_preparation.v1.json` freezes new request/contract
hashes and links the prior plan/failure. Offline preparation first re-admits the
original source hashes, joins and seal, then checks the new requests. It keeps the
same 10 synthetic challenges and R01–R04, model/settings and source text; owner
labels, source-model identities and provisional family joins do not enter prompts.
The candidate explicitly records `execution_enabled: false` and zero model calls.

```bash
python -m scripts.action_quote_annotations --out /tmp/pw-action-quotes-new
python -m pytest -q tests/test_action_quote_annotations.py tests/test_action_annotation_reply.py
```

The quote-contract correction in PR #132 **did not enable another paid run**.
At that stage the live campaign accepted only its old frozen plan/consumed identities. Its requests, trigger,
workflow, reservations, price receipt and budget rules are unchanged. A future
reviewed campaign change must bind the quote plan, interpreter format, new attempt
identity and preserved prior receipts, with current prices/budgets and a bounded
owner execution decision. Code merge alone neither fires nor authorizes that run.
No new frontend payload or publication path is introduced.

The regression fixture `tests/fixtures/action_annotations/quote_failure_regression.json`
records the previous invalid annotation and a **synthetic test transformation** of
its quotations. That transformed object is not a new provider response, repaired
research result or independent gold label. Tests keep the original failure invalid
and exercise Unicode, overlapping/repeated/missing quotations, nested context,
schema-first refusals, legacy compatibility and unchanged live-plan refusal.


## One CI-connected quote attempt (owner continuation, 2026-10-27 UTC)

After merging #132 the owner requested the next step. The fixed new campaign is
`data/action_annotations/quote_campaign.v1.json`, SHA-256
`af5ebe737664fca846ac9452cf639fbb0ee26fdb83e9f3556763b0326f25906b`,
with nonce `assisted-action-quotes-20261027-1`. It admits exactly one new $1-bounded
pass on the same 14 sources and quote requests. No additional sample, retry, model
change, publication or alteration of historical measurements is included. This
owner request supplies the bounded continuation authorization; code still needs
independent review and owner merge before execution. Do not ask for the same
authorization again once those prerequisites pass.

The receipt pins both earlier reservations unchanged, the landed invalid-response
cost receipt, original failure receipt, quote preparation and normalization/parser
source bytes. Admission refuses missing/edited/reordered history, duplicated or
further paid attempts, and a plan/nonce mismatch. Free park entries may coexist.
Neither expiry nor the UTC date change erases the old commitments: they remain in
the conservative monthly bound; the existing daily gate keeps its own documented
UTC-day accounting. No ceiling, reservation or cost is relaxed.

`action_pilot.prepare_campaign` revalidates the original and new frozen requests.
The existing live CLI chooses the packet from the admitted trigger, before it
constructs the provider client. The worker explicitly selects quote interpretation
and refuses mixed plan/format/attempt identities before any count or send. The
existing CI owner/ref/first-attempt/source checks, 14-count preflight, $1 full
reservation, per-call upper bound, stop-on-first-failure, raw capture, additive
cost landing and no-retry policy remain unchanged. No workflow or trigger-file
change is needed in the code PR.

Offline preparation, with no key or model calls:

```bash
python -m scripts.action_pilot prepare \
  --plan-sha256 af5ebe737664fca846ac9452cf639fbb0ee26fdb83e9f3556763b0326f25906b \
  --out /tmp/pw-action-quote-campaign-new
```

The prepared packet is version 2 and identifies the new campaign, response format
and hash of the quote preparation. The run/cost receipt keeps
`patientwords.action-pilot-report/1` for the existing ledger consumer; additive
`response_format`, `inputs_sha256`, `preparation_sha256`, `prepared_inputs_sha256`
and `quote_campaign` fields identify the change. Item interpretations use version 2
and retain the provider proposal, normalized annotation and raw/schema/code hashes.
Legacy preparation and offset interpretation remain unchanged. The unadmitted
quote-preparation manifest itself is still not a valid trigger plan.

After owner merge: verify exact merged source, terminal queue and retained failure
receipts, current pricing and daily/monthly capacity. Restore resting state with
the tool if necessary. Rehearse `fire_trigger.py fire --trigger action-annotate`
with `mode: run`, this campaign SHA, the new nonce, `max_spend: "1.00"` and the
exact then-current main as `expected_commit`, using `--dry-run` first. Fire only
once when all gates pass; never dispatch/rerun manually or replay either old nonce.
Retain artifacts and costs even on another refusal, then re-park through the tool.
No next retry is admitted. Label completeness, semantic correctness and clinical
validity remain unverified until the resulting annotations are independently read.

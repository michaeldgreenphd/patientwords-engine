# Evidence-linked action annotations — offline v1

This staged tool extracts no live model output yet. It prepares blinded request
previews, checks synthetic response packets and compares them with an independently
written synthetic key. It supplements the existing advice and Petri instruments;
it does not replace their scores, the next-token endpoint, or physician ratings.

The question is whether equivalent wording changes the actions explicitly expressed
by a model. Clinical appropriateness, realism, and equity effects require separate
evidence. Wording alone does not establish a person's identity, literacy or resources.
API-only transcripts do not supply hidden activations for circuit or lens analysis.

## Contract and boundaries

- `data/action_annotations/annotation.v1.schema.json` defines the structure.
  `rubric.v1.json` defines allowed labels and annotation rules. The validator checks
  raw JSON before any transformation; absent required fields fail, explicit null is
  accepted only where declared. No coercion, defaults, duplicate keys or NaN.
- Each action has a category, stance, actor, exact evidence span, explicit timing
  or null, and explicit condition or null. Offsets count Unicode code points,
  zero-based, end-exclusive. The evidence must contain its timing/condition spans.
  Exact quotation is necessary but cannot prove correct classification or completeness.
- `annotated`, `no_actions` and `uncertain` are distinct. Uncertain needs a reason
  and remains a visible missing annotation. A discouraged conditional action retains
  its condition; it is not converted to a conditional recommendation.
- The v1 source envelope has `schema_version: patientwords.action-sources/1`,
  `artifact_kind: synthetic_fixture`, and nonempty `items`, each containing exactly
  `source_id`, `text`, `source_sha256`. The hash is of unchanged UTF-8 text.
- Request previews bind source identity, rubric/schema file bytes and the actual
  implementation file hash. `sources_sha256`, `request_sha256`, response and key
  hashes use sorted compact UTF-8 JSON (`ensure_ascii=false`, no NaN). Source IDs
  remain in the outer join envelope; only response text, rubric and schema are in
  the preview payload. No source arm, generator, prior score or answer key is sent.
- Response envelopes (`patientwords.action-responses/1`, synthetic kind) contain
  exactly one row per selected source: `source_id`, `source_sha256`,
  `request_sha256`, `annotation`. Missing, extra, duplicate or stale rows refuse
  the entire packet. Request hashes bind exact prompt/rubric/schema bytes.
- Output `patientwords.action-validation/1` retains the request packet, annotations,
  response hash, and explicit `structurally_valid_semantics_unverified` status.
  No provider identity or scientific result is invented: `model_calls` is zero.
- `score` additionally checks a separately supplied key. Exact action matching
  includes every label, span, timing and condition, ignoring array order. It counts
  missing/extra actions and exact cases, retaining empty and uncertain cases. Reason
  prose is validated but not matched. This strict fixture metric is not clinical
  accuracy, recall of all appropriate actions, or agreement with physicians.
- Output creation is exclusive, in an existing directory outside Git, with fixed
  filenames `action_requests.json` / `action_annotations.json`. Existing files,
  repository destinations and measurement-collector filenames refuse. A second
  attempt uses a fresh directory; no archive is rewritten or automatically retried.
- The CLI accepts synthetic fixtures only. This is an honest execution boundary,
  not a detector of mislabeled real text. No archive collector, provider client,
  CI lane, site export or physician-app content is changed. The request preview is
  provider-neutral and is not yet an Anthropic Messages API request.

## Reproduce without API access

From the engine root, reuse the normal developer environment; no model packages,
keys or environment upgrade are needed. Choose three new directories outside Git:

```bash
PW_ACTION_CHECK=$(mktemp -d /tmp/pw-action-check.XXXXXX)
mkdir "$PW_ACTION_CHECK/preview" "$PW_ACTION_CHECK/validated" "$PW_ACTION_CHECK/scored"
python -m scripts.action_annotations prepare \
  --sources tests/fixtures/action_annotations/sources.json \
  --out "$PW_ACTION_CHECK/preview/action_requests.json"
python -m scripts.action_annotations validate \
  --sources tests/fixtures/action_annotations/sources.json \
  --responses tests/fixtures/action_annotations/responses.json \
  --out "$PW_ACTION_CHECK/validated/action_annotations.json"
python -m scripts.action_annotations score \
  --sources tests/fixtures/action_annotations/sources.json \
  --responses tests/fixtures/action_annotations/responses.json \
  --key tests/fixtures/action_annotations/responses.json \
  --out "$PW_ACTION_CHECK/scored/action_annotations.json"
python -m pytest -q tests/test_action_annotations.py
```

The self-comparison is a plumbing check, not a model evaluation. The tests also
inject a wrong stance with a valid quote: structural validation passes and the
independent key comparison fails that case. They test malformed output, incomplete
coverage, Unicode, joins, output preservation and null/missing distinctions.
`cases.json` is the author-written semantic key, kept outside the request payload;
`sources.json` and `responses.json` materialize its literal spans for CLI replay.
These ten cases are provisional software fixtures, not clinical ground truth.

## Next API pilot — specification only, not authorized or wired

1. Independently review this contract and the ten author-written challenge keys
   before looking at model annotations. Freeze rubric, schema, prompts and keys.
2. In a separate focused integration, add an explicit unsealed archive selection
   manifest (ten existing matched case families, both responses, identifiers/hashes
   and selection seed recorded). Freeze it before extraction; preserve failed and
   already-correct cases. Never choose from holdouts or use a best-looking outcome
   to define the sample. Keep arm/model mappings outside the extractor prompts.
3. Wire the annotation pass into an owner-approved CI-only route using the existing
   reservation, price-refusal, queue and per-pass sidecar machinery. Do not silently
   reuse Jev's OpenRouter route for an Anthropic allocation, or replace a registered
   judge. Preserve mandated judge-of-record/secondary passes in their existing lanes.
   The new annotation task needs its own exact model/settings identity, request IDs,
   raw completions, truncation/refusal states, server usage, timestamps and run SHA.
   No execution command exists for this annotation pass until that wiring is reviewed.
4. Proposed first run: ten synthetic challenges plus twenty archived responses,
   each independently presented, with a **$1 total reservation**, including all
   permitted attempts and any required second pass. Cost it using verified current
   model support/prices and worst-case output allowances before authorization. Reduce
   the sample if it cannot fit; do not silently increase the reservation. Keep the
   current enforced ceiling: the owner's newer $50/day and $200/month allocation
   does not itself implement monthly accounting or authorize a fire.
5. Audit every pilot annotation against the literal source and frozen key. Report
   abstentions, invalid output and missing actions, not just accepted rows. Require
   no silent drops, no unsupported evidence and no missed negation/quotation controls
   before expansion. A software-valid but wrong label remains a failed annotation.
   The 20 archived responses need independent manual labels; model consensus is not
   ground truth. Compare errors by wording arm before interpreting an equity gap.
6. After revisions, use fresh case families for confirmation. Report family-level
   effects with uncertainty; repeated annotations/tokens are not independent samples.
   Clinicians separately assess realism and appropriate follow-up using the unchanged
   approved bundle. If a later site view is approved, show machine-annotation status,
   exact evidence and source provenance; no clinical quality or safety meter.

No live API/model run, new stimulus generation, physician-bundle change, scientific
claim, publication or deployment is part of this slice. The separately prepared
lens-independent baseline remains governed by `baseline_ci.md`; unknown historical
J++ fit revisions do not block descriptive action annotations or that baseline.

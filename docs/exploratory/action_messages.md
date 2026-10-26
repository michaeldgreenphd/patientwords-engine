# Action annotations: offline Messages adapter

Integration update: [the fixed assisted-pilot runner](action_pilot.md) now supplies
the separate CI/source/budget admission described as future work below. The original
synthetic-only CLI remains unchanged. No live pilot has run.

This is the next preparation slice after [action_annotations.md](action_annotations.md).
It creates deterministic Anthropic Messages request envelopes and replays explicitly
synthetic transport records. Its CLI has no client, credentials, live mode, retry loop,
archive reader, CI workflow or budget admission path. A prepared request is not
permission to send it. Nothing in this slice changes historical judgments, the
physician bundle, the next-token endpoint or site payloads.

## Request contract

`scripts/action_annotation_messages.py prepare` consumes the unchanged v1 synthetic
source envelope plus a settings object containing exactly `model` and `max_tokens`.
The model is a nonblank string; the output allowance is an integer from 1 through
8192 (a rehearsal bound, not proof of that model's support). The fixture model name
is deliberately nonexistent. There is no default model selection or price fallback.

The `patientwords.action-messages-requests/1` output retains the existing preview,
source/rubric/schema/implementation hashes, and a separate wire-request hash. That
hash covers POST, `/v1/messages`, the explicit API version and the exact body. The
body uses one user text block, the frozen rubric plus output-schema instructions
in the system field, `model`, `max_tokens`, and `stream: false`. Source identifiers,
wording arms, generator identities and reference keys stay outside the body.
Canonical hashes use the existing sorted compact UTF-8 JSON convention.

The schema is supplied as prompt text, **not** as a native structured-output API
feature. Raw completion JSON is checked afterward, with no fences stripped, default
insertion, repair or coercion. This deliberately preserves malformed responses as
failures. Source text is marked untrusted in the prompt; prompt wording is not a
proof against prompt injection. Freeze and review it before a future live pilot.

The protocol file pins API version `2026-10-21`. Anthropic's version documentation
says this version removes temperature, top_p and top_k parameters; the adapter
therefore sends none. Model-specific sampling/thinking defaults are **unverified**.
No model's availability, supported output allowance, alias resolution or price has
been established by this offline contract. These are explicit future execution
prerequisites, not values to infer from a successful fixture replay.

## Attempt and replay contracts

Input `patientwords.action-messages-attempts/1` has exactly `schema_version`,
`artifact_kind: synthetic_fixture`, and `items`. There must be exactly one attempt
for every source; duplicates, extra/missing rows and stale request hashes refuse
before writing an output. Retries need a separately reviewed attempt/accounting
contract; do not overwrite an attempt to simulate one.

Each attempt contains exactly:

| Field | Meaning |
|---|---|
| `source_id` | Outer join identity; never sent in the prompt |
| `request_sha256` | Hash of this source's exact wire-request envelope |
| `started_utc`, `finished_utc` | Explicit UTC timestamps, finish at/after start; fixture declarations, not server attestations |
| `http_status` | Integer HTTP code, or null for a transport failure |
| `request_id` | The provider request ID, or explicit null if unavailable |
| `body` | Exact decoded UTF-8 response body string, or null for a transport failure |
| `transport_error` | null, `timeout`, or `connection_error`; non-null requires the three response fields above to be null |

No arbitrary headers or credential values are accepted. A replay file is not
cryptographically authenticated API provenance, and the synthetic label cannot
detect real text deliberately mislabeled by a caller. A future CI writer must
supply trusted execution identity and capture these fields from the actual transport.

Output `patientwords.action-messages-replay/1` retains every attempt and its hash,
raw body hash, message/model/stop metadata, complete supplied usage object and a
named outcome. Only a 200 assistant message with the exact requested model, both
IDs, valid nonnegative integer input/output usage, `end_turn`, no stop sequence,
and one uncited text block can reach annotation validation. Missing cache counters
stay absent; additional usage fields are retained. No token total or dollar cost is
invented. `cost.usd` remains null and status is `not_priced` even on replay success.

Truncation, provider refusal, unsupported stop reason/content (including thinking
or tool blocks), model mismatch, missing/invalid usage, invalid JSON/annotation,
HTTP errors and transport errors remain visible outcomes. Unsupported multi-block
responses are not silently concatenated. Duplicate JSON keys, nonfinite numbers
(including overflow), invalid escaped Unicode and missing required-nullable fields
cannot become accepted annotations.

A complete replay emits a compatible v1 `response_packet` for the existing
validator/key scorer. If any attempt fails, this field is null: successful rows
cannot silently become a smaller analysis sample. All outcomes remain in `items`
and `status_counts`; the CLI writes the failure receipt and exits 1. Input-contract
or output-preservation refusals exit 2. Prepare/complete replay exits 0. A complete
replay is explicitly `semantics_unverified`; `uncertain` remains the original
annotation status, not zero actions or semantic success.

## Raw-reply interpretation library

`interpret_reply(reply, expected_model=..., source_text=...)` accepts the bounded
`Reply` produced by [the separate transport](action_transport.md). It makes no
network call, reads no archive or key, and writes nothing. The legacy synthetic
prepare/replay CLI and its request hashes remain unchanged. This library lets the
explicit disabled-thinking profile use the same envelope and annotation validator
without disguising a captured response as a synthetic v1 attempt.

The derived `patientwords.action-reply-interpretation/1` object records raw-byte
SHA-256/length, HTTP status/request ID, completeness/error, expected model, supplied
source-text hash, parsed outcome and provider metadata. Keep `response.bin` and the
original start/request/result receipts; this object neither replaces nor edits them.
Invalid UTF-8 yields `invalid_response_encoding`. An incomplete transfer always yields
`transport_incomplete`, with no accepted annotation or usage, even when its received
prefix happens to be valid JSON. Raw partial bytes remain available for reconciliation.
Complete replies use the strict parser described above, including exact model identity,
literal evidence spans, usage presence, stop reasons and unsupported-content refusals.

`source_binding: caller_asserted_not_admitted` is deliberate. The caller must separately
verify source eligibility, the wire request, immutable receipt hashes and CI origin.
A matching quote does not prove that a response belongs to this source; this function
is a parser, not a campaign loader or authentication gate. It does not validate request
settings, admit an archive source, establish billing or certify correct labels. Every
outcome retains `cost_usd: null` and `reservation_release_allowed: false`. Additional
provider usage fields stay intact and unpriced. The original synthetic gate is unchanged;
there is no new CLI mode accepting research inputs.

Tests exercise the real capture writer with an injected reply, reread its bytes and
interpret the fixed transport profile. All ten existing fixture outcomes agree with
the legacy parser. They also reject complete-looking partial responses, invalid UTF-8,
malformed JSON, mismatched models/spans and invalid transport metadata. These are
synthetic software checks, not model-generated annotations or provider-access evidence.

## Offline commands

Reuse the engine developer interpreter. Run from the repository root; create a new
external directory each time. No package installation, model access or service is
needed. Fixed output filenames reuse the existing exclusive/outside-Git writer.

```bash
PW_MESSAGES_CHECK=$(mktemp -d /tmp/pw-messages-check.XXXXXX)
mkdir "$PW_MESSAGES_CHECK/prepare" "$PW_MESSAGES_CHECK/replay"
python -m scripts.action_annotation_messages prepare \
  --sources tests/fixtures/action_annotations/sources.json \
  --settings tests/fixtures/action_annotations/messages_settings.json \
  --out "$PW_MESSAGES_CHECK/prepare/action_requests.json"
python -m scripts.action_annotation_messages replay \
  --sources tests/fixtures/action_annotations/sources.json \
  --settings tests/fixtures/action_annotations/messages_settings.json \
  --attempts tests/fixtures/action_annotations/messages_attempts.json \
  --out "$PW_MESSAGES_CHECK/replay/action_annotations.json"
python -m pytest -q tests/test_action_annotation_messages.py tests/test_action_annotation_reply.py \
  tests/test_action_annotation_transport.py tests/test_action_annotations.py
```

The ten provider-shaped fixture responses wrap the existing author-written key;
they were not generated by a model. They test plumbing, not model performance.
A separate test changes a stance while preserving its literal quote: parsing and
structural validation succeed, but comparison with the unchanged key fails. Failed
HTTP/transport/usage/content cases, output preservation and complete joins are
also exercised. Synthetic usage numbers must never enter the spend ledger.

## Remaining path to the first useful data

1. Independently review this adapter and the existing challenge key; freeze the
   protocol/rubric/schema. Obtain the shared review window before submitting new
   hosted review requests. No upstream package upgrade is required here.
2. Preserve the owner's narrowed assisted-pass selection: the ten existing synthetic
   challenges and existing R01–R04 responses, with exact source identities and hashes.
   Preserve independent owner selections separately from machine proposals; those
   preliminary, non-exhaustive selections are not an accuracy benchmark. The owner
   requested assistance before further open-ended labeling. Case-family grouping
   stays with the research team and is needed before later confirmation, not as a new
   clinician task. The synthetic CLI still refuses research-source envelopes.
3. Integrate and review the staged CI-only sender and parser with verified exact model/settings,
   raw response/request IDs, immutable per-attempt sidecars and existing queue,
   reservation and ledger integration. Resolve how thinking/content blocks are
   handled for the chosen model before sending anything. Do not add a local live
   flag or use this replay as a budget gate. Unknown usage after a timeout must
   retain its reservation, not count as zero spend.
4. Price the ten synthetic challenges plus four responses within the proposed
   **$1 total reservation**, including attempts/required passes. Obtain explicit
   execution approval and use the repository's approved trigger tooling. The
   $50/day and $200/month owner allocation is dedicated to PatientWords but its
   policy branch is still separate and monthly enforcement is not implemented;
   the runtime's stricter existing limits remain in force.
5. Inspect literal evidence, missed actions, negation/attribution failures, uncertainty
   and error counts before considering a larger fresh-family confirmation. The
   result is descriptive annotation reliability, not clinical correctness or an
   equity conclusion. Clinician realism/follow-up ratings remain a separate gate.

This can progress independently of the lens-independent Qwen baseline, whose Linux
runtime, suitable runner/cost, exact execution pins, seal and authorization gates
remain in [baseline_ci.md](baseline_ci.md). J++ historical fit provenance blocks
verified lens comparisons only. Neither a package import nor this replay validates
an original-model intervention path.

## API references

Inspected 2026-10-24; source documentation, not a live API test:
[Messages](https://platform.claude.com/docs/en/api/messages/create),
[versioning](https://platform.claude.com/docs/en/api/versioning),
[errors and request IDs](https://platform.claude.com/docs/en/api/errors), and
[stop reasons](https://platform.claude.com/docs/en/build-with-claude/handling-stop-reasons).

# Single-attempt action annotation transport

Integration update: [the fixed assisted-pilot runner](action_pilot.md) now supplies
the separate CI/source/budget admission described as future work below. The original
synthetic-only CLI remains unchanged. No live pilot has run.

This library supplies one missing execution primitive: a fixed-endpoint Messages
POST and durable, write-once attempt records. It has no CLI, workflow, key lookup,
source admission, budget admission, retry, campaign runner or publication path.
No real provider execution has been performed. Importing it or preparing a request
makes no network call. Do not use the transport locally: only a future reviewed CI
caller with the existing reservation/nonce, source and owner gates may invoke it.

## Request profile and separation from the offline adapter

`prepare_wire(system, text)` produces the explicit proposed Haiku 5.5 profile:
`claude-haiku-5-5`, `max_tokens=8192`, nonstreaming, disabled thinking, medium effort,
one user text block, one system string, API version `2026-10-21`. `_wire_bytes`
rejects extra fields, alternative destinations/models/settings, invalid UTF-8 and
requests over 1 MiB. This byte limit bounds local memory, **not billed input tokens**.
All request fields are hashed, including the API version and endpoint.

The [official thinking guide](https://platform.claude.com/docs/en/build-with-claude/thinking)
documents disabled thinking for this model at medium effort. The
[Messages reference](https://platform.claude.com/docs/en/api/messages/create)
documents the HTTPS endpoint and API version. Sources inspected 2026-10-25;
documentation is not proof of account access or successful model execution.

This is a wire primitive, not an annotation prompt builder. A future caller must
bind the rubric/schema and correctly escaped source data to these strings. It must
validate source origin, immutable hashes, eligibility and holdout status first.
The synthetic-only contract in `action_annotations.py` is unchanged. The separately
reviewed Messages v1 adapter in engine PR #126 remains unchanged and does not accept
this new profile; its request hashes are not interchangeable. No archive record can
be reclassified as synthetic to use that adapter. The separate [raw-reply interpreter](action_messages.md#raw-reply-interpretation-library)
now accepts this transport’s reply type without changing the v1 fixture contract.
A later campaign integration must still version admitted live/assisted records and
bind source/request/execution identities rather than silently reuse v1 fixtures.

## Transport behavior

`AnthropicTransport` takes a credential in memory, never from files/environment,
and uses the standard-library HTTPS client with its normal certificate validation.
It sends exactly one POST to `api.anthropic.com/v1/messages`. No redirect following,
SDK retry, tools, cache configuration, alternate provider or fallback model exists.
Only the request ID is retained from response headers; credentials and exception
messages are not written to receipts. Raw provider bodies are untrusted data and
must not be published without the existing privacy/secret checks.

The socket timeout is 120 seconds per operation, not an overall deadline. The future
CI job needs a hard timeout. Responses are capped at 4 MiB; overflow, incomplete
Content-Length, timeout and connection errors retain a bounded prefix and an explicit
incomplete state. The connection closes on success and failure. HTTP errors, redirects,
malformed JSON and invalid UTF-8 remain raw bytes; this layer never treats HTTP 200
as annotation success, parses usage, assigns a price or claims valid semantics.

## Write-ahead identity and record contract

`capture_attempt` requires an existing directory named `action_annotation_attempts`
outside this engine checkout and outside `trace_out`, `pilot` or `.git`. A child named
by SHA-256 of the canonical wire request is claimed with exclusive `mkdir`. Before
calling the injected transport, `request.json` and `start.json` are exclusively
created and synced, including directory entries. Files are never overwritten.
The same request within that root cannot be sent again after success or interruption.
Different roots are not a deduplication mechanism: the future campaign must own one
fixed run root and persist it across attempts through its nonce policy.

| File | Meaning |
|---|---|
| `request.json` | Canonical method/path/API-version/body bytes; no credentials |
| `start.json` | `patientwords.action-attempt-start/1`; source ID/hash, request and implementation hashes, server-process UTC start, expected filenames, unknown charge and no release permission |
| `response.bin` | Exact raw body or explicitly bounded partial bytes, including invalid UTF-8/JSON |
| `result.json` | `patientwords.action-attempt-result/1`; start fields plus UTC finish, monotonic elapsed seconds, HTTP status/request ID, raw body hash/length, completeness and named transport error |

The source hash is a caller-supplied join receipt, not verified admission. The caller
must validate it against the selected source. A start without a result, an incomplete
file or even an empty claimed directory is an unknown outcome: stop and reconcile,
never retry it automatically. A write/sync failure before sending prevents the call;
a failure afterward retains earlier evidence and raises. A process or machine crash
can leave only the start or partial files. Local fsync is not remote artifact backup;
the future CI route must preserve partial records even on failure and must keep the
reservation held when upload/accounting fails.

Every receipt keeps `cost_usd: null` and `reservation_release_allowed: false`.
These fields are instructions to the future reconciler, **not an update to the actual
budget ledger**. A complete HTTP response has status `http_response_uninterpreted`;
an incomplete transfer has `transport_incomplete`. The offline interpreter can now check annotation structure and exact returned model
identity and preserve supplied usage; it does not verify semantic correctness or
complete billing. Source admission, request/receipt joins, dated pricing, unknown-charge
holds and sidecar accounting remain mandatory before any live campaign may continue.

## First assisted pass and remaining integration

Family grouping belongs to the research team, not an open-ended task added to the
clinician app. The next assisted pass should propose explicit actions and exact
supporting quotes for a small, frozen set of eligible responses. Preserve original
independent owner answers unchanged; machine proposals and later corrections need
separate provenance. Preliminary, non-exhaustive owner selections cannot define
false negatives or yield a classifier accuracy estimate. Do not equate a neutral
style, conditional recommendation or list of options with clinical appropriateness.

The remaining CI integration must separately admit archived inputs, record assistance
rather than independent validation, bind the request and capture to the parser, enforce the
existing journal/budget/queue gates, preserve partial artifacts and prevent resumption
with a new root. Benchmark claims still require a finalized reference and case-family
splits. No clinician bundle, questions, existing judge or registered endpoint changes.
The new primitive needs no frontend change and does not alter published results.

## Offline checks

```bash
python -m pytest -q tests/test_action_annotation_transport.py tests/test_action_annotations.py
```

Tests inject fake HTTPS connections into the actual transport. Local socket pairs
also exercise the real HTTP response buffer for fixed-length, chunked and
connection-close bodies, including stalls and premature EOF. No external server
is contacted. These tests exercise exact
request bytes/endpoint, redirects/errors without retries, byte limits, partial reads,
credential-free receipts, write-before-send, storage failures, interruptions and
exclusive claims. They call no provider, read no keys or archive data, and establish
no real-model support or inference result. Full offline suite and Ruff remain required
before pushing code. There is deliberately no live invocation example yet.

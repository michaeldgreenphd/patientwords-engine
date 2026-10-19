# One local exporter-to-browser slice

This is synthetic software evidence, separate from the Causalab fix and first
interpretability pilot. It is neither a deployed-site test nor real-model evidence.
No inference, production export, workflow dispatch, push or deployment is required.

The selected path is `scripts/export_frontend_simulated.py` →
`data/simulated_scenarios.json` → `simulated-scenarios/index.html`. The resource is
a static JSON file served by HTTP, not a dynamic engine API. The existing
[case-report mapping](case_report_mapping.md#existing-site-boundary-test) now maps
this slice separately from the proposed exploratory report.

## Authority and client

[`simulated_scenarios.v1.schema.json`](../../scripts/contracts/simulated_scenarios.v1.schema.json)
is the structural authority. It preserves additive fields and legacy absence of
`models_meta`, `models`, and `archive`. The existing export gate still requires
model metadata for newly generated exports (`x-export-required` annotation).
The existing checker derives its field/type definitions from this schema and
keeps counts, calibration, joins and base-mirror equality as semantic checks.
Its small stdlib adapter supports only the declared schema subset and rejects
unsupported keywords; it is not a replacement for JSON Schema generally. Its
pre-existing strict integer-token rule rejects `1.0`; draft-07 accepts it as an
integer. No payload field or research dependency changed.

The [OpenAPI 3.1 description](../../scripts/contracts/simulated_scenarios.openapi.json)
declares draft-07 and references that authority for the one existing GET resource.
It defines no write endpoints. The client resolves the local external reference;
the generator handles its internal references. Regeneration is byte-compared.

**Client limitation and fallback:** datamodel-code-generator 0.35.0 generates
response models, not HTTP transport, and renders required nullable fields as
optional defaults. Its generated models also discard unknown additive fields on
serialization. They therefore cannot independently enforce/preserve this contract.
The small [real-HTTP client](../../scripts/boundary_client/client.py) validates
status, JSON media type and actual decoded response bytes with full draft-07
validation *before* exercising generated models, and returns the original object.
The HTTP transport is handwritten; this is a validated-client fallback with
generated response models, not a claim of a fully generated SDK. Nothing generated
is edited by hand. No SDK enters the production frontend or build process.

## Execute locally

Prerequisites: Python 3.13, two local checkouts, an isolated development venv with
[`requirements.lock`](../../scripts/boundary_client/requirements.lock), and Chromium.
The browser may be an already-installed executable; its actual version is recorded.
To install only the separate test environment (network access is needed for setup):

```sh
python3 -m venv /tmp/pw-boundary-venv
/tmp/pw-boundary-venv/bin/pip install -r scripts/boundary_client/requirements.lock
/tmp/pw-boundary-venv/bin/python -m playwright install chromium
```

One-command slice, from the engine checkout; omit `--browser` to use the installed
Playwright browser, or set `CHROMIUM` to an existing executable:

```sh
/tmp/pw-boundary-venv/bin/python scripts/check_frontend_boundary.py --site "$SITE" --browser "$CHROMIUM" --receipt /tmp/frontend-boundary.json
```

The runner materializes the independently specified
[fixture](../../tests/fixtures/frontend_boundary.json), invokes the real exporter
CLI in a sibling `patientwords-engine`/`patientwords` layout with the same `scripts/`
subtree available in site CI, copies the actual site, and serves it under
`/patientwords/` on an ephemeral `127.0.0.1` port. Source inputs, exports, render
pruning and mutations exist only in the temporary tree; its server and files are
cleaned on exit. The real exporter, HTTP transport and page JS are not mocked.
No inference is attempted. The five ancillary JSON fetches get explicit local
substitutes from the fixture; no other study results enter those page sections.
Browser routing blocks every origin except the test server; the client accepts
only literal loopback and follows neither redirects nor environment proxies.
The only temporary HTML edit inserts a visible synthetic disclosure; page JS and
rendering remain the real consumer. The index has no native sample mode.

## Evidence and limits

The [receipt](frontend_boundary_receipt.json) binds actual engine/frontend HEADs,
dirty diff identity, fixture/schema/toolchain hashes, versions, normalized commands,
and results. `tracked_diff_sha256` hashes `git diff --binary HEAD` (staged and
unstaged tracked changes); untracked files have individual byte hashes. The receipt
itself is excluded to avoid circular identity. Paths in the receipt are repository
relative or placeholders, not private workstation paths.

The browser asserts exact two-decimal probabilities, shared 0–1 axis, gap sign
convention, row/target associations, model labels/provenance, outcome/search
filters, zero versus missing, untraced second-model rows, and legacy base fallback.
Independent semantics assert the full-vocabulary probability meaning, patient minus
clinical gap, two scored rows out of three, mean −0.0734, and absent CI. These are
fixture expectations, not study findings; no empirical softmax computation occurs.
The real exporter also receives a fourth accepted synthetic input without a trace;
the browser must show “1 of 4 accepted scenarios are still tracing.”

The final local run passed 14 checkpoints, including 287 affected offline cases
inside the sparse sibling layout. The receipt includes each deliberate rejection
and restored pass, zero browser errors and zero attempted external requests.
Ruff and `git diff --check` passed for the changed handwritten Python and patch.
Generated-model regeneration was byte-identical. Hosted tests remain unrun.

## Small extraction after protection

The coverage/contract commit is `ef22c7b9`; the frontend documentation-only commit
is `6bfd860`. Only after its passing browser run, the schema interpreter was moved
to `scripts/frontend_contract_schema.py`. It is a cohesive structural-validation
responsibility; no test, exporter, research data or existing script path moved.

| Before | After | Compatibility |
|---|---|---|
| `validate_frontend_contract.check_schema_subset(rep, ...)` body | `frontend_contract_schema.check_schema_subset(rep.err, ...)` | Original public function remains a forwarding wrapper with identical signature and diagnostics |
| Validator's scalar type helper used by adapter | Adapter's private scalar type helper | Identical bool/integer handling; other validators retain their existing helper |
| `tests/test_simulated_schema.py` and four affected test modules | Same modules, functions, parameter IDs and fixture scope | Every one of the 286 prior node IDs maps to itself; one arbitrary-CWD regression added |

The receipt's grouped node inventory is the explicit old→new identity mapping,
not merely a count. Inspection found no collection hooks in `tests/conftest.py`;
selected tests use offline fixtures. Existing imports by filename, package imports,
CLI calls, `__file__` schema resolution, cross-artifact join callers and the site's
sparse `scripts` path were checked. No historical source receipt is rewritten.
An isolated interpreter test verifies the public wrapper and CLI from an arbitrary
working directory without relying on `PYTHONPATH`. Further validator splitting is
deferred; it would extend beyond this one responsibility.

The deliberate controls are executable in each run:

- Delete a required model probability: raw HTTP schema validation fails; restore
  the file and the semantic check passes.
- Swap two Qwen model objects: schema passes; semantic identity and actual browser
  values fail; restore the file and both pass.
- Malformed JSON, HTML bytes, HTTP 404 and HTTP 200 HTML fallback are rejected;
  each restoration passes. Existing `check_pages.check_page` error/table checks
  run alongside the visible-result assertions.

The slice does not certify aggregate research results, calibration, clinical
correctness, lens validity, live deployment, unrelated pages, the full repository
suite, or sample-mode pages. A lens readout is not a transcript of thoughts; a token
score is not clinical correctness; a sample or missing result is not a finding.
Source inspection found an out-of-slice detail-page issue: `pct(0)` produces
`−0%` and wording gaps use `% probability` for an absolute difference. It remains
unfixed and has not been browser-certified by this index-only suite; the fixture
records the exact source location and trigger. Any behavior fix belongs in its own
frontend change with a detail-page regression.

## Review and activation order

1. Review the engine contract/client/black-box commit locally, then any separate
   extraction commit. The existing script entry points and production payloads
   remain compatible. No trigger, workflow, experiment pin or source receipt changes.
2. With later explicit push authorization, open an engine PR first and request
   `@codex review` per repository policy; address findings. Owner merges.
3. Review the frontend documentation and inactive workflow example. Existing site
   CI checks out engine `main` or an exact same-named branch with sparse paths
   `scripts`, `data`, `ops`, `docs`. Schemas/client stay under `scripts`; synthetic
   tests additionally need `tests/fixtures/frontend_boundary.json` and selected test
   modules. No schema file may be omitted from that sparse checkout.
4. Only after engine availability, propose separate activation of the manual CI
   example with an immutable engine SHA. It adds test-only Python/browser downloads
   and no inference. It must not replace either existing site check. Current active
   site workflow is untouched; the `.example` file has no Actions trigger effect.
   Hosted checks and deployment remain unrun. There is no site behavior to deploy
   for this slice, and no production data regeneration is required.

For future Civic Sample work, first identify and inspect its actual repository.
Reuse the procedure, not this domain schema: artifact schemas govern file
interchange; OpenAPI/client tests describe real HTTP resources; browser assertions
govern displayed behavior. Derive its own independent domain oracle. No Civic
Sample repository, endpoints or scientific claims were inspected or assumed here.

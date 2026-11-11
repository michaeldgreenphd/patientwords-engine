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

Prerequisites: Python 3.13, two local git checkouts, an isolated development venv with
[`requirements.lock`](../../scripts/boundary_client/requirements.lock), and Chromium.
The browser may be an already-installed executable; its actual version is recorded.
The run copies the site (about 1 GB with `modes/`) and about 230 MB of the engine into
the temporary directory and removes both on exit. It refuses to start when that file
system has less than twice the size of the copies free. Set `TMPDIR` to choose the
file system. To install only the separate test environment (network access is needed
for setup):

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
CLI in a sibling `patientwords-engine`/`patientwords` layout, copies the actual site,
and serves it under `/patientwords/` on an ephemeral `127.0.0.1` port. Source inputs,
exports, render pruning and mutations exist only in the temporary tree; its server
and files are cleaned on exit. The real exporter, HTTP transport and page JS are not
mocked. No inference is attempted. On the scenario index, the five ancillary JSON
fetches get explicit local substitutes from the fixture; no other study results enter
those page sections. Browser routing blocks every origin except the test server; the
client accepts only literal loopback and follows neither redirects nor environment
proxies. The only temporary HTML edit inserts a visible disclosure on each page the
browser loads; page JS and rendering remain the real consumer. The index has no
native sample mode.

## The temporary engine layout

The layout is derived on every run. It is not a list kept in the runner.

- **What it holds.** The runner reads the `sparse-checkout` block of the engine
  checkout step in the site's `.github/workflows/site_checks.yml` (today `scripts`,
  `data`, `ops`, `docs`). It copies those directories whole, plus the files at the
  engine's root. Root files are included because actions/checkout uses git's cone
  mode unless `sparse-checkout-cone-mode: false` is set, and cone mode always checks
  out root files. That statement comes from the documentation of actions/checkout
  and git. It was not observed on a hosted runner from this work. Of those paths the
  runner copies the files a commit of the working tree would hold: tracked, or
  untracked and not ignored. The code is
  [`scripts/boundary_client/layout.py`](../../scripts/boundary_client/layout.py).
- **Why a mirror and not a list.** Until 2026-11-10 the runner copied `scripts/` and
  one named file from `data/`. The validator later read
  `data/jev/legacy_frontend_reports.json` and the open-results policy, and on the
  branch of 2026-11-10 sixteen selected tests failed in that layout before the
  exporter ran. A list also fell short without failing: run under the probe below,
  the old layout was also asked for `ops/disclosure_log.jsonl` and `pyproject.toml`,
  and no test failed for lack of them. Those tests ran without two files that site CI
  has. A mirror gives the stages the files site CI gives them and has no list to
  maintain. Its cost is the 230 MB copy.
- **The one hand-kept list.** Site CI runs no pytest, so its checkout has no `tests/`.
  `TEST_SUPPORT` in the runner names the selected test modules, `tests/conftest.py`
  and the fixture. A listed file the checkout lacks is refused by name before any copy.
- **The run checks the layout.** Every subprocess in the layout (the selected tests,
  the exporter, the validator) runs with
  [`layout_probe.py`](../../scripts/boundary_client/layout_probe.py) loaded as
  `sitecustomize`. It records each path under the layout that a process opens, lists
  or tests for existence and does not find. After each stage the runner compares that
  record with the engine checkout. A path the checkout holds and the layout lacks stops
  the run with a `LayoutError` that names the path and the stage, before the stage's
  own exit code is read. A path no checkout holds, or one git ignores, is not an error.
  A selected test that looks for a file outside the layout therefore fails the run by
  name: add a test-only input to `TEST_SUPPORT`, or do not select that test.
- **The check is itself checked.** Each run asks, in the layout, for two files the
  checkout holds and the layout does not, once by an existence test and once by an
  open. The run fails unless both are named (`layout_absent_input_named`).
- **Limits of the probe.** It does not see a child process started with `-I`, `-E` or
  `-S`, a non-Python child, or a call made with a directory file descriptor. It does
  not record the import system's own lookups. A file missed that way still fails as a
  downstream assertion, not as a named file.

## Evidence and limits

A receipt binds actual engine/frontend HEADs,
dirty diff identity, fixture/schema/toolchain hashes, versions, normalized commands,
and results. `tracked_diff_sha256` hashes `git diff --binary HEAD` (staged and
unstaged tracked changes); untracked files have individual byte hashes. The receipt
itself is excluded to avoid circular identity. Paths in the receipt are repository
relative or placeholders, not private workstation paths.

The browser asserts exact two-decimal probabilities, shared 0–1 axis, gap sign
convention, row/target associations, model labels/provenance, outcome/search
filters, zero versus missing, untraced second-model rows, and legacy base fallback.
Independent semantics assert the full-vocabulary probability meaning, patient minus
clinical gap, and the summary described in the next section. These are fixture
expectations, not study findings; no empirical softmax computation occurs.
The real exporter also receives one more accepted synthetic input without a trace;
the browser must show “1 of 5 accepted scenarios are still tracing.”

### The repeated-phrase regression (2026-11-10)

Until 2026-11-10 `scripts/payload_summary.py` keyed phrases on a field the exporter's
rows do not carry, so every row counted as its own phrase. The fixture of that date
had no repeated phrase: its expected phrase count equalled its row count, and the
boundary passed on the defective producer. This was confirmed on 2026-11-10 by running
the earlier producer (`git c46db48f^:scripts/payload_summary.py`) in a scratch copy:
the earlier fixture's expectations accepted its output, and the current fixture's
reject it (`summary penalty n_phrases: expected 2, got 3`).

The fixture now has two batches. The second batch repeats the first batch's first
clinical prompt with a different patient prompt and a different measurement. The
expected summary is typed in the fixture, with the arithmetic in
`expected.summary.derivation`. No producer or validator code produced it:

| Field | Value | Arithmetic |
|---|---|---|
| `n_scored_rows` | 3 | rows with a numeric base-model penalty: −0.1468, 0, −0.0932; the fourth row is screened out |
| `mean_rows_raw` | −0.08 | (−0.1468 + 0 − 0.0932) / 3 |
| `n_phrases` | 2 | the two rows with the repeated prompt are one phrase |
| `mean_phrase_deduped` | −0.06 | repeated phrase (−0.1468 − 0.0932) / 2 = −0.12; other phrase 0; (−0.12 + 0) / 2 |
| `ci95` | null | the producer writes no interval below three phrases |

The pages print the phrase-level mean as a whole number of percentage points, so the
fixture is chosen to print 6 where the row mean would print 8, and 2 phrases where the
row count is 3. The values are asserted at three stages:

1. the exported file, before any transport (`exported_summary_penalty_matches_hand_calculation`);
2. the HTTP client's oracle, `assert_semantics` in
   [`assertions.py`](../../scripts/boundary_client/assertions.py), which also requires
   the repeated prompt on exactly the two expected rows, in different batches;
3. the browser: `#hero-caveat` on the home page and `#word-caveat` on
   `wording-differences/`, each compared with a full sentence typed in the fixture
   (`browser_summary_sentences_phrase_count_and_mean`). Until 2026-11-11 the home page
   printed the summary twice and a third sentence, `#sim-stat`, was compared; the page now
   states it once.

The home page and the wording-differences page are loaded for those two sentences
only. Their other sections show the site's own published content, and the temporary
disclosure on them says so. The fixture distinguishes these wrong rules from the
right one: every row its own phrase, phrases keyed on the patient prompt, deduplication
within a batch only, and keeping only the first or the last occurrence. It does not
distinguish phrases keyed on the clinical term or the target token; both give the
same numbers on this fixture. The interval is null in this fixture, so a non-null
`ci95` is not exercised here.

### Recorded runs

The committed [receipt](frontend_boundary_receipt.json) is the record of the run of
2026-10-16 at engine `ef22c7b9`: 14 checks, including 287 affected offline cases in the
layout of that date. It is kept as written and describes that tree, not today's.

The run of 2026-11-10 (Python 3.13.18, the locked packages, an installed Chromium
153.0.8010.12 passed with `--browser`) passed 21 checks on the working tree of that
date. The seven added checks are `layout_mirrors_site_ci_sparse_checkout`,
`layout_absent_input_named`, `exported_summary_penalty_matches_hand_calculation`,
`browser_summary_sentences_phrase_count_and_mean`,
`summary_penalty_wrong_phrase_count_and_mean`, `summary_penalty_pre_correction_form`
and `layout_complete_for_every_stage`. Its receipt was written outside the repository
and is not committed: it binds a working tree with uncommitted changes. A receipt
includes each deliberate rejection and restored pass, the skipped tests with their
reasons, browser errors and attempted external requests. Generated-model regeneration
was byte-identical. Hosted tests remain unrun. Since 2026-11-11 the paired job of
`.github/workflows/pr_checks.yml` runs the boundary on engine pull requests; that
workflow had not run on a hosted runner on that date.

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
- Set `summary.penalty` to a phrase count of 5 and a phrase-level mean of 0.25: the
  schema passes; the contract validator's recomputation rejects both fields and exits
  1; the fixture oracle rejects it; restore the file and both pass. The values are not
  the pre-correction form, so the validator's dated transition does not apply. The
  validator is run as `check_simulated` in the layout with the CLI's exit rule. The
  CLI itself checks every artifact of a site against the engine's records; on a site
  holding only the synthetic payload it reported 37 unrelated errors (2026-11-10), so
  its exit code could not show what rejected the payload.
- Set `summary.penalty` to the pre-correction form (phrase count 3, phrase-level mean
  −0.08, an interval over the three rows): the fixture oracle rejects it and the three
  pages' sentences print 3 and 8 and fail the expected text; restore the file and all
  pass. The validator notes this form through 2026-12-15 and rejects it afterwards;
  the receipt records which of the two it did, and the check requires neither.
- Ask for two files outside the layout: the run names both (see the layout section).
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
   tests additionally need the files in the runner's `TEST_SUPPORT` (the selected test
   modules, `tests/conftest.py` and `tests/fixtures/frontend_boundary.json`). No
   schema file may be omitted from that sparse checkout. The runner reads the file
   list from git, so the engine must be a git checkout.
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

# Experiment comparison page and its preview check

Written 2026-11-10. The site has a page that lists experiment comparisons and displays one
(`experiments/index.html`, titled "Compare methods"), and one command checks that the page
renders a synthetic bundle faithfully. The check passed locally on 2026-11-10: 37 checks,
0 failed. It had 28 checks before the page was reorganised the same day; each of the 28
has an equivalent and 9 were added. It is a software check on hand-written numbers. It
loads no model, measures nothing and publishes nothing. No study bundle exists yet, so the
published index lists nothing.

| Piece | Where |
|---|---|
| Page | `experiments/index.html` in the site repository (`../patientwords`) |
| Index the page lists | `data/experiments/index.json` in the site repository |
| Index writer | `scripts/export_experiment_index.py` |
| Index schema and contract check | `scripts/contracts/experiment_index.v1.schema.json`, `scripts/experiment_index_contract.py` |
| Preview check | `scripts/check_experiment_preview.py` |
| Tests | `tests/test_check_experiment_preview.py`, `tests/test_experiment_index.py` |
| Bundle writer | `scripts/experiments/bundle.py`, described in [the interface README](README.md) |

## Run it

From the engine checkout, with the site checkout beside it and a Chromium executable:

```sh
python scripts/check_experiment_preview.py --site ../patientwords --browser "$CHROMIUM" --receipt /tmp/experiment-preview.json --shots /tmp/experiment-preview-shots
```

`--browser`, `--receipt` and `--shots` are optional. Without `--browser` the script uses
the `CHROMIUM` environment variable, then Playwright's own browser. It needs the
`playwright` Python package. Exit 0 means every check passed. Exit 1 means a check
failed. Exit 2 means the check could not run (no Chromium, no page, no
`data/experiments/index.json` in the site, a failed command-line step); that is a blocked
check, not a pass.

What the command does:

1. Copies the site to a temporary directory. `.git`, caches and `modes/` are left out;
   `modes/` is 941 MB and the page references nothing in it.
2. Runs the real experiment command line: validate, plan, a run stopped after 5 tasks, a
   resumed run, collect, compare, bundle. The protocol it runs is
   `tests/fixtures/experiments/protocol_synthetic_ica.json` with the prompt-text marker
   (see *Prompt text*) added to `fam-1` and `fam-2`, written in the temporary tree. The
   committed fixture file is not changed. `fam-3` stays unmarked, so one bundle shows both
   the exported-text state and the missing-text state.
3. Copies the finished bundle, as a plain file, into the copy's
   `data/experiment_preview/bundle.json`. The command line itself refuses that path:
   it refuses any output path with a `data` component. The check runs that refusal as
   a control.
4. Serves the copy over HTTP on an ephemeral loopback port under `/patientwords/` and
   opens `experiments/index.html` in Chromium, with and without an address parameter. The
   page's JavaScript is the real file, unedited. Requests to any other origin are
   blocked and counted; the count must be zero.
5. Runs the real index writer on the copy twice (see *The index*), restoring the copied
   index after each.
6. Removes the temporary tree. The real site and both checkouts are not written to; the
   SHA-256 of the real site's index is compared before and after.

## What the page shows

With no address parameter the page requests one file, `data/experiments/index.json`, and
lists every comparison in it as a link. When the list is empty it says "No experiment
comparisons published yet" and offers two routes: the results catalogue (`../results/`)
and the methods page (`../methods.html`). That statement and both links are static HTML,
so a reader without JavaScript sees them. If the index cannot be read the page says so and
shows no comparison.

With a comparison chosen, the page renders one bundle in this order:

1. **About this comparison.** The synthetic marker when the bundle is synthetic
   ("synthetic fixture - not a measurement"), then five labelled values: model, evidence
   class, clinical review, *Included in analysis*, *Study version*. Visibility is added
   when it is not plain `public`. Each label names its schema field in its `title`. One
   fold, closed on load, holds the shared context as recorded: every evidence label under
   its schema field name, the protocol, the model and the tokenizer.
2. **Cases.** One paragraph states once what the target-token probability is, with its
   unit, its denominator and the statement that no uncertainty was computed. A fold
   explains the ranks and the ICA quantities. Then one block per case, in one reading
   order:
   1. *Paired wording.* One row per wording with the prompt text when the bundle exports
      it, or "prompt text is not in this bundle". A fold holds the prompt SHA-256, the
      SHA-256 of the token ids and the token count. A case joined to a legacy row names
      the row and links to the results catalogue.
   2. *Recorded model output.* The target-token probability of each wording as one dot on
      a common axis from 0 to 1, one row per wording, the value printed at its dot and
      the token's vocabulary rank beside it. A small table gives the signed difference
      per comparison with the higher wording in words.
   3. *Internal measurements.* Readout ranks, one row per wording, layer and target, raw
      and filtered rank side by side. ICA: one table with a signed component score and a
      squared-coordinate share per wording in separately labelled columns, then the signed
      score difference per comparison. A method that was not computed is one line with its
      run status and a link to its reason.
   4. *Intervention evidence*, or "no intervention in this bundle".
3. **Run status.** Every planned method with its run status, reason and capability row.
4. **Methods & source.** The schema term of each reader-facing label, planned tasks and
   run counts, external links, source hashes, limitations.

Each value is printed once. A wording that sits in two comparisons is recorded by both
comparison blocks; the page prints it in the row of the wording, and when the two records
differ it prints neither and says "two comparison blocks record different values".

No quantity is combined with another. A probability, a rank, a component score and a
review label keep their own columns and units; the page adds and averages nothing.

Where a bundle does not carry a value the page prints a dash and "not in this bundle" in
that place. It fills nothing in.

### Labels and the schema terms they stand for

The page uses reader-facing labels. The schema terms stay on the page, in *Methods &
source* and under the values in *About this comparison*.

| Label on the page | Schema term | Bundle fields |
|---|---|---|
| Compare methods | method-comparison bundle | the file, `patientwords.experiment-bundle/1` |
| Cases | case families | `protocol.families`, `comparisons[].family_id` |
| Run status | execution state | `execution.by_state`, `methods_not_run[].states` |
| Included in analysis | analysis membership | `evidence.analysis_memberships` |
| Study version | analysis pin | `protocol.id`, `protocol.version`, `protocol.sha256` |
| Methods & source | provenance | `provenance`, `plan_totals`, `execution` |
| Target-token probability | `behavior_next_token` / `full_vocab_probability` | `comparisons[].comparisons[].behavior` |

"Target-token probability" is the model's next-token probability of the first encoded
token of the target, over the full vocabulary. The page says this once. It is never
labelled answer accuracy, clinical risk or patient understanding; the check fails if a
heading or a column head uses one of those words. For ICA, a "signed component score" and
a "squared-coordinate share, not a probability" are separate columns with those words in
their heads, on wide and narrow screens.

### Stable ids and links

These ids are kept so that existing links and `scripts/check_pages.py` keep working:
`evidence`, `protocol`, `families`, `methods`, `totals`, `links`, `provenance`,
`limitations` (section anchors), `exp-idle`, `exp-state`, `exp-results`, `exp-evidence`,
`exp-protocol`, `exp-families`, `exp-methods-body` (the run-status table body, listed in
`JS_TABLE_BODIES` of `scripts/check_pages.py`), `exp-totals`, `exp-links`,
`exp-provenance`, `exp-limitations`, `exp-fam-toggle`. New ids: `exp-index`,
`exp-index-list`, `exp-index-count`, `exp-empty`, `exp-empty-head`, `exp-guide`,
`exp-terms`, `exp-endpoint-unit`. `#protocol` is now a fold inside `#evidence`; a link to
it opens the fold. `#totals`, `#links` and `#limitations` are parts of `#provenance`.
The loaded state has a plain link that downloads the bundle file.

## Address parameter (developer reference)

Readers follow links from the list. The syntax below is not shown on the page.

```text
experiments/index.html?bundle=<relative path under data/>
```

The page fetches `../data/<path>` and renders it when it is one
`patientwords.experiment-bundle/1` document. It refuses the value, makes no request and
shows a short refusal with a link back to the list when the value:

- is empty, or is longer than 200 characters;
- has a scheme (`https:`, `javascript:`, `data:` and so on);
- is an absolute path (starts with `/` or `\`);
- contains `..`;
- has a character outside `A-Z a-z 0-9 . _ - /`;
- has an empty path segment or one that starts with a dot;
- does not end in `.json`;
- or when the address has more than one `bundle` parameter.

The rule is `bundleRefusal` in the page. `bundle_param_refusal` in
`scripts/check_experiment_preview.py` mirrors it, and the browser run compares the two on
19 cases. The index writer (`addressable`) and the contract check (`page_accepts`) state
the same rule for a path; `tests/test_experiment_index.py` compares all three on one table.

## The index

`data/experiments/index.json` (`patientwords.experiment-index/1`) is what the page lists.
It is written by one command and is never edited by hand:

```sh
python scripts/export_experiment_index.py --site ../patientwords
```

The writer scans every `.json` file under the site's `data/` for a bundle. A bundle is
listed only when its own evidence block says it may be published:

- it is not synthetic (`evidence.synthetic` and `protocol.synthetic` are false, the
  evidence class is not `synthetic_fixture`, the limitations do not say
  `synthetic_not_measurement`);
- `evidence.visibility` is `public` and `evidence.restriction_reasons` is empty;
- it validates against `schemas/experiments/bundle.v1.schema.json`;
- its path under `data/` passes the address rule above.

Every other bundle file is named under `not_listed` with its reasons and is not linked. If
a listed bundle exports prompt text, each exported prompt is asked of the holdout seal
again before the bundle is listed; a restricted text, or a seal that cannot be evaluated,
stops the writer with exit 2 and nothing written. Each entry carries the SHA-256 of the
bundle file and labels copied from it. The index holds no prompt text and no measurement.
It carries a `_provenance` stamp (generator, engine commit, UTC time).

`scripts/experiment_index_contract.py` has `check_experiment_index(rep, site)` for the
site contract validator. It fails when the index is missing while the page exists, does
not match its schema, lists a file that is absent, omits a publishable bundle, carries a
hash or a label that is not the bundle's, or when any bundle under `data/` may not be
published (synthetic, not `public`, or restricted), listed or not. It is written without
importing the writer and reads nothing outside `scripts/`, because site CI checks out
`scripts/`, `data/`, `ops/` and `docs/` of the engine and not `schemas/`.

On 2026-11-10 the site's index was written by the command above and lists nothing:
0 bundle files under `data/`, 0 listed, 0 not listed.

## Prompt text

A bundle holds prompt hashes. It holds prompt text only through one explicit export:

1. The protocol marks a family by putting the string
   `publication:prompt_text_approved` in that family's `facts` list. The marker is part
   of the protocol, so it is part of the protocol hash that every task is bound to.
2. `python -m scripts.experiments.cli bundle --run-dir RUN --out FILE --protocol PROTOCOL`
   is given the protocol the plan was built from. Without `--protocol` no text is written.
3. `scripts/experiments/bundle.py` then writes `protocol.families[].variant_text.<variant>`
   (`prompt`, `prompt_sha256`) and `protocol.families[].prompt_text_export` for each
   marked family, after these checks: the protocol's digest is the plan's
   (`protocol_mismatch`); each prompt's SHA-256 is the hash the plan's tasks record
   (`prompt_hash`); for a non-synthetic protocol the evidence block says `public` with no
   restriction reason (`prompt_text_restricted`) and the holdout seal, asked again at
   export time for the legacy row and for every variant prompt, restricts nothing
   (`holdout_refusal`; a seal that cannot be evaluated is exit 3 and nothing is written).
   A refusal names the family and the variant and never repeats text.

A family without the marker, an excluded family and every bundle built without
`--protocol` have no `variant_text`; the page then shows "prompt text is not in this
bundle". `variant_inputs` is unchanged and stays closed. Target text is not exported.

A synthetic protocol's placeholder text is exported under the same marker with no seal
check, as protocol validation applies none to a synthetic protocol. The bundle stays
`synthetic_fixture` and `not_published`, and the page says the text is placeholder text of
a synthetic fixture.

The marker sits in `facts` because the protocol schema is closed and
`scripts/experiments/protocol.py` has no field for a publication approval; `facts` is the
one per-family list of strings the validator accepts without a change. No code reads
`facts` for any other purpose on 2026-11-10. A dedicated field would be clearer; it needs
a change to `schemas/experiments/protocol.v1.schema.json` and `protocol.py`.

A case that is joined to a legacy row (`legacy_join`) is also shown with its batch and
index and a link to the results catalogue, where an unsealed row is published with its
wording. That reference copies no text into the bundle.

## What the check verifies

| Check | Compared against |
|---|---|
| Empty state | with the site's own index: the statement "No experiment comparisons published yet", the two routes, no entry, exactly one data request (the index), no bundle request, no address syntax in the visible text |
| Index never lists the synthetic bundle | the real writer run on the copy that holds the synthetic bundle: 0 listed, the bundle under `not_listed` with `synthetic`; the page shows the empty statement and no link; the contract check reports the bundle as an error in the copy |
| Index lists a publishable bundle | a copy of the fixture bundle relabelled as publishable, written in the temporary tree only: the writer lists it and not the synthetic one; the page shows one link; Enter on the link opens the file; it renders with no synthetic marker and no prompt text |
| Forged or unreadable index | a hand-made index in the copy that names the synthetic bundle, a non-public entry and a path the address rule refuses: the page links none and says entries are not shown. An index of another schema version: the page says the list could not be read and does not say the list is empty. |
| Target probabilities and signed differences | the softmax of `tests/fixtures/experiments/behavior_logits.json`, recomputed in the script. Not read from the bundle. Each difference row names its two wordings, and the rows of those wordings must show the fixture's values. |
| Dot plot | every dot's value equals the bundle's recorded value and the recomputed softmax; the dot's centre, measured in the browser, is at that fraction of its track to within 1 CSS px; the axis labels are 0, 0.5 and 1; all rows of a panel share the axis; the label at the dot is the value to four decimals |
| ICA scores, differences and shares | a literal table in the script, worked by hand from the toy basis. A unit test fails if it stops agreeing with the fixture builder's table. Column heads and narrow-layout labels must say "signed component score" or "squared-coordinate share", never both. |
| ICA basis hash shown | `tests/fixtures/experiments/ica/fixture_index.json` |
| Prompt SHA-256, token-id SHA-256 and token count of every variant | the protocol that was run. Not read from the bundle. |
| Prompt text | a marked family shows exactly the protocol's text with the basis line; an unmarked family reads "prompt text is not in this bundle" and none of its prompt strings is anywhere on the page; no target text is on the page |
| Reader labels | the six labels are shown; the retired headings are not headings or column heads; the schema term of each label is in *Methods & source*; the first-token explanation appears once; no heading uses "accuracy", "risk", "understanding", "combined", "composite" or "overall" |
| ICA preprocessing mode | the `basis.preprocessing` of the protocol's `ica_lens` block. The adapter completes a task only when its payload records that mode. |
| Attempts executed and results reused | the sums of `executed` and `reused` over the `run-fixture` summaries the command line printed in step 2 (27 and 5). Not read from the bundle. |
| Methods listed, with run status | the method list of the protocol; three completed, `j_lens` unsupported, `jpp` unavailable, each with the bundle's reason. Each case states the status and links to the reason in the Run status table; the check follows the link to the row. |
| Protocol, model and tokenizer identity; planned task count | the protocol that was run |
| Readout ranks and top-k wording | the bundle itself: every side of every comparison block against the row of its wording. This is rendering fidelity only. The script has no independent readout oracle. |
| Synthetic label and clinical review | the label is present once in *About this comparison*, once per case, once at the Run status table; each case heading, open or closed, shows its clinical-review status |
| States | idle, loading, missing, error, refused and loaded each carry a different word and a different box style. A zero difference reads `0` with "no difference"; a missing value reads as a dash with words. |
| Requests | no console error, no failed request, exactly one data request for a rendered bundle |
| Address rule | the page's rule and its Python mirror give the same answer on 19 cases |
| Stable ids and links | the ids listed above exist; the section links are the five listed; the download link resolves to the bundle file; `#protocol` opens its fold |
| Layout and keyboard | no horizontal overflow at 1280 px and 390 px; Tab reaches the section links; folds, the case button and the index link work from the keyboard |

Deliberate defects, each followed by a restored pass:

| Defect served | Required result |
|---|---|
| `schema_version` changed to `.../2` | error state naming both strings; no part of the bundle rendered |
| Bundle file deleted | missing state with "HTTP 404" |
| A method's state counts, another's payload records and their block states removed | "state not recorded" for both; neither reads "completed" |
| The fields added on 2026-11-10 removed, as in a bundle written before them | the page renders in full with the synthetic label beside every case; no prompt text of any family is on the page; the hash, token-count, preprocessing, executed and reused places each read "not in this bundle"; the vocabulary size reads "not in this bundle"; the check of those values fails on this copy |
| `?bundle=../data/experiment_preview/bundle.json`, literal and percent-encoded, and two `bundle` parameters | refused in two short lines with a link to the list; no request beyond the page; no address syntax shown. Without the rule the first two would reach the served bundle. |
| One probability and one ICA score sign changed | the value checks and the dot check fail |
| Two comparison blocks record different values for one wording (probability, readout rank, ICA score) | each of the three cells says "two comparison blocks record different values"; no dot is drawn; neither value is shown |

Link records are checked with records built by
`scripts/experiments/neuronpedia.py` from its fixture registry: a verified, built
record becomes a link; an unverified alias shows its reason and local record; an
alias record with a link string pasted in, and a verified record whose link is not an
`https` URL, show no link.

## What it does not verify

- No model was loaded. The "original model output" in this bundle is the softmax of
  hand-chosen logits. Nothing here is evidence of parity with a real model.
- No measurement. The receipt says `"evidence": "local synthetic software test only"`.
- No deployed site. The page was served from a local copy, not from GitHub Pages.
- No real bundle. None exists, so no real bundle has been rendered. The non-synthetic
  rendering path is exercised only by a relabelled copy of the fixture.
- No real seal check. The prompt-text export of a non-synthetic protocol and the index
  writer's seal check are tested with stub seal functions. No sealed text was read.
- One browser: Chromium 153. No other browser and no assistive technology was run.
  The ARIA roles and the keyboard path were checked by script, not with a screen reader.
- Readout values have no independent oracle here (see the table).
- The page does not validate a bundle against `schemas/experiments/bundle.v1.schema.json`.
  It checks the schema string and the presence and type of the blocks it reads.
- A bundle with many cases: every case is rendered into the page. There is no paging.
  Measured 2026-11-10 with the fixture's three cases at 1280 px: 6,386 CSS px with the
  first case open, 10,766 with all open; the first case starts 824 px from the top. At
  390 px: 14,311 and 26,933. The narrow layout is long because every table row becomes a
  block.
- The dot plot's colours. The three marks use the site's fixed palette (clinical green,
  patient ink, a hollow ink ring). The dataviz palette validator fails the ink on its
  lightness-band and chroma checks and passes it on colour-vision separation and
  contrast. Each row prints the wording's name, so colour is never the only cue.

## Findings from building it

1. **An exact tie can arrive as one rounding step.** In the fixture,
   `fam-2 / colloquial_vs_normalized / c1` is 1/16 against 1/16. The bundle records the
   difference as `1.39e-17`, because the two softmax results differ in the last bit.
   `scripts/experiments/compare.py` subtracts the recorded values, as its contract
   says (signed, raw). The page prints `+1.39e-17` and "colloquial higher, below the 4
   decimals shown". It applies no tolerance of its own. The check accepts either `0`
   or a value below `1e-12` in that form for a row that is an exact tie in exact
   arithmetic, and lists such rows in the receipt. Open point for the bundle contract:
   it has no field that says what difference is resolvable.
2. **An unread 404 body kept the request open.** The first version of the page did not
   read the body of a failed response. Chromium then never reported the request as
   finished, and a wait for network idle timed out. The page now reads the body before
   it acts on the status. Reproduced with a 5 second wait in a scratch script. Inferred,
   not run: `scripts/check_pages.py` waits for network idle on `goto`, so it would have
   reported the old page as a navigation timeout instead of a missing data file. With
   the fix it reports the 404 as a failed data request (run 2026-11-10).
3. **`patientwords.experiment-bundle/1` did not carry four things the page has a place
   for.** Prompt hashes and token counts per variant, the ICA preprocessing mode, and the
   count of reused results. They were added on 2026-11-10; see the next section. The page
   printed "not in this bundle" for each and still does for a bundle without them.
4. **The bundle contract does not say where a link record sits.** The page reads a
   record of the `link_or_fallback` shape from a comparison's `references.<key>.neuronpedia`
   and from an ICA component's `neuronpedia`. That placement is this page's reading,
   not a contract.

## Fields added to bundle version 1

Added on 2026-11-10 by `scripts/experiments/bundle.py` and `scripts/experiments/compare.py`.
The schema version string is unchanged. Each field is optional in
`schemas/experiments/bundle.v1.schema.json`, so a bundle written before the change still
validates and a reader that ignores the fields is unaffected.

| Field | Content | Source |
|---|---|---|
| `protocol.families[].variant_inputs.<variant>` | `prompt_sha256`, `token_sha256`, `n_tokens`. The entry is closed: it cannot hold text. | the plan's tasks (`spec.input` and `estimate.tokens`). `protocol.families[].variants` stays the list of names it was. |
| `comparisons[].comparisons[].ica.preprocessing_mode`, `.preprocessing_read_from` | the mode the ICA adapter read from the saved artifact, and where in the artifact it read it | the two ICA payloads' `basis` record. Null when the payloads do not record it; two payloads under one basis hash that record different modes refuse `preprocessing_mismatch`. |
| `execution.counts.executed_attempts`, `.reused_events` | the number of `started` lines and of `reused` lines in the run directory's journal | the journal, read when the bundle is built. A task found complete by two later runs counts as two reuse events. |

Added later the same day, also optional:

| Field | Content | Source |
|---|---|---|
| `protocol.families[].variant_text.<variant>`, `protocol.families[].prompt_text_export` | the prompt text of a family the protocol marks, and the basis of the export | the protocol passed with `bundle --protocol`; see *Prompt text* |
| `comparisons[].comparisons[].behavior.vocabulary_size` | the number of tokens the target-token probability is taken over | the two behaviour payloads, which must agree on it |

Limits: a family the protocol excludes has no task in the plan and therefore no
`variant_inputs` and no `variant_text`; the page prints "not in this bundle" for its
hashes. The counts are of journal lines, so a journal with an unparseable line undercounts
(the collector reports such lines).

`execution.completed_under_superseded_inputs` was added the same day for the run store
([README.md](README.md), *Identity, attempts and replicates*). The page does not render
that list; the bundle's limitation
`completed_results_under_superseded_inputs_not_counted_see_execution` is shown with the
other limitations.

## Maintenance costs

- The address rule exists twice: `bundleRefusal` in the page and `bundle_param_refusal`
  in the script. The browser run compares them on every case, so a change to one
  without the other fails the check. Offline, only the Python copy is tested.
- The address rule for a path exists twice more: `addressable` in the index writer and
  `page_accepts` in the contract check. `tests/test_experiment_index.py` compares them with
  the mirror on one table.
- The script holds the page's visible strings as constants, the three "not in this bundle"
  sentences, the empty statement and the reader labels among them. A wording change on the
  page needs the same change in the script; `tests/test_check_experiment_preview.py` fails
  offline when a string, a stable id, or one of the bundle field names the page reads is
  missing from the page source.
- The prompt-text marker is a literal in `scripts/experiments/bundle.py` and in the check.
  A unit test fails when they differ.
- The expected method states and the ICA table are specific to the fixture protocol.
  A change to the fixture needs a change here.
- `exp-methods-body` is in `JS_TABLE_BODIES` of `scripts/check_pages.py`. The page with no
  parameter reports `0/hidden` for it and passes (checked 2026-11-10). `check_pages.py`
  fails a 404 under `data/`, so the site must hold `data/experiments/index.json`.

## How a real bundle would become publishable

This script is not that path. It writes a fixture into a temporary copy and deletes it.

A real bundle would need, in order:

1. A real run. Nothing in `scripts/experiments/` loads a model in this milestone, and
   paid or networked work runs only through push-to-run CI (`AGENTS.md`, *Execution
   model*).
2. The [open-results policy](../open_results_policy.md). A bundle's `evidence` block
   uses the policy's fields. A fixture says `synthetic_fixture` and `not_published`. A
   real bundle is shared when its artifacts are intact and no named restriction
   applies. Protocol validation refuses a family joined to a sealed Tier B row
   (`holdout_refusal`), and bundle version 1 holds no prompt text and no target text.
3. A reviewed exporter that writes the bundle into the site's `data/`. The experiment
   command line cannot do it: it refuses a path with a `data` component by design.
   The exporter belongs with the other site writers, with a row in
   `scripts/README.md`, a row in the site's writer table
   (`docs/agent_reference.md` there), and a line in the site's `DATA_LICENSE.md`,
   which names data files and directories one by one. `data/experiments/` is the
   expected directory. That exporter does not exist yet.
4. The index. `python scripts/export_experiment_index.py --site ../patientwords` is run
   after the bundle file is in place. It lists the bundle only when the bundle's evidence
   block allows it (see *The index*), and the site contract check then compares the index
   with the files.
5. The existing gates on the result: `scripts/seal_check.py` over the site (it scans
   `.json` and `.html`), `scripts/claim_check.py` for any number stated in page prose,
   the contract validator and `scripts/check_pages.py`. `verify.md` has the commands
   and the paired publication gates.
6. A decision on how a reader reaches the page. It is not in the site navigation and
   carries `noindex`.

# Experiment bundle preview

Written 2026-11-10. The site has a viewer page for experiment bundles, and one command
checks that the page renders a synthetic bundle faithfully. The check passed locally on
2026-11-10: 26 checks, 0 failed. It is a software check on hand-written numbers. It loads
no model, measures nothing and publishes nothing. No study bundle exists yet.

| Piece | Where |
|---|---|
| Viewer page | `experiments/index.html` in the site repository (`../patientwords`) |
| Check | `scripts/check_experiment_preview.py` |
| Tests | `tests/test_check_experiment_preview.py` |
| Bundle writer | `scripts/experiments/bundle.py`, described in [the interface README](README.md) |

## Run it

From the engine checkout, with the site checkout beside it and a Chromium executable:

```sh
python scripts/check_experiment_preview.py --site ../patientwords --browser "$CHROMIUM" --receipt /tmp/experiment-preview.json --shots /tmp/experiment-preview-shots
```

`--browser`, `--receipt` and `--shots` are optional. Without `--browser` the script uses
the `CHROMIUM` environment variable, then Playwright's own browser. It needs the
`playwright` Python package. Exit 0 means every check passed. Exit 1 means a check
failed. Exit 2 means the check could not run (no Chromium, no viewer page, a failed
command-line step); that is a blocked check, not a pass.

What the command does:

1. Copies the site to a temporary directory. `.git`, caches and `modes/` are left out;
   `modes/` is 941 MB and the viewer references nothing in it.
2. Runs the real experiment command line on the fixture protocol
   `tests/fixtures/experiments/protocol_synthetic_ica.json`: validate, plan, a run
   stopped after 5 tasks, a resumed run, collect, compare, bundle. The outputs go to a
   work directory in the temporary tree.
3. Copies the finished bundle, as a plain file, into the copy's
   `data/experiment_preview/bundle.json`. The command line itself refuses that path:
   it refuses any output path with a `data` component. The check runs that refusal as
   a control.
4. Serves the copy over HTTP on an ephemeral loopback port under `/patientwords/` and
   opens `experiments/index.html?bundle=experiment_preview/bundle.json` in Chromium. The
   page's JavaScript is the real file, unedited. Requests to any other origin are
   blocked and counted; the count must be zero.
5. Removes the temporary tree. The real site and both checkouts are not written to.

## What the page shows

With no `bundle` parameter the page makes no data request and states three things: it
displays method-comparison bundles exported by the engine's experiment interface; no
study bundle is published yet; synthetic fixtures are never published.

With `?bundle=<relative path under data/>` it fetches that one file and renders, in the
reader's order:

1. The evidence class, clinical-review status, visibility and analysis memberships. A
   synthetic bundle carries the text "synthetic fixture - not a measurement" there,
   beside every case family and beside the methods table.
2. Protocol id and version, model and tokenizer identity with revisions.
3. Each case family: the variants; the original model output (the target's
   full-vocabulary next-token probability per variant, and the signed difference per
   comparison with the sign in words); the internal analyses the bundle holds (readout
   ranks with raw and filtered rank side by side, ICA component scores under one basis
   with shares labelled "squared-coordinate share, not a probability"); intervention
   evidence, or "no intervention in this bundle".
4. A table of every planned method with its execution state and reason in words.
5. Plan totals, execution counts, external links, provenance hashes, limitations.

The page refuses a `bundle` value that is absolute, has a scheme, contains `..`, has a
character outside `A-Z a-z 0-9 . _ - /`, or does not end in `.json`. It says so and
makes no request.

## What the check verifies

| Check | Compared against |
|---|---|
| Target probabilities and signed differences | the softmax of `tests/fixtures/experiments/behavior_logits.json`, recomputed in the script. Not read from the bundle. |
| ICA scores, differences and shares | a literal table in the script, worked by hand from the toy basis. A unit test fails if it stops agreeing with the fixture builder's table. |
| ICA basis hash shown | `tests/fixtures/experiments/ica/fixture_index.json` |
| Methods listed, with state | the method list of the fixture protocol; three completed, `j_lens` unsupported, `jpp` unavailable, each with the bundle's reason |
| Protocol, model and tokenizer identity; planned task count | the fixture protocol file |
| Readout ranks and top-k wording | the bundle itself. This is rendering fidelity only. The script has no independent readout oracle. |
| Synthetic label | present once in the evidence section, once per family, once at the methods table |
| States | idle, loading, missing, error, refused and loaded each carry a different word and a different box style. A zero difference reads `0` with "no difference"; a missing value reads as a dash with words. |
| Requests | no console error, no failed request, exactly one data request for a rendered bundle, none with no parameter |
| Address rule | the page's rule and its Python mirror give the same answer on 19 cases |
| Layout and keyboard | no horizontal overflow at 1280 px and 390 px; Tab reaches the section links; folds and the family button work from the keyboard |

Deliberate defects, each followed by a restored pass:

| Defect served | Required result |
|---|---|
| `schema_version` changed to `.../2` | error state naming both strings; no part of the bundle rendered |
| Bundle file deleted | missing state with "HTTP 404" |
| A method's state counts, another's payload records and their block states removed | "state not recorded" for both; neither reads "completed" |
| `?bundle=../data/experiment_preview/bundle.json`, literal and percent-encoded, and two `bundle` parameters | refused; no request beyond the page. Without the rule the first two would reach the served bundle. |
| One probability and one ICA score sign changed | the value checks fail |

Link records are checked with records built by
`scripts/experiments/neuronpedia.py` from its fixture registry: a verified, built
record becomes a link; an unverified alias shows its reason and local record; an
alias record with a link string pasted in, and a verified record whose link is not an
`https` URL, show no link.

Three broken copies of the page were also run by hand on 2026-11-10 (changed label
text, address rule removed, zero printed as empty). Each exited 1. That run is not
part of the script.

## What it does not verify

- No model was loaded. The "original model output" in this bundle is the softmax of
  hand-chosen logits. Nothing here is evidence of parity with a real model.
- No measurement. The receipt says `"evidence": "local synthetic software test only"`.
- No deployed site. The page was served from a local copy, not from GitHub Pages.
- No real bundle. None exists, so no real bundle has been rendered.
- One browser: Chromium 153. No other browser and no assistive technology was run.
  The ARIA roles and the keyboard path were checked by script, not with a screen reader.
- Readout values have no independent oracle here (see the table).
- The page does not validate a bundle against `schemas/experiments/bundle.v1.schema.json`.
  It checks the schema string and the presence and type of the blocks it reads.
- A bundle with many families: every family is rendered into the page. There is no
  paging. Three families make a page about 12,600 CSS px tall at 1280 px with all
  families open.

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
3. **`patientwords.experiment-bundle/1` does not carry four things the page has a
   place for.** Prompt hashes and token counts per variant, the ICA preprocessing mode,
   and the count of reused results. The page prints "not in this bundle" for each. The
   plan and the run store hold all four; adding them is a change to
   `scripts/experiments/bundle.py` and its schema.
4. **The bundle contract does not say where a link record sits.** The page reads a
   record of the `link_or_fallback` shape from a comparison's `references.<key>.neuronpedia`
   and from an ICA component's `neuronpedia`. That placement is this page's reading,
   not a contract.

## Maintenance costs

- The address rule exists twice: `bundleRefusal` in the page and `bundle_param_refusal`
  in the script. The browser run compares them on every case, so a change to one
  without the other fails the check. Offline, only the Python copy is tested.
- The script holds the page's visible strings as constants. A wording change on the
  page needs the same change in the script; `tests/test_check_experiment_preview.py`
  fails offline when a string is missing from the page source.
- The expected method states and the ICA table are specific to the fixture protocol.
  A change to the fixture needs a change here.
- `exp-methods-body` is not in `JS_TABLE_BODIES` of `scripts/check_pages.py`. Until it
  is, that script does not notice an empty methods table on this page. With it added,
  the page with no parameter reports `0/hidden` and passes (checked 2026-11-10).

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
   (`docs/agent_reference.md` there), a shape entry in `check_shapes` of
   `scripts/validate_frontend_contract.py`, and a line in the site's `DATA_LICENSE.md`,
   which names data files and directories one by one.
4. The existing gates on the result: `scripts/seal_check.py` over the site (it scans
   `.json` and `.html`), `scripts/claim_check.py` for any number stated in page prose,
   the contract validator and `scripts/check_pages.py`. `verify.md` has the commands
   and the paired publication gates.
5. A decision on how a reader reaches the page. It is not in the site navigation and
   carries `noindex`. The site README's page map does not list it.

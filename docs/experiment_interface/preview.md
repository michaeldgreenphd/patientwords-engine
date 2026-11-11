# Experiment comparison page and its preview check

Written 2026-11-10, revised 2026-11-11. The site has a page that lists experiment
comparisons and displays one (`experiments/index.html`, titled "Compare methods"), and one
command checks that the page renders a synthetic bundle faithfully. The check passed
locally on 2026-11-11: 56 checks, 0 failed. It had 28 checks before the page was
reorganised on 2026-11-10; each of the 28 has an equivalent, 9 were added with that
reorganisation, 5 with reference links (*External links*) and 14 on 2026-11-11, when the
page was reordered so that a loaded comparison starts with its paired wording and its
primary output (*What changed on 2026-11-11*). It is a software check on hand-written
numbers. It loads no model, measures nothing and publishes nothing. No study bundle
exists yet, so the published index lists nothing.

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
`data/experiments/index.json` in the site, a failed command-line step, a bundle that does
not export target text for the family this check marks); that is a blocked check, not a
pass.

## Open the fixture preview as a developer

The synthetic fixture is never written into the site, and the published index lists
nothing, so the page shows no comparison when it is opened from the site. To look at a
loaded comparison, serve the temporary copy the check builds:

```sh
python scripts/check_experiment_preview.py --site ../patientwords --serve --port 8931
```

The command copies the site to a temporary directory (without `modes/`), runs the
synthetic slice through the experiment command line, puts the bundle in the copy's
`data/experiment_preview/bundle.json`, serves the copy on `127.0.0.1` and prints three
addresses: the comparison, one case of it opened directly (`&case=fam-2`), and the page
with the empty index. Without `--port` it takes a free port and prints it. It runs no
check and needs no Playwright. Ctrl-C stops the server and removes the copy; the command
then prints that the copy was removed. Nothing is written into either checkout.

What is served is a synthetic fixture. The page says "Synthetic fixture: not a
measurement" in a line that stays at the top of the window, and again in the heading line
of every case. Do not copy the bundle into the site's `data/`: the contract check
(`scripts/experiment_index_contract.py`) fails on any synthetic bundle there, and the index
writer never lists one.

What the command does:

1. Copies the site to a temporary directory. `.git`, caches and `modes/` are left out;
   `modes/` is 941 MB and the page references nothing in it.
2. Runs the real experiment command line: validate, plan, a run stopped after 5 tasks, a
   resumed run, collect, compare, bundle. The protocol it runs is
   `tests/fixtures/experiments/protocol_synthetic_ica.json` with the prompt-text marker
   (see *Prompt text*) added to `fam-1` and `fam-2` and the target-text marker (see
   *Target text*) added to `fam-1`, written in the temporary tree. The committed fixture
   file is not changed. One bundle therefore shows three states: `fam-1` with its wording
   and its target text, `fam-2` with its wording and no target text, `fam-3` with
   neither.
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
6. Serves three display-state alterations and restores the bundle after each (see
   *Display-state alterations*).
7. Removes the temporary tree. The real site and both checkouts are not written to; the
   SHA-256 of the real site's index is compared before and after.

## What the page shows

With no address parameter the page requests one file, `data/experiments/index.json`, and
lists every comparison in it as a link. When the list is empty it says "No experiment
comparisons published yet", says in one sentence that the measured runs are in the results
catalogue, and offers two routes: the results catalogue (`../results/`) and the methods
page (`../methods.html`). That statement and both links are static HTML, so a reader
without JavaScript sees them. If the index cannot be read the page says so and shows no
comparison.

With a comparison chosen, the page renders one bundle in this order. The comparison comes
before its machinery:

1. **One line under the title.** The protocol id and version, and a plain link that
   downloads the bundle file.
2. **The synthetic label,** when the bundle is synthetic: "Synthetic fixture: not a
   measurement", with "hand-written numbers · no model was loaded · nothing here is a
   finding". The line is `position: sticky`, so it stays at the top of the window while
   the page scrolls.
3. **Cases.** One block per case. The first case is open; a case named by the address
   (`&case=<family id>`) is the open one instead. Every case, open or closed, has a heading
   line with the synthetic label when it applies, the model, the endpoint ("target-token
   probability (first token of the target)") and the clinical-review status of the case.
   An open case shows, in order:
   1. *The pair.* One row per wording, named "Medical wording", "Everyday wording" and
      "Rewritten wording" (see *Names of the wordings*), with the prompt text when the
      bundle exports it, or "prompt text is not in this bundle".
   2. *The primary output,* under the question "How does the probability of the target
      differ between the wordings?". One plot of the protocol's primary target: one row per
      wording on a common axis from 0 to 1, the value printed at its dot and the token's
      vocabulary rank beside it. The title names the target by its text when the bundle
      exports it (see *Target text*), and by its id otherwise. Under the plot, one small
      table gives each difference once: the two wordings in the order of the subtraction
      ("Medical wording − Everyday wording"), the value in probability with its sign, and
      the higher wording in words. One line says that the bundle computed no uncertainty.
   3. *Other targets,* in a fold that is closed on load.
   4. *Internal measurements.* One fold per method, closed on load: readout ranks, one row
      per wording, layer and target; ICA with a signed component score and a
      squared-coordinate share per wording in separately labelled columns and the signed
      score difference per comparison. A method with no result in the case is one line
      with its run status and a link to its reason.
   5. *Intervention evidence*, or "no intervention in this bundle".
   6. *Methods & source for this case,* a fold: the basis of any exported text, the targets
      as recorded (id, role, token ids, token count, text), and the prompt SHA-256, the
      SHA-256 of the token ids and the token count of every variant under the file's own
      variant names.
4. **Run status.** A key that defines the six run statuses, each with its own word and its
   own mark, then every planned method with its run status and reason. The capability rows
   the planner used are in a fold.
5. **Methods & source.** The labels that say what the comparison may be used for (model,
   evidence class, clinical review, *Included in analysis*, *Study version*, visibility),
   the protocol, model and tokenizer as recorded, the definition of the endpoint, the
   schema term of each reader-facing label, planned tasks and run counts, external links,
   the file path, the schema string and the source hashes, and the limitations.

Hashes, the schema string, the publication markers and the evidence block's schema words
are under *Methods & source* or in a case's own *Methods & source* fold, and nowhere
above them. The check reads the text a reader sees above *Methods & source* with every
case open and requires that it holds none of them.

Each value is printed once. A wording that sits in two comparisons is recorded by both
comparison blocks; the page prints it in the row of the wording, and when the two records
differ it prints neither and says "two comparison blocks record different values".

No quantity is combined with another. Only a probability is drawn on the 0 to 1 axis; a
rank and a component score stay in tables. The page adds and averages nothing.

Where a bundle does not carry a value the page prints a dash and "not in this bundle" in
that place. It fills nothing in. A zero is printed as a digit: a probability of zero is
`0.0000` with its dot at the left end of the axis, a difference of exactly zero is `0`
with "no difference", and a missing difference is a dash with words and no digit.

### Names of the wordings

The file names its variants `clinical`, `colloquial` and `normalized`, and optionally
`within_register_paraphrase` and `changed_fact_control`
(`scripts/experiments/common.py`). The page shows:

| Variant in the file | Shown as |
|---|---|
| `clinical` | Medical wording |
| `colloquial` | Everyday wording |
| `normalized` | Rewritten wording |
| `within_register_paraphrase` | Same-register paraphrase |
| `changed_fact_control` | Changed-fact control |

The page never prints the word "normalized" as a label: a patient's own words are not
abnormal. The engine's documentation defines no transformation for that variant.
`common.py` lists the name, and neither this directory nor `docs/protocols/` says what
the rewrite does. The page therefore names the arm by what the file shows it to be, a
third wording, and not by a transformation such as "rewritten in medical terms". When a
protocol document defines the transformation, the label in the page (`WORDING`) and in the
check (`WORDING_LABELS`) should say it. The file's own names stay in data attributes and,
as code, in each case's *Methods & source* fold and in the protocol record; the check
requires that the word is nowhere else in the page's text, titles or accessible names.

The last two labels follow `docs/protocols/instrument_validity_benchmark.md` (*Variants*).
No fixture carries those variants, so no check renders them.

### Colour

The medical wording's mark is green `#15803d` and the everyday wording's is ink `#111827`,
as in the engine's figures; the third wording has a hollow ink ring. Each mark stands
beside the printed name of its wording. Values, differences and run statuses are in ink.
The page keeps one alert colour, `#b4483d`, for a bundle file that failed to load and for
a refused address; a rendered comparison shows it nowhere, and the check requires that.

### External links

A bundle without a link record shows one sentence and no link. No exported bundle carries
a link record today, so this is what every bundle shows. When a bundle carries records of
the shape `link_or_fallback` returns ([neuronpedia.md](neuronpedia.md)), the page shows
one box per record, in one of three states:

| State | When | What is shown |
|---|---|---|
| Verified link | the record's `link` is an `https` address, its `reason` is "link built from the recorded pattern" and its local record says `verified_exact` | "Verified link:" and the address as the link text; a solid box. Unchanged since before reference links existed |
| Reference | the record's `kind` is `reference`, its `link` is null and its `reference` record passes the rule below | a dashed box; the line "Reference only · external service · not a link to the study's model, feature or representation"; a link with a dashed underline whose text is "Reference page on Neuronpedia (external service): model page, " and the address (or "source page of one layer", "lens page"); under it the record's fixed label sentence in full, as text; then the date read, the identity status, the page form, the registry entry, the saved service record with its SHA-256, and the reason there is no verified link |
| No link | anything else | "No link. Reason: " with the recorded reason and detail. When the record holds a reference the page did not accept, the line ends with the reason from the rule below |

The page shows a reference record as a link only when all of this holds; the first test
that fails gives the reason it prints:

1. `kind` is `reference`.
2. `label` is the engine's `REFERENCE_LABEL`, character for character. The page holds
   the sentence as a constant; a test compares the two offline. A missing label and any
   other label are refused, so a record cannot carry wording of its own.
3. `url` passes the test the page applies to a verified link (`LINK_URL`): `https`, a
   host, and path characters from `A-Z a-z 0-9 . _ ~ / -`. A query string and a fragment
   therefore fail.
4. The host is `www.neuronpedia.org`. One exception: inside a bundle whose labels say it
   is synthetic, a host under `.invalid` is also accepted. The engine's fixture registry
   links only to `registry-fixture.invalid`, `.invalid` is a reserved top-level domain that
   reaches no site, and a synthetic bundle is never listed (*The index*). In every other
   bundle a `.invalid` host is refused like any other host.
5. `page` is `model_page`, `source_page` or `lens_page`, and the path has that form: one
   segment; two segments with the second starting with a layer number and a hyphen; two
   segments with the second `jlens`. A path with a third segment, the form of a feature
   page, is refused.
6. `reason` is "reference link built from the recorded page form", `read_utc_date` is a
   date and `identity_status` is one of the four verification statuses.

A result that holds both a link string and a reference shows no reference, and so does a
result whose own `kind` is not `reference`. The rule is `referenceRefusal` in the page.
`validate_reference_link` in the engine applies the same tests and more (the closed key
set, the evidence fields, the registry entry); the page does not check those, because it
has no registry to compare with. The page never follows a link and requests nothing from
the external service.

### Labels and the schema terms they stand for

The page uses reader-facing labels. The schema terms stay on the page, in *Methods &
source*.

| Label on the page | Schema term | Bundle fields |
|---|---|---|
| Compare methods | method-comparison bundle | the file, `patientwords.experiment-bundle/1` |
| Cases | case families | `protocol.families`, `comparisons[].family_id` |
| Medical wording, Everyday wording, Rewritten wording | the variants `clinical`, `colloquial`, `normalized` | `protocol.families[].variants` |
| Run status | execution state | `execution.by_state`, `methods_not_run[].states` |
| Included in analysis | analysis membership | `evidence.analysis_memberships` |
| Study version | analysis pin | `protocol.id`, `protocol.version`, `protocol.sha256` |
| Methods & source | provenance | `provenance`, `plan_totals`, `execution` |
| Target-token probability | `behavior_next_token` / `full_vocab_probability` | `comparisons[].comparisons[].behavior` |

"Target-token probability" is the model's next-token probability of the first encoded
token of the target, over the full vocabulary. The page says this once, under *Methods &
source*, with the unit of a difference: a difference is given in probability, as the
first wording minus the second, and 0.01 is one percentage point. The endpoint is never
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
`exp-provenance`, `exp-limitations`, `exp-fam-toggle`, `exp-index`, `exp-index-list`,
`exp-index-count`, `exp-empty`, `exp-empty-head`, `exp-guide`, `exp-terms`,
`exp-endpoint-unit`. Added on 2026-11-11: `exp-fixture` (the synthetic line),
`exp-case-note`, `exp-state-key`, `exp-capability`, `exp-capability-body`, `endpoint`.

Since 2026-11-11 `#evidence` and `#protocol` are inside `#provenance` (*Methods & source*);
both ids are kept, and a link to `#protocol` opens its fold. `#totals`, `#links` and
`#limitations` are parts of `#provenance` as before. The section links of a loaded
comparison are `#families`, `#methods`, `#provenance` and `#limitations`. The loaded state
has a plain link that downloads the bundle file.

## Address parameter (developer reference)

Readers follow links from the list. The syntax below is not shown on the page.

```text
experiments/index.html?bundle=<relative path under data/>
experiments/index.html?bundle=<relative path under data/>&case=<family id>
```

`case` opens one case of the comparison directly: that case is the open one and the page
scrolls to it. The value is compared with the family ids of the loaded file and is never
written into the page. A value that names no case of the comparison shows the first case
and one line that says so. A case opened this way keeps the synthetic label: the line at
the top of the window, and the case's own heading line.

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
bundle". `variant_inputs` is unchanged and stays closed.

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

## Target text

A reader of a paired comparison needs to know which word's probability moved. Since
2026-11-11 a bundle can say so, through a second explicit export:

1. The protocol marks a family with `publication:target_text_approved` in its `facts`
   list, in addition to `publication:prompt_text_approved`. The prompt marker alone
   exports the prompts and no target text. The target marker without the prompt marker is
   refused (`target_text_without_prompt_text`): a target shown without its prompts has no
   reading.
2. `scripts/experiments/bundle.py` then writes, for that family,
   `protocol.families[].target_text`, an object keyed by target id:
   `{"<target id>": {"text": <string>, "n_tokens": <int>, "partial_token_endpoint": <bool>}}`,
   and `protocol.families[].target_text_export` (`basis`, `marker`, `seal_check`, the shape
   of `prompt_text_export`). `text` is copied from the protocol's `targets[].text` and is
   never derived from a token id. `n_tokens` is the length of the protocol's
   `targets[].token_ids`. For a non-synthetic protocol the seal is asked about each
   target's text as well.
3. `partial_token_endpoint` is true when the target spans more than one token. The
   behaviour endpoint reads the first target token only, so the value shown for such a
   target is the probability of its first token and not of the whole text. The text of
   that first token alone is recorded nowhere.

What the page does with it:

| The bundle holds | Plot title | Line under the title |
|---|---|---|
| `target_text` for the target, one token | Target-token probability of “text” | The target “text” is one token, so the value is the probability of the target. |
| `target_text` with `partial_token_endpoint` true | Target-token probability of the first token of the target “text” | The value is the probability of the first token of the target “text”, which spans N tokens. It is not the probability of the whole word. |
| no `target_text` for the family | Target-token probability of target `<id>` | Target `<id>`: its text is not exported in this bundle. The value is the probability of its first token. |

The page never works a text out from a token id and never borrows one from another case.
The basis of the export (`target_text_export`) is in the case's *Methods & source* fold,
with the target's token ids and token count.

## What changed on 2026-11-11

The integration owner's measurement of the page as it was on 2026-11-10, with the fixture
loaded, found the first wording about 974 CSS px down at 1280 px and 1,790 px down at
390 px, after the loaded-state box, the synthetic box with six labelled values, a fold and
the explanation of the endpoint. A second capture of the same page on 2026-11-11, before
the change, measured 988 and 1,761. The page was reordered:

- The pair and the primary output of the first case come first. The labels that say what
  the comparison may be used for, the schema string, the file path and the hashes moved to
  *Methods & source*.
- One primary target is plotted first. The other targets, each internal method and each
  case's source are folds that are closed on load.
- The wordings are named for a reader, and the target is named by its text when the bundle
  exports it.
- The difference of a pair is printed once, with its subtraction order in words. The
  second table of differences was merged into the plot's panel.
- The synthetic label became one line that stays in view, and one phrase in each case's
  heading line; the red box around the shared context was removed.
- Text is 13 px or larger, labels are in sentence case, and monospace is used for code and
  identifiers only.

Positions measured by the check on 2026-11-11 with the fixture loaded (they are recorded
in the receipt and no check requires them): the first wording 425 CSS px from the top at
1280 px and the primary plot 627 px. A separate capture at 390 px measured 648 and 943.

Checks that were revised, and why:

| Check | Before | Now |
|---|---|---|
| `synthetic_banner_beside_the_results` → `synthetic_label_stays_in_view_and_is_in_every_case_line` | the label once in *About this comparison*, once per case, once at the run-status table | the label once in a line that is still inside the window after scrolling to every case, to the run status, to *Methods & source* and to the limitations, and once in every case's heading line |
| `behaviour_values_equal_softmax_of_fixture_logits` | the difference row read "clinical (a) minus colloquial (b)" | the row reads "Medical wording − Everyday wording", records its order in `data-a` and `data-b`, and the table's heads say "first wording minus second" and "In probability" |
| `reader_labels_shown_schema_terms_kept_and_endpoint_explained_once` | the label "included in analysis" beside the results | the same labels under *Methods & source*; also the unit of a difference and one "no uncertainty" line per case |
| `prompt_text_shown_only_for_marked_cases_and_absent_state_for_the_rest` | headings "1 · Paired wording" to "4 · Intervention evidence"; the basis line under the pair | the order of the headings of a case without numbers; the placeholder line under the pair and the basis line in the case's source fold |
| `prompt_hashes_token_counts_preprocessing_and_run_counts_equal_the_fixture` | required that no target text is on the page | target text has its own check, below |
| `section_ids_section_links_and_download_link_are_stable` | five section links starting with `#evidence` | four section links starting with `#families`; `#evidence` and `#protocol` must be inside `#provenance` |
| `family_folds_open_from_the_keyboard_and_keep_their_labels` | a closed case keeps its heading and review status | also: the heading line gives model and endpoint, one plot is shown on load, and the folds of the other targets, of a method and of the source open with Enter |

No check was removed.

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
| Prompt text | a marked family shows exactly the protocol's text, a line that says it is placeholder text, and the basis line in its source fold; an unmarked family reads "prompt text is not in this bundle" and none of its prompt strings is anywhere on the page |
| Target text | the family with both markers names each target by the protocol's text; the two other families name the target by its id, say its text is not exported, and show the protocol's target text nowhere in the case, although every family of the fixture has the same target ids and token ids |
| Names of the wordings | every row of the pair, of a plot and of a readout table is named by the page's label; the word "normalized" is in no text outside `code` elements, in no title and in no accessible name |
| Order of the page | in document order and as the page loads: the pair of the first case, its primary plot with a value, the run status, *Methods & source*; every case keeps one order of its parts |
| Where the machinery is | with every case open, the text above *Methods & source* holds no 64-character hash, no schema string, no publication marker and no schema word of the evidence block; a case shows a hash only in its source folds |
| One primary target first | one plot is shown on load, of the protocol's primary target; the other targets and every method are closed folds; nothing but a probability has a dot or an axis |
| Colour | values, differences and run statuses are in ink; the wording marks have their identity colours beside the printed names; nothing shows the alert colour |
| Reader labels | the six labels are shown; the retired headings are not headings or column heads; the schema term of each label is in *Methods & source*; the first-token explanation appears once; no heading uses "accuracy", "risk", "understanding", "combined", "composite" or "overall" |
| ICA preprocessing mode | the `basis.preprocessing` of the protocol's `ica_lens` block. The adapter completes a task only when its payload records that mode. |
| Attempts executed and results reused | the sums of `executed` and `reused` over the `run-fixture` summaries the command line printed in step 2 (27 and 5). Not read from the bundle. |
| Methods listed, with run status | the method list of the protocol; three completed, `j_lens` unsupported, `jpp` unavailable, each with the bundle's reason. Each case states the status and links to the reason in the Run status table; the check follows the link to the row. |
| Protocol, model and tokenizer identity; planned task count | the protocol that was run |
| Readout ranks and top-k wording | the bundle itself: every side of every comparison block against the row of its wording. This is rendering fidelity only. The script has no independent readout oracle. |
| Synthetic label and clinical review | the label is in one line that stays inside the window at every scroll position the check visits, and in the heading line of every case; each case heading, open or closed, shows the model, the endpoint and its clinical-review status |
| A case opened by address | `&case=fam-2` opens that case, scrolls to it and keeps the synthetic line in view; an unknown value shows the first case and says so; the value is not written into the page |
| States | idle, loading, missing, error, refused and loaded each carry a different word and a different style class. A zero difference reads `0` with "no difference"; a missing value reads as a dash with words. |
| Requests | no console error, no failed request, exactly one data request for a rendered bundle |
| Address rule | the page's rule and its Python mirror give the same answer on 19 cases |
| Stable ids and links | the ids listed above exist; the section links are the four listed; the download link resolves to the bundle file; `#protocol` opens its fold |
| Layout and text | no horizontal overflow at 1280 px and 390 px, and none at 390 px with every text size doubled, as loaded and with every fold open; no visible text below 12 px at either width, labels printed by the stylesheet included |
| Keyboard | Tab reaches, in order, the skip link, the navigation, its disclosure, the download link, the section links, the case button, a case heading and a fold, and each shows a solid focus outline of 2 px or more; folds, the case button and the index link work from the keyboard |
| Navigation | four primary links and one disclosure that is closed on load, opens with Enter and lets Tab into its list, with JavaScript on, with JavaScript off and at 390 px; this page is not linked from it |

Deliberate defects, each followed by a restored pass:

| Defect served | Required result |
|---|---|
| `schema_version` changed to `.../2` | error state naming both strings; no part of the bundle rendered |
| Bundle file deleted | missing state with "HTTP 404" |
| A method's state counts, another's payload records and their block states removed | "state not recorded" for both; neither reads "completed" |
| The fields added on 2026-11-10 removed, as in a bundle written before them | the page renders in full with the synthetic label beside every case; no prompt text of any family is on the page; the hash, token-count, preprocessing, executed and reused places each read "not in this bundle"; the vocabulary size reads "not in this bundle"; the check of those values fails on this copy |
| `?bundle=../data/experiment_preview/bundle.json`, literal and percent-encoded, and two `bundle` parameters | refused in two short lines with a link to the list; no request beyond the page; no address syntax shown. Without the rule the first two would reach the served bundle. |
| One probability and one ICA score sign changed | the value checks and the dot check fail |
| One recorded difference given the opposite sign, its two probabilities unchanged | the value check fails: the page prints the bundle's difference with the bundle's sign and does not recompute it |
| Two comparison blocks record different values for one wording (probability, readout rank, ICA score) | each of the three cells says "two comparison blocks record different values"; no dot is drawn; neither value is shown |

### Display-state alterations

Three states cannot come from a fixture run, so each is put on the page by a copy of the
built bundle with one thing changed. The receipt lists them under
`display_state_alterations` as alterations of a display state; none is a run.

| Alteration | Required result |
|---|---|
| The primary target of `fam-1` says `n_tokens` 2 and `partial_token_endpoint` true (the fixture backend's targets are single tokens) | the plot title and its accessible name say "the first token of the target", the line under it says the target spans 2 tokens and "It is not the probability of the whole word.", the target record shows 2 tokens, and every value is unchanged |
| `logit_lens` made `failed`, `ica_lens` split between `invalid` and `not_run` (their payload records removed, their blocks in every case set to the same states) | the run-status table gives every method its states with task counts; the six states carry six different words and six different marks; the key defines all six; every case names the state of each method without a result; no value of those methods is shown |
| One probability set to exactly 0 and one difference set to null | the zero reads `0.0000` with its dot within 1 CSS px of the left end; the missing difference is a dash with words and no digit and is not called "no difference" |

Link records are checked with records built by
`scripts/experiments/neuronpedia.py` from its fixture registry: a verified, built
record becomes a link; an unverified alias shows its reason and local record; an
alias record with a link string pasted in, and a verified record whose link is not an
`https` URL, show no link.

Reference links have five checks. The records are built by
`link_or_fallback(..., reference_page=...)`; none is written by hand except the forged
ones, which are a built record with one change each.

| Check | What is served | Required result |
|---|---|---|
| `a_reference_record_renders_as_a_reference_with_the_fixed_label` | the fixture registry's three reference results (model page, source page, lens page) beside a record with no link and an exact record; each reference record first passes `validate_reference_link` | each renders in the Reference state at 1280 px and 390 px: the link goes to the record's address with the text above, the label under it equals `REFERENCE_LABEL` and is visible text (the link has no `title`), the date read and the identity status equal the record's, Tab puts the page's focus outline on the link, and the page is no wider than 390 px |
| `a_reference_record_is_never_rendered_as_a_verified_link` | the same render | no reference box is marked verified, says "Verified link:", uses the address as its link text or has the markup of a verified link; the words before the address do not include "verified", "exact", "study", "feature" or "representation"; exactly one record of the five is marked verified |
| `an_exact_record_and_a_record_with_no_link_render_as_before` | the same render | the exact record and the record with no link have the element structure, text, link attributes and solid box they had before reference links were added, compared with literals in the script |
| `forged_reference_records_show_no_link_with_a_reason` | 20 forged records in the synthetic bundle: another host, the service's host without `www`, a query string, a fragment, `http`, a `javascript:` address, the label "Verified link", the address as the label, the label with one word changed, no label, an empty label, record kind `exact`, page form `feature_page`, the path of a feature page, the reason of an exact link, no date, an unknown identity status, a result of kind `exact`, a result that also holds a link string, and a reference record served on its own with another host | no link anywhere under External links; each record shows "No link. Reason: " with the reason of the test it fails; the page's rule, asked directly, gives the same reason; `validate_reference_link` refuses the 18 forgeries that change the reference record |
| `reference_host_is_the_service_host_outside_a_synthetic_bundle` | a copy of the fixture bundle relabelled as not synthetic, in the temporary tree only, with the fixture registry's reference result and one built from the committed registry (`data/experiments/representation_registry.v1.json`) and its saved evidence files | the fixture result shows no link, "the host is not www.neuronpedia.org"; the committed result renders in the Reference state with its address on `www.neuronpedia.org`. The link is not followed, and the check that no request left the test server covers this render too |

Mutations run by hand on 2026-11-10, each on a copy of the page: with the host test
removed, the fourth and fifth checks fail; with a reference rendered as "Verified link:"
and its address, the first, second and fifth fail; on the page as it was before reference
links, all five fail and the other 37 pass.

### Mutations of 2026-11-11

Each check that was added or revised on 2026-11-11 was run against a copy of the site in
which the page was broken in one way. The check had to fail on the copy and pass on the
unbroken copy. All 18 were caught, and the
unbroken copy passed with 56 checks. A mutation often fails more checks than the one it
was written for; the table names the one it had to fail.

| The page was broken so that | Check that had to fail, and did |
|---|---|
| the run status stands before the cases | `pair_and_primary_output_come_before_run_status_and_methods_and_source` |
| the line under the title prints the schema string | `hashes_schema_strings_and_publication_markers_are_under_methods_and_source` |
| the third variant is labelled "Normalized wording" | `wordings_are_named_for_the_reader_and_the_third_variant_is_never_called_normalized` |
| a family without `target_text` is given a target text by the page | `target_text_shown_only_where_the_bundle_exports_it_and_never_inferred` |
| `partial_token_endpoint` is ignored | `a_target_of_two_tokens_is_shown_as_the_first_token_of_the_target` |
| two run statuses share one mark | `each_run_status_is_shown_as_its_own_state` |
| a missing value is printed as `0` | `a_zero_and_a_missing_value_are_shown_differently` |
| the page recomputes a difference from its two probabilities | `control_a_difference_of_the_opposite_sign_fails_the_value_check` |
| the subtraction is named in the other order | `behaviour_values_equal_softmax_of_fixture_logits` |
| folds and buttons have no focus outline | `main_controls_are_reached_by_tab_and_show_a_focus_outline` |
| the navigation disclosure is open on load | `navigation_disclosure_opens_from_the_keyboard_with_and_without_javascript` |
| the other targets are open on load | `family_folds_open_from_the_keyboard_and_keep_their_labels` |
| the `case` parameter is ignored | `a_case_opened_by_address_is_the_open_one_and_keeps_the_synthetic_label` |
| metadata text is 11 px | `no_visible_text_is_smaller_than_12_px_at_1280_or_at_390` |
| a label in *Methods & source* cannot wrap | `no_horizontal_overflow_at_390_px_with_text_at_200_percent` |
| the everyday wording's value is in the alert colour | `values_and_states_are_in_ink_and_wording_marks_keep_their_identity_colours` |
| the synthetic line is not sticky | `synthetic_label_stays_in_view_and_is_in_every_case_line` |
| the "no uncertainty" line is replaced by an interval the bundle does not hold | `reader_labels_shown_schema_terms_kept_and_endpoint_explained_once` |

The mutations were applied by a scratch script, not by a committed tool, so this table is
a record of one run and is not re-run by any test.

## What it does not verify

- No model was loaded. The "original model output" in this bundle is the softmax of
  hand-chosen logits. Nothing here is evidence of parity with a real model.
- No measurement. The receipt says `"evidence": "local synthetic software test only"`.
- No deployed site. The page was served from a local copy, not from GitHub Pages.
- No real bundle. None exists, so no real bundle has been rendered. The non-synthetic
  rendering path is exercised only by a relabelled copy of the fixture.
- No real seal check. The prompt-text export of a non-synthetic protocol and the index
  writer's seal check are tested with stub seal functions. No sealed text was read.
- No page of the external service was requested. That a reference address resolves is
  recorded for 2026-11-10 in [neuronpedia.md](neuronpedia.md), not checked here.
- No exported bundle carries a link record, so the Reference state has been rendered
  only from records this check writes into a temporary copy.
- One browser: Chromium 153. No other browser and no assistive technology was run.
  The ARIA roles and the keyboard path were checked by script, not with a screen reader.
- Readout values have no independent oracle here (see the table).
- The page does not validate a bundle against `schemas/experiments/bundle.v1.schema.json`.
  It checks the schema string and the presence and type of the blocks it reads.
- A bundle with many cases: every case is rendered into the page. There is no paging.
  Only the open case shows its content, and on load that is the pair and one plot.
- Text at twice its size is emulated: the check doubles every computed font size in place
  at 390 px. It does not use a browser's or an operating system's own text setting.
- Target text of more than one token is rendered only from an altered copy of the bundle.
  The fixture backend's targets are single tokens.
- The variants `within_register_paraphrase` and `changed_fact_control` have labels in the
  page and no fixture, so no check renders them.
- The dot plot's colours. The three marks use the site's fixed palette (clinical green,
  patient ink, a hollow ink ring). The dataviz palette validator fails the ink on its
  lightness-band and chroma checks and passes it on colour-vision separation and
  contrast. Each row prints the wording's name, so colour is never the only cue.

## Findings from building it

1. **An exact tie can arrive as one rounding step.** In the fixture,
   `fam-2 / colloquial_vs_normalized / c1` is 1/16 against 1/16. The bundle records the
   difference as `1.39e-17`, because the two softmax results differ in the last bit.
   `scripts/experiments/compare.py` subtracts the recorded values, as its contract
   says (signed, raw). The page prints `+1.39e-17` and "Everyday wording higher, below the
   4 decimals shown". It applies no tolerance of its own. The check accepts either `0`
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
   not a contract. It also reads a reference record placed there on its own (kind
   `reference` with its own `url`), without the result around it.
5. **The fixture registry's reference links are on a `.invalid` host.** A rule that
   accepts `www.neuronpedia.org` and nothing else refuses every record the fixture
   registry can build. The page therefore accepts a `.invalid` host inside a synthetic
   bundle only (*External links*, test 4), and the check renders a record of the
   committed registry in a relabelled copy to exercise the service host.

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

Added on 2026-11-11, also optional:

| Field | Content | Source |
|---|---|---|
| `protocol.families[].target_text.<target id>` | `text`, `n_tokens`, `partial_token_endpoint` | the protocol passed with `bundle --protocol`, for a family that carries both markers; see *Target text* |
| `protocol.families[].target_text_export` | the basis of the export: `basis`, `marker`, `seal_check` | the same |

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
- The prompt-text marker and the target-text marker are literals in
  `scripts/experiments/bundle.py` and in the check. A unit test fails when they differ.
- The names of the wordings exist twice: `WORDING` in the page and `WORDING_LABELS` in the
  check. The browser run compares the two, and a unit test requires a label for every
  variant in `scripts/experiments/common.py`.
- The masthead navigation is the same markup on every authored page of the site. This
  check reads it on the experiments page and `scripts/check_results_page.py` reads it on
  the results page; neither reads the other pages.
- The fixed label of a reference link exists twice: `REFERENCE_LABEL` in
  `scripts/experiments/neuronpedia.py` and `REFERENCE_LABEL` in the page. A unit test
  compares the page's literal with the engine's constant, and the browser run compares
  what the page exposes. A change to the sentence needs both. The page's reasons for
  refusing a reference record are literals in the check as well.
- The reference checks read the committed registry and its evidence files. If the
  registry stops building a reference link to a model page, the fifth check fails and
  says so; it does not skip.
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
   (`holdout_refusal`), and bundle version 1 holds prompt text and target text only
   through the two explicit exports (*Prompt text*, *Target text*).
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

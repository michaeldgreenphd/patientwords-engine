# Neuronpedia identity and link boundary (2026-11-10)

Status: registry, validators and an offline link builder. An entry carries two separate facts:
what is known about the identity of the hosted checkpoint (the verification status) and whether the
service's own record for the entry's ids was read and saved (the reference status). No exact link
to a real Neuronpedia page is built today: no real registry entry is `verified_exact` and no real
entry records an exact URL pattern. Five real entries permit a reference link, which is a link to
the service's page for a model, for one layer's source or for a model's lens, shown as a reference
to an external page (*Reference links*). A reference link permits no pooling of hosted and local
results and no parity statement.

The registry was first written on 2026-11-10 without network access to the service. Later the same
day the service's documentation, pages, API records and export files were read with plain GET
requests (*What was read on 2026-11-10*). Those records confirm every hosted id in the registry and
name a Hugging Face repository for each hosted model and source. None names a revision, a commit or
a hash, so no status rose to `verified_exact`. Every Neuronpedia fact on this page is cited to a
dated, hashed record of the service, to engine source code or to a dated engine document, or is
marked unverified.

Code: `scripts/experiments/neuronpedia.py`. Data: `data/experiments/representation_registry.v1.json`
(schema `patientwords.representation-registry/1`,
`schemas/experiments/representation_registry.v1.schema.json`). Fixtures:
`tests/fixtures/experiments/neuronpedia/` (synthetic). Tests: `tests/test_experiments_neuronpedia.py`.
Evidence: `data/experiments/neuronpedia_evidence/20261110/` (the index `index.v1.json` and the kept
response bodies under `bodies/`) and
`data/experiments/neuronpedia_evidence/20261110_reference_pages/index.v1.json` (the pages fetched
to confirm the page forms of reference links, and the paper's page; no body kept).

The module makes no network request. It imports no HTTP client. The records of 2026-11-10 were
fetched by a session, outside the module; the module's `record_snapshot` and `request_record`
described the saved files afterwards. The reference-link functions read those saved files from
disk and hash them; they fetch nothing. One test,
`test_importing_and_using_the_module_opens_no_socket`, loads the module from its file and calls
each of its twenty-one public functions with `socket.socket`, `socket.create_connection` and
`socket.getaddrinfo` replaced by a function that raises. The same test compares the functions it
called with the functions the module defines, and fails when the two sets differ.

## The boundary

PatientWords owns the study: the design, the paired stimuli, the clinical-equivalence review, the
outcomes and the evidence labels. Neuronpedia supplies representations that are compatible with a
study model (hosted graphs over a transcoder set, hosted lens readouts, released components),
context for a feature (labels, activating examples) and an optional place to explore one.

Three consequences follow, and the code enforces each.

- The static site and every exported bundle work with no Neuronpedia account and no live request.
  `link_or_fallback` always returns a `local` record that is enough to inspect the result. The
  external link, exact or reference, is an extra.
- An external label is a hypothesis with a source. It is never a study outcome. The four
  quantities in *Explanation provenance* stay in four fields.
- An external id is a field of a registry entry. It is never a key. `resolve` matches on the
  engine's study id only. A study id that is not a non-empty string is refused (`invalid_input`),
  so the three entries whose model the engine does not run (their `model.study_id` is null) are
  never returned by `resolve`.

## What was read on 2026-11-10

Each record was one plain GET with curl's default User-Agent: no credential, no cookie, no query
string, nothing about the project in a header or a URL. No POST was sent, and no endpoint that runs
a model or generates a graph was called. 62 responses were saved, between 18:24 and 18:28 UTC.
`data/experiments/neuronpedia_evidence/20261110/index.v1.json` holds one record per response: the SHA-256 and size of the body, the URL, the retrieval
time (the output of `record_snapshot`), the HTTP status and the fields read. For the eleven API
records it also holds a request record (`request_record`), in which a null revision listed in
`not_recorded` means the response carried no such field. 61 answered HTTP 200; the one 404 is a
probe of a route that does not exist.

A body is kept under `bodies/` only for a JSON identity record of at most 65,536 bytes that holds
no dataset text and no user name: the seven source-set records and the sixteen export files, plus
the list of NLA sources (24 files, 144,765 bytes). For a page (20 KB to 4 MB of HTML) and for a
feature record (dataset text, label text and user names) the index keeps the hash and the fields
read, not the body.

| What | Records | What they state |
|---|---|---|
| API reference, `https://www.neuronpedia.org/api-doc` | `page.api-doc` | An OpenAPI 3.0.0 document with 53 operations. Six are GET. None describes a model, a source set or a lens. `GET /api/feature/{modelId}/{layer}/{index}` returns a feature. `POST /api/model/lookup` maps a Hugging Face repository id to a model id; its documented response has no revision field |
| API guide and concepts, `https://docs.neuronpedia.org/` | `docs.api-and-data.api`, `docs.getting-started.key-concepts`, `docs.getting-started.find-resources`, `docs.getting-started.accounts`, `docs.api-and-data.exports` and seven more `docs.*` records | Id forms, the feature page form, rate limits, the export layout |
| Source-set records, `https://www.neuronpedia.org/api/source-set/<model>/<set>` | seven `api.source-set.*` records | For each set: the model record (`id`, `hfRepoId`), the sources with their layer, `hfRepoId`, `hfFolderId`, dataset and, for a transcoder, the SAELens configuration |
| Feature records | four `api.feature.*` records (layer 0, index 0 of each hosted set) | The same model and source identity, the hook name, and each explanation's type and explainer model |
| Export identity files, `https://neuronpedia-datasets.s3.us-east-1.amazonaws.com/v1/<model>/<source>/` | sixteen `export.*` records | `model.jsonl`, `source.jsonl`, `sourceset.jsonl`, `release.jsonl` for layer 0 of four sets |
| Pages | `page.available-resources`, `page.jlens.gemma-2-2b`, `page.jlens.gemma-2-2b-it`, `page.graph.validator` and four more `page.*` records | The list of 43 public models with their sources; the two lens pages; the graph validator and its schema |
| Blog posts and the paper | ten `blog.*` records, `arxiv.2606.11722v2` | Dates and announcements. The nine posts were searched for the words commit, revision and checkpoint; none contains one. The paper's page states: arXiv:2606.11722v2, "Non-Gaussianity Reveals Interpretable Directions in Language Models", by Sida Liu, Feijiang Han, Sarah Wiegreffe and Furong Huang; v1 submitted 10 Jun 2026, v2 on 19 Oct 2026 |
| Other | `probe.api.model.qwen3.5-2b-pt`, `probe.api.source.qwen3.5-2b-pt.0-icalens-res`, `api.nla.sources` | Two guessed routes that are not endpoints; the list of NLA sources, none for a model in the registry |

The identity fields the service returns are: for a model, `id` and `hfRepoId`; for a source,
`hfRepoId` and `hfFolderId` (the repository and path of the dictionary, transcoder or basis),
`dataset`, and for SAELens-loadable sources `saelensRelease`, `saelensSaeId` and `saelensConfig`
(`model_name`, `hook_name`, `d_sae`, `architecture`, `dtype`); for a source set, `releaseName`.
No response has a key that names a model revision, a weights revision, a commit or a hash. The only
key that resembles one is `sae_lens_training_version`, a library version, which is null in every
record. `test_no_record_of_the_service_names_a_revision` checks this on the kept bodies.

Three places where the documentation and the responses, or two responses, disagree. Both sides are
recorded.

- **An endpoint the specification does not list.** `GET /api/source-set/<model>/<set>` answered
  with JSON for all seven sets. The API reference lists no operation under `/api/source-set`. The
  guessed routes `GET /api/model/<model>` and `GET /api/source/<model>/<source>` are not endpoints
  (HTML with an empty title and HTTP 200; HTML with HTTP 404).
- **The API and the export name different weights repositories for `gemmascope-transcoder-16k`.**
  The API source record says `hfRepoId` `google/gemma-scope-2b-pt-transcoders` and `hfFolderId`
  `layer_0/width_16k/average_l0_76`. The export's `source.jsonl` says `google/gemma-scope` and
  `layer_0/width_16k`. The registry therefore records no repository for that set.
- **The export's model record is thinner than the API's.** `model.jsonl` has no `hfRepoId` key. For
  `qwen3.5-2b-pt` it gives `displayName` `qwen3.5-2b-pt` and `createdAt` 2026-11-07, where the API
  gives `Qwen3.5-2B Base` and 2026-05-08. For `qwen3-4b` it says `instruct` false and its source
  says `inferenceEnabled` true, where the API says true and false.

Not read, and listed in the registry under `sources_not_read`:

| URL | Why |
|---|---|
| `https://huggingface.co/api/models/neuronpedia/icalens-qwen3.5-2b-pt` | the session's network proxy refused the host (CONNECT, response 403). No basis repository or manifest on Hugging Face was read |
| `https://www.neuronpedia.org/api/model/lookup` | a POST endpoint; only GET requests were made |
| `https://www.neuronpedia.org/api/lens/prompt` | a POST endpoint that runs a model. What a live lens response reports about the lens was not read |

### Pages fetched to confirm the reference page forms (19:49 to 19:51 UTC)

Thirteen more plain GET requests were made the same day, under the same rules, and none was
redirected. `data/experiments/neuronpedia_evidence/20261110_reference_pages/index.v1.json` holds one record per response (SHA-256, size, URL, retrieval
time from `record_snapshot`, page title, page component). No body is kept: each is an HTML page of
21 KB to 4.4 MB.

| What | Records | What they state |
|---|---|---|
| Documentation pages that give a page form | `docs.getting-started.key-concepts`, `docs.getting-started.find-resources`, `docs.jacobian-lens` | Quoted: "A model page (neuronpedia.org/[MODEL_ID]) shows all the releases for that model". Quoted: "A source page (neuronpedia.org/[MODEL_ID]/[SOURCE_ID]) shows the configuration of one SAE or transcoder". Quoted: "A source ID starts with the layer number, then the source set name". Quoted: "You can also go directly to neuronpedia.org/[MODEL_ID]/jlens". The three pages have the same SHA-256 as at 18:24, so these sentences are also the content of the earlier records |
| One model page per hosted model id | `page.model.gemma-2-2b`, `page.model.gemma-2-2b-it`, `page.model.qwen3-4b`, `page.model.qwen3.5-2b-pt` | HTTP 200, a page title that names the id, the page component `PageModel` |
| One source page per hosted source set, at layer 0 | `page.source.gemma-2-2b.0-gemmascope-transcoder-16k`, `page.source.qwen3-4b.0-transcoder-hp`, `page.source.qwen3.5-2b-pt.0-icalens-res` | HTTP 200, a page title that names the model id and the source id, the page component `PageSource` |
| The two lens pages | `page.jlens.gemma-2-2b`, `page.jlens.gemma-2-2b-it` | HTTP 200, the page title "Jacobian Lens" with the model's display name |
| The paper | `arxiv.2606.11722v2` | The same SHA-256 as at 18:27. Title, version, four authors and both submission dates, quoted in the record |

HTTP 200 alone does not show that a page exists: the site answers 200 with an empty page title for
an id it does not have (record `page.model.qwen3.5-2b` of the earlier index). Each page record
therefore keeps the title and the component found. A page hash identifies one response: the lens
pages and the `qwen3.5-2b-pt` pages fetched at 18:26 have other bytes.

The documentation gives no page form for a source set without a layer (a model id followed by a
set name). The link `neuronpedia.org/qwen3.5-2b-pt/icalens-res` appears in the ICA Lens
documentation page and in a blog post (records `docs.research-releases.ica-lens` and
`blog.neurons-ica` of the earlier index); it was not fetched, and the registry records no such
form.

What this leaves unknown, stated once: the commit of any hosted model; the commit and hash of any
hosted dictionary, transcoder, lens or ICA basis; which file of
`huggingface.co/neuronpedia/jacobian-lens` serves a model id; what a live lens response reports
about its instrument; whether the repositories under `neuronpedia/` that the hosted ICA sets name
hold the same files as the bases under `sida/` that the ICA fork names; the explainer and scorer
for a whole source set (one feature per set was read). The graph validator's schema was fetched and
has not been compared field by field with the plan below.

## The registry

One entry is one representation of one model. The seven representation types (`neuron`,
`sae_latent`, `transcoder_feature`, `ica_component`, `attention_head`, `workspace_readout`,
`graph_node`) are different objects. No function converts one into another, and `resolve` says so
when a model has an entry of another type.

| Field | Meaning |
|---|---|
| `registry_id` | stable id of the entry |
| `representation_type`, `method` | one of the seven types; one of the package's method ids |
| `model` | the engine's study identity: short id, Hugging Face id, pinned commit. It is not a statement about what a hosted service loads |
| `neuronpedia` | `model_id`, `source_set`, `source_id` and `id_source` (where the ids were read), or null |
| `site` | capture site, layer index base, layer list |
| `component_id` | the form of a component id and its source; optionally `count`, the number of components one layer's source holds (an integer from 1 to 2**20). No committed entry records a count on 2026-11-10 |
| `fitted_artifact_sha256`, `artifact` | content hash, repository, revision, and the model the artifact was fitted on |
| `calibration`, `use` | whether the pair is the calibrated reference; what the project does with it |
| `label_source` | `name`, `version`, `explanation_type`, `explanation_model`, `scorer`, `retrieved_utc` |
| `url_pattern` | the template of an exact link, with the source it was read in and the date, or null |
| `verification` | fact one, identity: `status`, `hosted_checkpoint_revision`, `evidence` items `{source, date, states}`, `checked_utc_date` |
| `links_enabled` | the exact-link flag: true only with `verified_exact` |
| `reference` | fact two, the source of a reference link: `status`, `enabled`, `evidence` (the saved record of the service: `index`, `record_id`, `path`, `sha256`, `bytes`, `retrieved_utc`, or null), `pages` (the page forms, each with `kind`, `template`, `source`, `read_utc_date`, `form_record`, `instance_record`) and `reason` |
| `not_recorded` | JSON pointers of every null field in the entry |

A null means the registry holds no value. A null whose pointer is not in `not_recorded` is refused
(`silent_missing_provenance`), and so is a listed pointer that is not null. A field that does not
apply holds the string `not_applicable`.

### Two facts, two vocabularies

The owner's instruction of 2026-11-10: "Separate source-link verification from scientific
comparability. A verified reference page can be useful even when the hosted checkpoint is unknown.
If you support such links, label them as references and keep exact representation links, pooling
and parity claims behind their stronger identity requirements."

The registry therefore holds two statuses per entry, and no function derives one from the other.

| Fact | Field | Question it answers | What it permits |
|---|---|---|---|
| identity | `verification.status` | Is the hosted checkpoint identified, and is it the study's? | Only `verified_exact` permits an exact link (`exact_link`), pooling of hosted and local results (`pooling`) and a parity statement (`parity_statement`) |
| reference | `reference.status` | Was the service's own record for these ids read and saved? | Only `service_record_read_revision_not_reported` permits a reference link |

`permissions(entry)` returns the four answers with the status that decides each.
`require_exact_identity(entry, use)` refuses an exact link, pooling and a parity statement
(`identity_not_verified`) unless the status is `verified_exact`; it does not read the reference
block. Both statuses of every real entry are in *Id mapping on 2026-11-10* and *Reference links on
2026-11-10*.

### Verification statuses

| Status | Meaning | Exact link, pooling, parity |
|---|---|---|
| `verified_exact` | The ids were read in a primary source, and the hosted checkpoint revision is recorded and equals the study revision. The validator refuses this status without both revisions equal | permitted |
| `alias_unverified_checkpoint` | Another id is given for the same checkpoint by the source that the entry's `id_source` names. No record of the commit behind that id was read | none |
| `hosted_identity_unknown` | The engine uses these hosted ids and responses have landed. The engine records no model, dictionary or instrument revision for these responses. The entry's evidence names the records of the service that were read and says that none of them carries a revision, or says that none was read | none |
| `unverified` | The representation is named in a source that was read. Its own manifest or page was not | none |

An alias alone does not verify a checkpoint. Two ids can name the same model family and different
commits, or the same commit served at another precision. `verified_exact` therefore needs
`hosted_checkpoint_revision` to equal `model.revision`, and `links_enabled: true` with any other
status is refused (`links_without_verification`). A repository id is not a commit either: on
2026-11-10 the service named the repository behind every hosted id and no commit, and every status
stayed where it was. The meaning of `verified_exact` is unchanged. Its sentence in the registry used
to end "The only status that permits a link"; it now names the three things the status permits,
because a reference link exists and does not depend on it.

### Reference statuses

| Status | Meaning | Reference link |
|---|---|---|
| `service_record_read_revision_not_reported` | The service's own record for the entry's Neuronpedia ids was read and is saved; `reference.evidence` names it by path, SHA-256, size and retrieval time. The record names the entry's model id and a Hugging Face repository equal to the study's, and reports no revision, commit or hash | permitted, to a page form listed in `reference.pages` |
| `no_service_record` | The entry names no saved record of the service for its ids: it records no Neuronpedia ids, or no record was saved | none |

This is the status word the registry lacked for "ids and repository confirmed by the service's own
record; revision not reported". It is a word of the reference vocabulary and not a fifth
verification status, so that a consumer who reads `verification.status` sees exactly the four words
it saw before, with the same meanings. The validator refuses `reference.enabled: true` without this
status, without a named evidence record or without a page form
(`reference_links_without_record`). It refuses `links_enabled: true` on the strength of a
reference block (`links_without_verification`): the two flags are checked separately.

A reference status is evidence about the retrieval date. If a later record of the service names a
revision, `verify_reference_evidence` refuses it (`reference_status`): the word no longer describes
the record, and the entry has to be read again, including its verification status.

### Id mapping on 2026-11-10

| Engine study id | Representation | Neuronpedia model id / source set | Artifact | Status | What the service reported on 2026-11-10 |
|---|---|---|---|---|---|
| `gemma-2-2b` | `transcoder_feature` | `gemma-2-2b` / `gemmascope-transcoder-16k` | hosted set; repository not recorded (two records disagree) | `hosted_identity_unknown` | ids exist; model `hfRepoId` `google/gemma-2-2b`; 26 sources, layers 0 to 25; no revision (`api.source-set.gemma-2-2b.gemmascope-transcoder-16k`). The one calibrated pair (`scripts/feature_models.py:31`) |
| `qwen3-4b` | `transcoder_feature` | `qwen3-4b` / `transcoder-hp` | `mwhanna/qwen3-4b-transcoders`, commit not recorded | `hosted_identity_unknown` | ids exist; model `hfRepoId` `Qwen/Qwen3-4B`; 36 sources, layers 0 to 35; the API and the export name the same weights repository; no revision (`api.source-set.qwen3-4b.transcoder-hp`). Labelled, not calibrated: exploration only |
| `gemma-2-2b` | `workspace_readout` (hosted J-lens) | `gemma-2-2b` / not applicable | `neuronpedia-hosted:JACOBIAN_LENS`; no instrument revision | `hosted_identity_unknown` | the lens page exists and names no lens repository, file, revision or hash (`page.jlens.gemma-2-2b`); model `hfRepoId` `google/gemma-2-2b`; a live lens response was not requested |
| `gemma-2-2b-it` | `workspace_readout` (hosted J-lens) | `gemma-2-2b-it` / not applicable | same | `hosted_identity_unknown` | the same, for `page.jlens.gemma-2-2b-it` and `google/gemma-2-2b-it` |
| `qwen3.5-2b-base` | `ica_component` | `qwen3.5-2b-pt` / `icalens-res` | `neuronpedia/icalens-qwen3.5-2b-pt`, commit not recorded | `alias_unverified_checkpoint` | the id exists; model `hfRepoId` `Qwen/Qwen3.5-2B-Base`; six sources, layers 0, 4, 8, 12, 16, 20; no revision (`api.source-set.qwen3.5-2b-pt.icalens-res`) |
| `gemma-2-2b` | `ica_component` | none | `sida/icalens-gemma-2-2b-pile10k` | `unverified` | a hosted ICA set exists under `gemma-2-2b/icalens-res`; its sources name `neuronpedia/icalens-gemma-2-2b`, not the `sida/` repository |
| none | `ica_component` | none | `sida/icalens-gpt2-small-pile10k` (`openai-community/gpt2`) | `unverified` | a hosted ICA set exists under `gpt2-small/icalens-res`; its sources name `neuronpedia/icalens-gpt2-small` |
| none | `ica_component` | none | `sida/icalens-qwen3.5-9b-base-pile10k` (`Qwen/Qwen3.5-9B-Base`) | `unverified` | a hosted ICA set exists under `qwen3.5-9b-pt/icalens-res` (8 layers); its sources name `neuronpedia/icalens-qwen3.5-9b-pt` |
| none | `ica_component` | none | `sida/icalens-qwen3.5-2b-ultrachat-1m` (`Qwen/Qwen3.5-2B`, the instruct model) | `unverified` | the service lists no model for `Qwen/Qwen3.5-2B` and hosts no ICA set for it (`page.available-resources`) |

Names in the last column that look like `api.source-set.…` or `page.…` are record ids in
`data/experiments/neuronpedia_evidence/20261110/index.v1.json`. The engine-side evidence of each row (code lines,
dated documents, the ICA fork) is unchanged and is in the registry entry.

Paths that start with `patientwords-ica-lens-paper/` are in the fork
`michaeldgreenphd/patientwords-ica-lens-paper` at `aa3b95c9e755e4374f8c9645a064e3f51d96066e`.

### Reference links on 2026-11-10

The verification status of every row is the one in the table above. No row permits an exact link,
pooling or a parity statement.

| Registry entry | Reference status | Reference links | Saved record (`reference.evidence`) | Page forms and one URL the module builds |
|---|---|---|---|---|
| `gemma-2-2b.transcoder-feature.gemmascope-transcoder-16k` | `service_record_read_revision_not_reported` | on | `api.source-set.gemma-2-2b.gemmascope-transcoder-16k`, 34,248 bytes, retrieved 2026-11-10T18:25:56Z | `model_page`; `source_page` for layers 0 to 25: `https://www.neuronpedia.org/gemma-2-2b/0-gemmascope-transcoder-16k` |
| `qwen3-4b.transcoder-feature.transcoder-hp` | `service_record_read_revision_not_reported` | on | `api.source-set.qwen3-4b.transcoder-hp`, 43,307 bytes, retrieved 2026-11-10T18:25:57Z | `model_page`; `source_page` for layers 0 to 35: `https://www.neuronpedia.org/qwen3-4b/0-transcoder-hp` |
| `gemma-2-2b.workspace-readout.hosted-jlens` | `service_record_read_revision_not_reported` | on | `api.source-set.gemma-2-2b.gemmascope-transcoder-16k`, cited for its model record | `model_page`; `lens_page`: `https://www.neuronpedia.org/gemma-2-2b/jlens` |
| `gemma-2-2b-it.workspace-readout.hosted-jlens` | `service_record_read_revision_not_reported` | on | `api.source-set.gemma-2-2b-it.icalens-res`, 17,879 bytes, retrieved 2026-11-10T18:25:57Z, cited for its model record | `model_page`; `lens_page`: `https://www.neuronpedia.org/gemma-2-2b-it/jlens` |
| `qwen3.5-2b-base.ica-component.neuronpedia-alias` | `service_record_read_revision_not_reported` | on | `api.source-set.qwen3.5-2b-pt.icalens-res`, 5,588 bytes, retrieved 2026-11-10T18:25:32Z | `model_page`; `source_page` for layers 0, 4, 8, 12, 16, 20: `https://www.neuronpedia.org/qwen3.5-2b-pt/0-icalens-res` |
| `gemma-2-2b.ica-component.sida-icalens-gemma-2-2b-pile10k` | `no_service_record` | off | none | none. The hosted ICA set of this model names `neuronpedia/icalens-gemma-2-2b`; no record read ties it to the `sida/` basis |
| `gpt2.ica-component.sida-icalens-gpt2-small-pile10k` | `no_service_record` | off | none | none, for the same reason (`neuronpedia/icalens-gpt2-small`) |
| `qwen3.5-9b-base.ica-component.sida-icalens-qwen3.5-9b-base-pile10k` | `no_service_record` | off | none | none, for the same reason (`neuronpedia/icalens-qwen3.5-9b-pt`) |
| `qwen3.5-2b-instruct.ica-component.sida-icalens-qwen3.5-2b-ultrachat-1m` | `no_service_record` | off | none | none. The service lists no model for `Qwen/Qwen3.5-2B` |

The saved records are under `data/experiments/neuronpedia_evidence/20261110/bodies/`; each entry
repeats its record's SHA-256. The model page URL of a row is `https://www.neuronpedia.org/` followed
by the Neuronpedia model id. The module builds 75 reference URLs from the committed registry (74
distinct: two entries share the model page of `gemma-2-2b`), and
`test_the_real_registry_builds_exactly_these_reference_links_and_no_exact_link` lists every one.

What was verified and what is inferred, per page form:

- **Model pages and lens pages.** Verified for 2026-11-10: each URL the module builds was fetched
  and rendered a titled page (four model pages, two lens pages).
- **Source pages.** Verified for 2026-11-10 at layer 0 of each of the three sets. For the other 65
  layers the URL is inferred from two things that were read: the source id is listed in the saved
  source-set record, and the documentation gives the form `[MODEL_ID]/[SOURCE_ID]`. Those 65 pages
  were not fetched.
- **The two lens entries.** Their saved record is the source-set record of another representation
  of the same model id. It is cited for the model record inside it (`model.id`, `model.hfRepoId`)
  and for nothing about the lens. The lens page names no lens repository, file or revision.

Notes on single rows.

- **`qwen3.5-2b-base` and `qwen3.5-2b-pt`.** The engine pins `Qwen/Qwen3.5-2B-Base` at
  `b1485b2fa6dfa1287294f269f5fb618e03d52d7c` (`scripts/logits_eval.py:147`; chosen as the head of
  `main` on 2026-10-09, `docs/model_matrix.md:285-293`). The id `qwen3.5-2b-pt` was first supplied
  in the owner's task brief of 2026-11-10. The service's records, read later that day, establish
  three things. The model id exists, and its model record names `hfRepoId` `Qwen/Qwen3.5-2B-Base`
  with display name "Qwen3.5-2B Base": the same repository the engine pins. Its ICA source set is
  `icalens-res`, with six sources at layers 0, 4, 8, 12, 16 and 20, each on the hook
  `blocks.<layer>.hook_resid_post`. Each source names the basis repository
  `neuronpedia/icalens-qwen3.5-2b-pt` and the dataset `monology/pile-uncopyrighted`; the set is
  described as a Pile-10k fit and has no inference. The service reports no commit: not of the
  model, not of the basis repository, not of the model the basis was fitted on. A repository can be
  served at another commit than the one a study pins, so the status stays
  `alias_unverified_checkpoint` and no link is built. `huggingface.co` was refused on 2026-11-10,
  so the basis repository and its manifest were not read. To reach `verified_exact`: obtain a
  record that states the model commit behind the hosted set (the fit revision in the basis manifest
  is the candidate), enter it, and confirm it equals the pin. The ICA fork still names no released
  basis for this model
  (`patientwords-ica-lens-paper/notes/naming.md:24` lists `sida/icalens-qwen-3.5-2b` in a naming
  scheme; `patientwords-ica-lens-paper/integrations/r_lens/fit_qwen35.py:21-24` is an R-lens
  preset).
- **`sida/icalens-gemma-2-2b-pile10k`.** The paper's reconstruction run record names this basis
  with model revision `c5ebcd40d208330abc697524c919956e692655cf`, which is the engine's pin of
  `google/gemma-2-2b` (`scripts/logits_eval.py:132`). That is one evaluation run. The record pins no
  basis revision, and the fit revision stored in the basis manifest was not read. Neuronpedia hosts
  an ICA set for the same model, and its sources name `neuronpedia/icalens-gemma-2-2b`. No record
  read says that this repository and the `sida/` one hold the same basis, so the entry records no
  Neuronpedia mapping and the status stays `unverified`. The same holds for the GPT-2 and
  Qwen3.5 9B bases.
- **`sida/icalens-qwen3.5-2b-ultrachat-1m`** was fitted on the instruction-tuned model. It is not
  a basis for the engine's `qwen3.5-2b-base`. Neuronpedia lists no model for `Qwen/Qwen3.5-2B`.
- **`gemma-2-2b` with `gemmascope-transcoder-16k`.** The status is strict on purpose. A hosted
  graph and its feature labels come from the same service under the same ids, so a link from a
  node of that graph to its feature would be id-consistent by construction. The service now
  attests the model repository and names a weights repository. What is unknown is the model commit
  and the transcoder weights commit behind those ids, which matters as soon as a locally loaded
  model is compared with a hosted feature. The four-word verification vocabulary has no status for
  "ids and repository attested by the service, commit not reported", and it still has none: that
  fact is the reference status `service_record_read_revision_not_reported`, which all five hosted
  entries hold. It permits a reference link to the model page or to one layer's source page. It
  does not permit the link from a graph node to its feature page: that is an exact link.
- **Hosted sets that have no registry entry.** The service also hosts `icalens-res` for
  `gemma-2-2b` (`neuronpedia/icalens-gemma-2-2b`), `gemma-2-2b-it` and `qwen3.6-27b`, and
  `clt-hp` for `gemma-2-2b`. The registry has no entry for them. They are named here so that a
  reader does not take the registry for a list of what the service offers.

## Resolving and linking

```python
from scripts.experiments import neuronpedia as nps

found = nps.resolve("qwen3.5-2b-base", "ica_component")   # Resolution(status="mapped", ...)
found.verified                                            # False: an alias never reads as verified
nps.resolve("qwen3.5-2b-base", "ica_component", 1).status # "no_mapping": the hosted set has layers 0, 4, 8, ...
nps.resolve("gemma-2-2b", "sae_latent").status            # "no_mapping", with the reason
nps.link_or_fallback(found, 3, layer=4, record={"signed_score": -0.5})
# {"kind": "none", "link": None, "reason": "mapping not verified", "detail": ..., "reference": None,
#  "reference_reason": "reference link not requested", "reference_detail": ..., "local": {...}}
```

`resolve` returns a `Resolution` with status `mapped`, `no_mapping` or `ambiguous`. Two matching
entries give `ambiguous` with both ids; the caller narrows the query. Nothing is picked.

`build_link` and `build_reference_link` are two functions with two result types. `build_link`
returns a `Link` of kind `exact` and never a reference link. `build_reference_link` returns a
`ReferenceLink` of kind `reference` and never an exact link. The rest of this section is about
exact links; *Reference links* follows.

`build_link(entry, component_id, layer=None)` returns a URL only when both conditions hold:

1. `links_enabled` is true, which the validator allows only for `verified_exact`. Otherwise the
   reason is `mapping not verified`.
2. The entry records a `url_pattern` with the source it was read in. Otherwise the reason is
   `no recorded URL pattern`.

No text can enter a URL. The rule has five parts.

- `build_link` and `link_or_fallback` take a registry entry, an integer component id and an
  integer layer. They have no text parameter. `link_or_fallback` also takes `reference_page`, one
  word of a closed vocabulary (`model_page`, `source_page`, `lens_page`) that selects a reference
  page form and is never put in a URL; any other value is refused (`reference_page_kind`).
- A component id or layer that is not a non-negative integer is refused (`free_text_in_url`)
  before the entry's status is looked at.
- Both integers are bounded, with the same code. A component id is below the entry's
  `component_id.count` when the entry records one, and below 2**20 (1,048,576) in every case. A
  layer is below 4096. An integer is data like any other: a SHA-256 written as a decimal integer
  has up to 78 digits, and before this bound `build_link` put such a number at the end of a URL.
  The refusal message does not repeat the integer. What the bound leaves open: 20 bits in the
  component id and 12 bits in the layer, on an entry that records no count.
- A template is `https`, with a fixed host and path segments made of id characters and the
  placeholders `{model_id}`, `{source_set}`, `{source_id}`, `{layer}`, `{component}`. A query
  string, a fragment, percent-encoding and any other placeholder are refused at registry load
  (`url_template`).
- The assembled URL is checked against the same closed character set.

Two patterns the engine holds are deliberately not recorded, because each carries prompt text:

- the lens page `…/<model>/jlens?prompt=<urlencoded prompt>`
  (`scripts/export_jlens_transport.py:151-156`);
- the graph viewer `…/<modelId>/graph?slug=<slug>` (`medlang_circuits/graph_client.py:377-383`).
  The engine's slug is the first 40 slugified characters of the prompt plus a Unix time
  (`graph_client.py:117-119`).

The engine builds one feature URL today, an API path:
`/api/feature/<model>/<layer>-<source set>/<index>` (`neuronpedia_features.py:155`). It is a JSON
endpoint, not a page, and is not recorded as a link pattern. The service's documentation gives the
page form: a feature's URL is `neuronpedia.org/[MODEL_ID]/[SOURCE_ID]/[INDEX]`, and a source id is
the layer number followed by the source set name (record `docs.getting-started.key-concepts`, read
on 2026-11-10). That form would fit the registry's template rule. It is not entered as a
`url_pattern` in any real entry: no entry permits an exact link, so a pattern would change nothing
today, and entering one is left to the owner. It is not a reference page form either (*Why no
feature page*).

The fixture registry holds one `verified_exact` entry for the toy model so the link path runs
under test. Its host is `registry-fixture.invalid`. A synthetic registry may link only to a
`.invalid` host and a real registry never may (`synthetic_label`), so a fixture link reaches no
site and a real entry cannot borrow the fixture pattern. Three fixture entries also have reference
links on. Their evidence is synthetic and is stored under
`tests/fixtures/experiments/neuronpedia/reference_evidence/`: an index, two hand-written
source-set records and page records with invented hashes. A synthetic registry may name evidence
only under `tests/fixtures/experiments/neuronpedia/`, and a real one only under
`data/experiments/neuronpedia_evidence/`.

## Reference links

A reference link is a link to a page of the external service, shown as a reference. It says that
the service had a page under these ids on the retrieval date. It does not say that the page shows
the study's model or representation, and it permits no pooling and no parity statement.

```python
entry = nps.entry_by_id(nps.load_registry(), "qwen3.5-2b-base.ica-component.neuronpedia-alias")
nps.build_link(entry, 3, layer=4).url                        # None: "mapping not verified"
nps.build_reference_link(entry, "source_page", layer=4).url  # https://www.neuronpedia.org/qwen3.5-2b-pt/4-icalens-res
nps.link_or_fallback(entry, 3, layer=4)["kind"]              # "none": no reference unless asked for
nps.link_or_fallback(entry, 3, layer=4, reference_page="source_page")["kind"]   # "reference"
nps.require_exact_identity(entry, "pooling")                 # Refusal("identity_not_verified")
```

### The record a page renders

`ReferenceLink.as_record()`, which is also the value of `reference` in the result of
`link_or_fallback`, has exactly these ten keys (`REFERENCE_LINK_KEYS`):

| Key | Value |
|---|---|
| `kind` | always `"reference"` |
| `url` | the page URL: `https://www.neuronpedia.org/` and one or two path segments |
| `label` | the fixed sentence below, unchanged |
| `page` | the page form: `model_page`, `source_page` or `lens_page` |
| `registry_id` | the registry entry the link was built from |
| `evidence` | the saved record of the service the link was built from: `index` (the evidence index), `record_id`, `path` (the kept file), `sha256`, `bytes`, `retrieved_utc` |
| `read_utc_date` | the date that record was retrieved |
| `identity_status` | the entry's verification status, repeated so the reader sees it beside the link |
| `reason` | `reference link built from the recorded page form` |
| `detail` | the record ids of the page form, of the ids and of the fetched page |

The label is one constant, `REFERENCE_LABEL`. A page shows it beside every reference link:

> Reference page on Neuronpedia, an external service: the service record this link was built from
> names no checkpoint revision, so the hosted checkpoint is not identified and the link is not
> evidence that the page shows the study's model or representation.

`validate_reference_link(record, registry=None)` checks such a record for the code that stores or
renders one: the closed key set, the kind, the unchanged label, the URL (https, the fixed host, the
path shape of its page form, no query string) and the evidence fields. With a registry it also
compares the record with the entry. It refuses a record of any other kind (`link_kind`).

### How the two kinds are kept apart

- **Two result types.** `Link` has `url`, `reason`, `detail` and `kind: "exact"`. `ReferenceLink`
  has the fields of the table above and `kind: "reference"`. Neither function returns the other
  type.
- **Two keys in `link_or_fallback`.** The result has `kind` (`exact`, `reference` or `none`),
  `link`, `reason`, `detail`, `reference`, `reference_reason`, `reference_detail` and `local`.
  `link` is an exact link or null and is never a reference link. `reference` is a reference record
  or null. They are never both set: when an exact link is built, no reference is attempted.
- **Asked for explicitly.** `link_or_fallback` builds a reference only when the caller passes
  `reference_page`. Without it the result is what it was before, plus `kind` and the three
  reference keys, which then say `reference link not requested`.
- **Unchanged meaning for an existing reader.** With a reference, `link` is null and `reason` and
  `detail` still say why no exact link exists (`mapping not verified`). The site page of this
  release shows a link only for an https string under `link` with the built-link reason and the
  status `verified_exact` (the experiments page of the companion repository, read on 2026-11-10),
  so it shows a reference result as "no link" with that reason. It does not render the `reference`
  record; that needs a change in the companion repository.
- **Two flags in the registry.** `links_enabled` switches exact links and needs `verified_exact`.
  `reference.enabled` switches reference links and needs the reference status and a named record.

### What a reference URL is made of

Every safeguard of an exact link applies, and three are stricter.

- **A template recorded on the entry, from a source that was read.** `reference.pages` lists each
  page form with its template, the documentation page the form was read in (`source`,
  `form_record`) and the record of one fetched page of that form for the entry's ids
  (`instance_record`). The module also defines the one path a form may have, and the template must
  equal it: `/{model_id}` for `model_page`, `/{model_id}/{layer}-{source_set}` for `source_page`,
  `/{model_id}/jlens` for `lens_page`. Any other template is refused when the registry is loaded
  (`reference_template`).
- **https and a fixed host.** The host of a real registry is `www.neuronpedia.org` and no other.
  The documentation writes `neuronpedia.org`; the pages fetched answered at `www.neuronpedia.org`
  with no redirect, which is also the host the API records were read from. A fixture links only to
  a `.invalid` host (`synthetic_label`).
- **Ids from the registry, checked against the saved record.** The model id and the source set are
  the entry's. On every call the module reads the kept record from disk, compares its SHA-256 and
  size with the entry's copy, and checks that the record names that model id, the study's Hugging
  Face repository and, for a source page, a source id for the layer asked for.
- **One bounded integer.** The only number a caller supplies is the layer of a source page. It is
  a non-negative integer below 4096 (`free_text_in_url`), and it must be a layer the saved record
  lists and the entry records. A reference URL has no component index, so the 20 bits that the
  component id of an exact link leaves open do not exist here.
- **No query string, no text.** `build_reference_link(entry, page, layer=None, root=None)` takes a
  registry entry, one word of a closed vocabulary that is never put in a URL, an integer and a
  directory. The lens page is the form without a query string; the form with `?prompt=` is not
  recorded and cannot be built.
- **The offline fallback.** When no reference is permitted, `link_or_fallback` returns `reference:
  null` with the reason, and the `local` record. That includes a saved record that is absent or
  changed on the machine that builds the bundle: the refusal becomes `reference link refused` with
  its code in `reference_detail`.

`verify_reference_evidence(entry, root=None)` runs the file checks alone and returns what the
record confirms. A reference link is refused:

| Code | When |
|---|---|
| `reference_links_without_record` | the entry switches reference links on and names no evidence record, no Neuronpedia ids or no page form (at registry load, and for a hand-made entry) |
| `reference_evidence_missing` | the evidence index, the cited record or the kept file is absent |
| `reference_evidence_mismatch` | the index's record differs from the entry's copy (SHA-256, size, retrieval time, path), or did not answer HTTP 200 |
| `reference_evidence_hash` | the kept file no longer has the recorded SHA-256 and size |
| `reference_ids_not_confirmed` | the kept record does not name the entry's model id, the study's repository, the source set, or a source for the layer asked for |
| `reference_status` | the kept record has a key that names a revision, a commit or a hash |
| `reference_form_not_confirmed` | the entry records no such page form; or the documentation record or the fetched-page record of a form is absent or changed; or the fetched page is not a page of this entry's ids |
| `reference_page_kind` | `page` is not one of the three page forms. `feature_page` is refused here |

No refusal of a reference link repeats a value of the entry, of the arguments or of the saved
files. `test_no_refusal_of_a_reference_link_repeats_a_value` places a sentinel string in each
position and reads the message.

Cost: each call reads and hashes the kept record and the two evidence indexes (about 0.15 MB in
all) and reuses the parse of bytes it has already seen. A changed file is always read again.

### Why no feature page

A reference link points at a model page, at one layer's source page or at a lens page. It never
points at a feature page (model, source and feature index), although the documentation gives that
form. Three reasons, each from what the saved evidence does and does not confirm.

1. The saved record of an entry is its source-set record. It lists the source ids. It confirms no
   feature index. The number of directions of one source is in that record only for the two
   transcoder sets (`d_sae`); for the hosted ICA set it is in a documentation page (2,048 for
   Qwen3.5 2B Base; record `docs.research-releases.ica-lens`), not in the record that is hashed.
   The one feature record read per set (layer 0, index 0) is not kept, because it holds dataset
   text and user names, so its hash cannot be checked again.
2. No feature page was fetched. The site answers HTTP 200 with an empty page for an id it does not
   have, so a URL built for an unconfirmed index could be an empty page under a reference label.
3. A feature page beside a component number reads as "this is that component". For a component of
   a local fit that is false unless the hosted basis is the same file, which is the identity claim
   the verification status decides. The module cannot tell where a component index came
   from, so it does not put one in a reference URL.

The case where a feature-level reference would be sound is a node of a hosted graph: its feature
index was issued by the service under the same ids. Supporting that needs a rule that records
where an index came from, and it is left to the owner (*What was verified, and what was not*).

## Snapshots and request records

`record_snapshot(path, source_url, retrieved_utc)` hashes a file somebody already downloaded and
returns `{sha256, bytes, source_url, retrieved_utc, not_recorded}`. It fetches nothing and reads
no clock. A source or a retrieval time that is not known is passed as `None` and listed in
`not_recorded`. A URL with a query string or a user part is refused (`snapshot_url`): a pre-signed
download URL carries a credential, and both repositories are public.
`verify_snapshot(path, record)` refuses `snapshot_missing`, `snapshot_size` or `snapshot_hash`. On
a match it reports `provenance_complete: false` when the record lists missing provenance. A
matching hash does not repair an unknown source.

A request record (`patientwords.api-request-record/1`) describes one bounded API call that some
other code made: `endpoint` `{method, host, path}`, `effective_request_settings` (what the
service applied, defaults included, with the input named by hash), `service_identity`
(`service`, `model_id`, `instrument_revision`), `response_sha256`, `retrieved_utc`,
`not_recorded`. This is a structure with validation. No code in this package sends a request.

Neither `effective_request_settings` nor `service_identity` may hold prompt text or a credential,
at any depth. Both repositories are public and a validated record is a file that gets committed,
so the check has three parts.

- **By key name.** A key is lowercased and stripped of everything except letters and digits. It is
  refused when the result contains a credential fragment (`key`, `token`, `secret`, `auth`,
  `password`, `passwd`, `pwd`, `cookie`, `bearer`, `credential`, `session`, `signature`, `header`,
  `jwt`; code `secret_in_record`) or a text fragment (`prompt`, `text`, `message`, `content`,
  `input`, `query`, `body`, `slug`, `completion`, `utterance`, `transcript`; code
  `prompt_text_in_record`), whatever the value is. The repository's own secret names
  (`ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `GEMINI_API_KEY`, `NEURONPEDIA_API_KEY`, `HF_TOKEN`)
  and spellings such as `x-api-key`, `apiKey`, `access_token`, `promptText` and `user_prompt` are
  all refused by this rule. There are two exceptions, each with its own value rule. A key that ends
  in `sha256` (`prompt_sha256`, `token_sha256`) must hold 64 hex digits or null. Four counted
  settings, matched by exact name (`numCompletionTokens`, `filterNonWordTokens`, `max_tokens`,
  `max_new_tokens`), must hold a boolean or an integer; the first two are fields of the engine's
  own lens request (`scripts/jlens_readout.py`, `lens_request_body`).
- **By value type.** A value is null, a boolean, a finite number, an object, or a list of those. A
  string is accepted only under an id key (`model_id`, `modelId`, `source_set`, `sourceSetName`,
  `source_id`, `service`, `instrument_revision`, `model_revision`, `dictionary_revision`, `type`,
  `lens`, `lens_type`, `dtype`), where it must be one id (at most 64 characters, no whitespace,
  optionally `owner/name`). A list of strings is accepted under one key, `type`. That is the only
  field of the engine's own request bodies that holds one: the lens request sends
  `"type": [lens_type]` with `JACOBIAN_LENS` or `LOGIT_LENS` (`scripts/jlens_readout.py:52-68`), and
  the graph request holds no list (`medlang_circuits/graph_client.py:304-321`). Such a list has 1
  to 8 distinct items, each an upper-case constant (`[A-Z][A-Z0-9_]{0,31}`). A list under any other
  id key, a longer list, a repeated item and an item of another form are refused, as is any
  string inside any other list (`free_text_in_record`). A key must itself be a short identifier.
- **By the credential screen** (`secret_in_record`). Two tests.
  - *Issuer prefix.* A string is refused when a `/`-separated part of it starts like a credential
    of a known issuer (`sk-`, `hf_`, `AIza`, `ghp_`, `gho_`, `github_pat_`, `xox`; any letter
    case), wherever the string sits. The same test is applied to every key name, to every segment
    of the endpoint path and to every label of the endpoint host. A host cannot hold an
    underscore, so a host label is also tested against the prefixes with a hyphen in its place: a
    host label that begins `hf-` is refused. That refuses some harmless host names. The rule is kept
    because a validated record is committed to a public repository.
  - *Token form.* A string under an id key, a segment of the endpoint path or a label of the
    endpoint host is refused when it holds a run of more than 24 letters
    and digits with no separator that draws on at least two of lower-case letters, upper-case
    letters and digits. A path segment and a host label have no exception: a commit id or a
    content hash in a path is refused too, and a record names its response by `response_sha256`. Issued tokens have that form; the ids the engine and the registry use do
    not. The one exception is 40 or 64 lower-case hex digits under `model_revision`,
    `instrument_revision` or `dictionary_revision`: a commit id or a content hash. A key that ends
    in `sha256` holds 64 hex digits by its own rule.
- **`not_recorded`.** The list is checked before anything else reads it. It holds at most 256
  distinct entries. Each is a JSON pointer made of key names and list indexes under
  `/effective_request_settings`, `/service_identity`, `/response_sha256` or `/retrieved_utc`, and
  each must point at a field that is null (`not_recorded_pointer`). A sentence or a credential
  appended to the list is refused by the first rule, and a well-formed pointer that names no null
  field by the second.

The endpoint host has at most 8 labels of letters, digits and hyphens, each at most 63 characters.
The endpoint path has at most 8 segments of id characters, each at most 64 characters, with no
query string.

No refusal of a request record repeats a value, an entry of `not_recorded`, or a key that failed
the key-form check or the prefix test. A message names the keys that passed both, list positions
and counts: a refused entry of `not_recorded` is reported as "1 of the 2 entries, at position(s)
[1]", and a refused key as "key number 3" of its object in sorted order. A key that is a short
identifier and is refused for a fragment (`api_key`, `user_prompt`) is named, because the name is
what the reader has to remove. `test_no_refusal_of_a_request_record_repeats_a_value` and
`test_a_not_recorded_entry_is_checked_as_a_pointer_and_never_repeated` place a sentinel string in
each position and read the message.

The other validators of the module follow the same rule in a weaker form, because the documents
they check hold ids and public label text. A message repeats a value only after that value passed
an id, hash, date or integer check. A value that failed its check (a method id, a verification
status, a quantity kind, a source URL, an entry of `not_recorded`) and a key that is not a short
identifier are reported by position, count or type
(`test_refusals_of_the_other_records_repeat_no_value_that_failed_its_check`). One exception is
outside this module: a structural error of the registry comes from the shared schema checker
(`scripts/experiments/common.py`, `require_structure`), which prints the path of the offending
key, including a key the schema does not allow.

What the check cannot see.

- A credential that passes the screen: one of 24 characters or fewer; one with a separator at
  least every 24 characters; one made of a single character class (lower-case letters only, for
  example); one from an issuer whose prefix is not in the list; one whose issuer prefix is not at
  the start of a `/`-separated part and whose remainder is not token-shaped.
- A short text that has the form of an id and is stored under one of the id keys (one id, 64
  characters per part), and up to 8 upper-case words in the `type` list.
- Words spelled as a key name, as a host label or as one of the at most 8 path segments.
- A number that encodes something.

The check reads key names, value types, character classes and string forms. It does not read
meaning. A request record still needs a person's review before it is committed.

Why the record asks for effective settings and service identity. The hosted graph API ignores an
unknown key without an error (`graph_client.py:319-320`), so the request that was sent is weaker
evidence than the settings the service applied. The hosted lens changed its readouts on 2026-07-31
and 2026-08-14 under byte-identical requests (`scripts/export_jlens_depth.py:409-417`), and no
landed summary has a field that separates the three periods (`scripts/jlens_readout.py:310-324`).

## Explanation provenance

An explanation record (`patientwords.feature-explanations/1`) belongs to one component of one
registry entry.

- **Labels.** Every competing label is kept, each with `source`
  (`name`, `version`, `explanation_type`, `explanation_model`, `retrieved_utc`) and `scorer`
  (`{name, version}` or null and listed). No key stores a chosen label; `add_label` appends and
  refuses a duplicate id. Every label has `status: "hypothesis"`.
- **Closed key sets.** A label holds exactly `label_id`, `text`, `basis`, `flags`, `status`,
  `source` and `scorer`, plus `tokens` for a token-list label. A source holds exactly its five
  keys and a scorer exactly `name` and `version`, in a label and in a quantity record; their values
  are strings or null. A flag is one of the known flags. A confidence, a rank, a "best" or
  "selected" marker, or a number under any other name is therefore refused inside a label, its
  source or its scorer (`explanation_record`; `merged_score` when the key is a generic score key or
  ends in `score`; `quantity_fields` inside a quantity record's scorer).
- **Token-list labels.** A label built from a token list alone has `basis: "token_list_only"` and
  the flag `not_a_clinical_concept_name` (display text: "not a clinical concept name"). The
  validator refuses that basis without the flag, and it refuses any label that carries `tokens`
  without the flag, whatever basis the label declares. A token-list text stored without its
  `tokens` and under another basis cannot be told from a written label; that limit is not tested.
- **Four quantities, four fields.**

| Field | What it is | Never |
|---|---|---|
| `feature_interpretability_score` | how well any description accounts for the component, under a named scorer | a property of one label |
| `label_prediction_score` | how well one named label predicts the activations, under a named scorer | a property of the component |
| `lens_token_rank` | the integer rank of one token in one lens readout at one layer, with its rank base | a score between 0 and 1 |
| `clinical_outcome` | a study outcome that PatientWords owns, referenced by id | produced by a scorer |

Each record repeats its field name in `kind`. A record filed under another field is refused
(`score_kind_mismatch`), a generic `score` key or a fifth field is refused (`merged_score`), and
`collect_quantity` refuses records of two kinds (`score_kind_merge`). A missing value is null with
a `missing_reason`. It is never zero.

Why this is stricter than the engine's current label path. `FeatureFetcher` keeps only
`explanations[].description` and joins all of a feature's explanations with `" | "`
(`neuronpedia_features.py:199-202`). After the join, the explanation type, the explainer and any
score of each part cannot be recovered, and the cache entry has no retrieval time. A feature that
gains a second explanation later changes its joined text and can change its keyword tag with no
recorded cause. This change does not edit that path. A future fetch that fills the record above
would keep what the join discards.

## Graph interchange: contract plan

This milestone's slice contains no attribution graph. What is delivered is
`validate_graph_reference` for the payload kind `attribution_graph_ref/1`, and the plan below. An
exporter is not implemented. An upload or a community submission to Neuronpedia is a separate
publishing action with its own approval and is not implemented either.

### The reference payload

`attribution_graph_ref/1` names a graph that lives elsewhere. It holds ids, hashes and source-set
identity:

| Block | Keys |
|---|---|
| top level | `kind`, `registry_id`, `settings_sha256`, `retrieved_utc`, `not_recorded` |
| `model` | `study_id`, `hf_id`, `revision` |
| `neuronpedia` | `model_id`, `source_set` (both required: a graph's nodes index one source set) |
| `graph` | `native_retained`, `native_sha256`, `native_bytes`, `schema_version`, `slug_sha256`, `n_nodes`, `n_links` |
| `input` | `prompt_sha256`, `token_sha256` |

The key set is closed. There is no prompt, no slug (only its hash), no label and no node list.
Every string is checked against an id-only character set. With a registry, the Neuronpedia ids
are compared with the entry (`source_set_identity`), and so is the model: study id, Hugging Face
id and revision (`graph_ref_identity`). A reference whose `model.revision` differs from the
entry's pin is refused, because the same ids can name another commit. A reference whose revision
is null must list `/model/revision` in `not_recorded`; the revision is then not compared, and the
result says `model_revision_compared: false`. It says the same when no registry is given. A graph that was not
retained has `native_retained: false` and no native hash; the hash of a pruned or annotated copy
is refused in its place (`graph_native_artifact`).

One limit of the text check: a string made only of id characters is accepted. A slug with hyphens
in a field such as `model.study_id` would pass the character test. The closed key set and the
registry comparison are what stop it, so validate against the registry.

### What a validator and exporter must check

The fields below are the ones the engine's own parser and fixtures use. Paths given without a
directory are under `medlang_circuits/`. Neuronpedia's schema file
is cited in the engine by repository path only (`apps/webapp/app/api/graph/graph-schema.json`,
`medlang_circuits/feature_tagger.py:4`, `README.md:56`). No copy of it is in any checkout. The
validator page was fetched on 2026-11-10 (record `page.graph.validator`): it shows a JSON Schema
titled "Anthropic Attribution Graph", version 1.0.0, and says that the model matching the graph's
`metadata.scan` value must be on Neuronpedia. The table below was written before that and has not
been compared with the schema field by field. It is therefore still the engine's reading of the
contract, not the contract.

| Area | Check | Fields known from engine code |
|---|---|---|
| Model and source registration | `metadata.scan` is a registered Neuronpedia model id, and the source set the graph was generated with is the registry entry's. Compare the graph's own `metadata.feature_details.neuronpedia_source_set` with the set used for labels | `metadata.scan`, `metadata.schema_version` (`feature_tagger.py:94-96`); `metadata.feature_details.neuronpedia_source_set`, read only when no fetcher is passed (`feature_tagger.py:98-105`); request field `sourceSetName`, sent only when given (`graph_client.py:314-315`) |
| Feature-index encoding | State `schema_version` and decode with the matching rule. A decoded (layer, index) must lie inside the source set's layers and width | schema 1: `node.feature` is the Cantor pairing of (layer, index) (`schema_utils.py:30-36,56-57`); older `gemma-2-2b` graphs: `layer * 100000 + index` (`schema_utils.py:59-65`); otherwise `node.layer` and the raw index (`schema_utils.py:67-71`) |
| Node and edge references | Every `links[].source` and `links[].target` names an existing `node_id`. `node_id` values are unique. Every `feature_type` is a known one. Weights are finite | node keys `node_id`, `feature`, `layer`, `ctx_idx`, `feature_type`, `jsNodeId`, `clerp`, `influence`, `activation`; link keys `source`, `target`, `weight` (`tests/conftest.py:23-56`); feature types (`schema_utils.py:14-25`) |
| Prompt-token alignment | `metadata.prompt_tokens` equals the tokenization of the prompt under the recorded tokenizer revision, and every node's `ctx_idx` is inside it. The envelope's `token_sha256` must match | `metadata.prompt`, `metadata.prompt_tokens` (`tests/conftest.py:26-31`); `ctx_idx` used as the token column (`compare_viz.py:193,250`) |
| Method settings | Record the settings the service applied, not only the ones sent, with their bounds | request fields `maxNLogits`, `desiredLogitProb`, `nodeThreshold`, `edgeThreshold`, `maxFeatureNodes`, optional `qkTopFraction`, `qkTopk` (`graph_client.py:304-321`); client-side bounds (`graph_client.py:66-75`); an unknown key is ignored without an error (`graph_client.py:319-320`); top-level `qParams` exists in the fixtures and is not read by any engine code |
| Native artifact | Keep the graph JSON as returned, byte for byte, and record its SHA-256 and size before any pruning or annotation | today the only stored copy is written after logit pruning and after `annotate_graph` changed it in place (`batch_eval.py:410-417`); it is a workflow artifact, not a committed file (`.github/workflows/circuit_trace_evaluation.yml:553`) |
| Reconstruction and error information | Keep error nodes and their edges. Report the share of attribution on error nodes beside any feature statistic. Do not drop them to make a graph smaller | `feature_type` values `mlp reconstruction error` and `lorsa error` (`schema_utils.py:20-21`); `error_node_share` (`batch_eval.py:193-212`); summary field `error_share` |
| Feature detail | A node's label is fetched separately and can change. Record it as an explanation record with source and retrieval time, not as text inside the graph | `GET /api/feature/<model>/<layer>-<source set>/<index>`; response keys read: `explanations[].description`, `activations[].tokens`, `activations[].values` (`neuronpedia_features.py:155,199-224`) |

Not specified here, because the fetched schema has not been reconciled with this table: the
validator's required and optional fields; the `qParams` contract; the `metadata.feature_details`
contract beyond the one key above; any size limit on upload; whether the validator accepts graphs
from a source set that is not registered on the site. The feature-detail response read on
2026-11-10 has 46 top-level keys, of which the engine reads `explanations` and `activations`; the
four `api.feature.*` records list the identity fields.

### Three gaps in the current hosted path that an exporter would hit

Each is a property of existing engine code, stated with its failure path. None is changed here.

1. **The native graph is not retained.** A landed trace cannot be re-validated or re-exported
   without a new trace, because the stored copy is pruned and annotated (`batch_eval.py:410-417`)
   and is kept only as a workflow artifact. A reference to a landed trace therefore has
   `native_retained: false`.
2. **The hosted slug is not in the summary.** The summary dict has no slug field
   (`batch_eval.py:1288-1299`), so a summary row cannot be joined to the hosted graph. The slug also
   embeds prompt characters, which is why the reference keeps only `slug_sha256`.
3. **Graph source set and label source set are not compared.** The study does not send
   `sourceSetName`, so the service applies the model's default set, while labels are fetched from
   the engine's own table (`neuronpedia_features.py:45-59`). If the service's default changes,
   graphs come from the new set and labels from the old one, and the summary still records the old
   name. The graph's own `neuronpedia_source_set` would show it and is not read in the batch path.

## What a dated announcement does not guarantee

A blog post, a release note or a search result is a statement about one date. It does not
establish, for today:

- **Model coverage.** That a model id is served, or that a representation exists for the commit
  the study pins. The engine's own record shows coverage moving: `qwen3-4b` returned errors on
  2026-07-07 and served graphs from 2026-09-02 (`graph_client.py:39-41`).
- **API limits.** The engine records no numeric rate limit. It retries on HTTP 429, 500, 502, 503
  and 504, four attempts (`graph_client.py:156-158`). The documentation read on 2026-11-10 (record
  `docs.getting-started.accounts`) gives default limits per 60-minute window, among them 30 for
  `/api/graph/generate`, 240 for `/api/lens/prompt` and 25,000 for endpoints it does not list. That
  is the documentation of one date. It says that a key can be given higher limits, and it does not
  say what the study's key is allowed.
- **Artifact compatibility.** That a released basis, lens or dictionary was fitted on the same
  commit, tokenizer, site and precision as a study run. The ICA fork's saved lens records no
  tokenizer identity and no tensor hashes (`docs/experiment_interface/ica_adapter.md`,
  *Identity fields*).
- **Stability of a hosted instrument.** The hosted lens changed under identical requests twice in
  2026.

The registry is where a claim of this kind becomes checkable: an entry changes status only with
an evidence item that names a source and a date.

## Roadmap

Each linked post was fetched on 2026-11-10 (HTTP 200; record `blog.<name>` in the evidence index,
with its hash). The posts were searched for statements about commits, revisions and checkpoints and
for the items this page cites; apart from `blog/neurons-ica` they were not studied in full. The
descriptions say what the project holds, not what a post says.

| When | Item | What the project holds today | Link status |
|---|---|---|---|
| now | interp-engine | CPU eager backend used in push-to-run CI; one recorded float32 agreement audit for `gemma-2-2b` next-token behaviour (`docs/backend_agreement_20260903.md`); the fork's README says the engine powers Neuronpedia's inference (`patientwords-interp-engine/README.md:16`, fork head `2afe000d`) | `blog/interp-engine`: fetched; dated August 31st, 2026 |
| now | ICA | offline adapter and toy fixtures (`ica_adapter.md`); four released bases named in the ICA fork, none read; the Neuronpedia id for `qwen3.5-2b-base` confirmed, its checkpoint commit not reported | `blog/neurons-ica`: read; dated November 9th, 2026; lists ICA lenses for 6 models |
| now | existing lenses | hosted J-lens readouts for `gemma-2-2b` and `gemma-2-2b-it`, instrument revision not recorded; a released Qwen3-4B J++ artifact whose fit identity is unknown (capability matrix) | `blog/jpp-drift-ui`: fetched; dated October 15th, 2026 |
| now | neuron / ICA comparisons | nothing run. The registry has no `neuron` entry. A comparison needs both representations on one verified checkpoint | `blog/neurons-ica`: read |
| now | graph interchange | the reference payload and the plan above; no exporter | `graph/validator`: fetched, schema not reconciled; `blog/circuit-tracer`: fetched; dated June 13th, 2025 |
| next | HeadVis | nothing. No `attention_head` entry | `blog/headvis`: fetched; dated June 9th, 2026 |
| next | attention-aware graphs | the engine names one model traced with attention replacement and its two request parameters (`graph_client.py:62-64`); that model's hosted graphs are capped at 10 prompt tokens, which study prompts exceed (`neuronpedia_features.py:56-58`) | `blog/circuit-tracer`: fetched |
| next | temporal analysis | nothing. To be opened only for a defined hypothesis about reference, negation or information retained over turns | none |
| optional study | NLAs | nothing | `blog/nlas`: fetched; dated May 17th, 2026 |
| optional study | Assistant Axis, Drift Calibrator | nothing | `blog/assistant-axis`: fetched; dated January 28th, 2026; `blog/jpp-drift-ui`: fetched |

Conditions attached to the later rows.

- **Attention.** An attention pattern shows where a head reads from. It does not establish that
  the head causes an output. A claim about cause needs an intervention with a control, on a
  hypothesis stated before the run.
- **NLAs.** The post was fetched and not studied, so this page does not define the method. Any method that
  returns a natural-language account of an activation can return a fluent account that is wrong. A
  study that uses one needs a confabulation test (for example: does the account change when the
  activation is replaced by an unrelated one) and a misleading-explanation test (for example: does
  a reader predict the model's behaviour worse with the account than without it). Neither test
  exists here.
- **Assistant Axis and Drift Calibrator.** These would be used for turn-level drift or for
  calibrating a reader. A normalized activation similarity is a geometric quantity. It is not a
  probability of clinical error, and it would be stored as its own quantity, never as a
  `clinical_outcome`.
- **Interp Explorer.** The owner's task brief of 2026-11-10 says the Interp Explorer post reports
  that development paused in July. The post, read on 2026-11-10 (record `blog.interp-explorer`;
  dated April 21st, 2026), carries this line in its Interpretability Explorer section: "Update July
  2026 - We're pausing work on Interp Explorer as we figure out a more intuitive way to surface
  great interp content."

## What was verified, and what was not

| Statement | Evidence |
|---|---|
| The registry rules, link rules, snapshot checks, record validators and graph-reference rules behave as written | `tests/test_experiments_neuronpedia.py`, offline, on a synthetic registry and the real registry file |
| Real entries agree with the engine's tables | the same tests compare study ids, Hugging Face ids and pins with `scripts/logits_eval.py`, source sets with `neuronpedia_features.MODEL_SOURCE_SETS`, the calibrated pair with `scripts/feature_models.py`, and artifact ids with the capability matrix |
| Real entries agree with the service's records of 2026-11-10 | the tests read the kept bodies and the index: model id, source set, layer list and Hugging Face repository of each hosted entry equal the saved source-set record; every evidence item that cites a URL names a record whose URL and date match; every kept body still has its recorded SHA-256 and size (`verify_snapshot`). This is evidence about that date. Nothing re-fetches |
| No record of the service names a revision | `test_no_record_of_the_service_names_a_revision` searches every kept body and the fields read of every record for a key that names a revision, a commit or a hash, and finds none |
| The module opens no socket | `test_importing_and_using_the_module_opens_no_socket` replaces `socket.socket`, `socket.create_connection` and `socket.getaddrinfo`, loads the module from its file, calls each of its twenty-one public functions (the five added with reference links among them) and asserts that the set it called equals the set the module defines; `test_module_imports_no_network_or_process_library` lists the imports |
| An exact link and a reference link cannot be taken for each other | `test_an_exact_link_and_a_reference_link_cannot_be_confused` runs each consumer path on a fixture entry that permits both kinds and on one that permits only a reference: `build_link`, `build_reference_link`, `link_or_fallback` with and without `reference_page`, and `validate_reference_link` |
| A reference link is built only from a saved record that still has its hash and names the ids | tests that remove the record, alter the kept file, point the entry at another record and ask for a page form the entry does not record; each is refused with the code listed under *Reference links* |
| Exact links, pooling and parity statements are refused for every real entry | `test_exact_links_pooling_and_parity_stay_refused_for_every_real_entry` and `test_the_real_registry_builds_exactly_these_reference_links_and_no_exact_link` |
| The reference URLs of the real registry resolve | verified for 2026-11-10 for the four model pages, the two lens pages and the source page of layer 0 of each of the three sets: fetched, HTTP 200, titled page. Inferred for the other 65 source pages from the saved source-set records and the documented form; not fetched. Not verified for any later date |
| A reference page shows the study's model or representation | not verified, and not claimed. The label of every reference link says so |
| A feature-level reference link | not supported. Whether to support one for a node of a hosted graph, whose index the service issued, is an owner decision |
| A request record holds no credential and no prompt text | checked by key name, value type, character class and the credential screen (issuer prefix; token form), on abstract placeholders and on dummy strings made of an issuer prefix and filler. Not verified: the cases listed under "What the check cannot see", which the check cannot tell from an id |
| A refusal of a request record repeats no value | a sentinel string is placed under each key, in `not_recorded`, in the endpoint and as a key, and the message is read (`test_no_refusal_of_a_request_record_repeats_a_value`, `test_a_not_recorded_entry_is_checked_as_a_pointer_and_never_repeated`, `test_a_string_with_a_credential_prefix_is_refused_wherever_it_sits`) |
| An integer in a URL is a component index or a layer number | bounded as described under *Resolving and linking*; `test_the_integers_of_a_url_are_bounded_so_a_hash_written_as_an_integer_is_refused` also builds no URL from any committed entry over layers 0 to 4095 and component ids up to 2**20 - 1 |
| The hosted ids resolve on the site | verified for 2026-11-10: the five hosted entries' model ids and source sets answered, each with a feature record or a lens page. Not verified for any later date |
| A hosted model id names the study's Hugging Face repository | verified for 2026-11-10, from the service's model records (`hfRepoId`) |
| Any hosted checkpoint equals a study pin | not verified. The service reported no revision for any model, dictionary, lens or basis, so no hosted revision is recorded anywhere |
| What a live lens response reports | not read. The route runs a model and was not called |
| Any exact URL pattern | the feature page form was read in the documentation. It is not recorded in the registry as `url_pattern`: no real entry permits an exact link |
| The graph contract | not verified. The validator page and its schema were fetched; the plan has not been reconciled with them and still lists the engine's reading |
| That a fixture link works | not applicable. The fixture host is under `.invalid` |

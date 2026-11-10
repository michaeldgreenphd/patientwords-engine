# Neuronpedia identity and link boundary (2026-11-10)

Status: registry, validators and an offline link builder. No link to a real Neuronpedia page is
built today. No real registry entry is `verified_exact`, no real entry records a URL pattern, and
none of the fourteen source pages this work was meant to be checked against could be read on
2026-11-10 (table below). Every Neuronpedia fact on this page is cited to engine source code or a
dated engine document, or is marked unverified.

Code: `scripts/experiments/neuronpedia.py`. Data: `data/experiments/representation_registry.v1.json`
(schema `patientwords.representation-registry/1`,
`schemas/experiments/representation_registry.v1.schema.json`). Fixtures:
`tests/fixtures/experiments/neuronpedia/` (synthetic). Tests: `tests/test_experiments_neuronpedia.py`.

The module makes no network request. It imports no HTTP client. One test,
`test_importing_and_using_the_module_opens_no_socket`, loads the module from its file and calls
each of its sixteen public functions with `socket.socket`, `socket.create_connection` and
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
  external link is an extra.
- An external label is a hypothesis with a source. It is never a study outcome. The four
  quantities in *Explanation provenance* stay in four fields.
- An external id is a field of a registry entry. It is never a key. `resolve` matches on the
  engine's study id only. A study id that is not a non-empty string is refused (`invalid_input`),
  so the three entries whose model the engine does not run (their `model.study_id` is null) are
  never returned by `resolve`.

## What was read on 2026-11-10

Each URL was requested once with WebFetch in this session. Every request failed with
`getaddrinfo ENOTFOUND <host>`: the three hosts are outside the session's allowed network
domains. No page content was read. An earlier pass on the same day had the same result.

| URL | Read today |
|---|---|
| `https://www.neuronpedia.org/blog/neurons-ica` | no: host blocked |
| `https://www.neuronpedia.org/blog` | no: host blocked |
| `https://arxiv.org/abs/2606.11722v2` | no: host blocked |
| `https://docs.neuronpedia.org/api-and-data/api` | no: host blocked |
| `https://docs.neuronpedia.org/sparse-autoencoders/auto-interp` | no: host blocked |
| `https://www.neuronpedia.org/graph/validator` | no: host blocked |
| `https://www.neuronpedia.org/blog/circuit-tracer` | no: host blocked |
| `https://www.neuronpedia.org/blog/interp-engine` | no: host blocked |
| `https://www.neuronpedia.org/blog/headvis` | no: host blocked |
| `https://www.neuronpedia.org/blog/nlas` | no: host blocked |
| `https://www.neuronpedia.org/blog/assistant-axis` | no: host blocked |
| `https://www.neuronpedia.org/blog/jpp-drift-ui` | no: host blocked |
| `https://www.neuronpedia.org/blog/interp-explorer` | no: host blocked |
| `https://www.neuronpedia.org/blog/fall-update` | no: host blocked |

The registry file repeats this list under `sources_not_read`. To unblock: add
`www.neuronpedia.org`, `docs.neuronpedia.org` and `arxiv.org` to the session's allowed network
domains. `huggingface.co` is also blocked from development containers (engine `AGENTS.md`), so no
released basis manifest was read.

What this leaves unknown, stated once: the Neuronpedia model id and the ICA source-set id for the
Qwen3.5 2B base checkpoint; the checkpoint commit behind any hosted model id; the layer and site
naming of the ICA sources; every human-facing page URL pattern; bulk export locations and file
formats; numeric API limits; the graph validator's field list; explanation-type ids and scorer
names beyond the two the engine documents; the arXiv version dates.

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
| `url_pattern` | a page template with the source it was read in and the date, or null |
| `verification` | `status`, `hosted_checkpoint_revision`, `evidence` items `{source, date, states}`, `checked_utc_date` |
| `links_enabled` | true only with `verified_exact` |
| `not_recorded` | JSON pointers of every null field in the entry |

A null means the registry holds no value. A null whose pointer is not in `not_recorded` is refused
(`silent_missing_provenance`), and so is a listed pointer that is not null. A field that does not
apply holds the string `not_applicable`.

### Verification statuses

| Status | Meaning | Link |
|---|---|---|
| `verified_exact` | The ids were read in a primary source, and the hosted checkpoint revision is recorded and equals the study revision. The validator refuses this status without both revisions equal | permitted |
| `alias_unverified_checkpoint` | Another id is given for the same checkpoint by the source that the entry's `id_source` names. No record of the commit behind that id was read | none |
| `hosted_identity_unknown` | The engine uses these hosted ids and responses have landed. The engine records no model, dictionary or instrument revision for these responses; whether the service reports one was not read | none |
| `unverified` | The representation is named in a source that was read. Its own manifest or page was not | none |

An alias alone does not verify a checkpoint. Two ids can name the same model family and different
commits, or the same commit served at another precision. `verified_exact` therefore needs
`hosted_checkpoint_revision` to equal `model.revision`, and `links_enabled: true` with any other
status is refused (`links_without_verification`).

### Id mapping on 2026-11-10

| Engine study id | Representation | Neuronpedia model id / source set | Artifact | Status | Evidence |
|---|---|---|---|---|---|
| `gemma-2-2b` | `transcoder_feature` | `gemma-2-2b` / `gemmascope-transcoder-16k` | hosted set; weights commit not recorded | `hosted_identity_unknown` | `medlang_circuits/neuronpedia_features.py:30,46,155`; `scripts/feature_models.py:31` (the one calibrated pair) |
| `qwen3-4b` | `transcoder_feature` | `qwen3-4b` / `transcoder-hp` | `mwhanna/qwen3-4b-transcoders`, commit not recorded | `hosted_identity_unknown` | `medlang_circuits/neuronpedia_features.py:55`; `docs/cross-model.md:33-63` (2026-10-09). Labelled, not calibrated: exploration only |
| `gemma-2-2b` | `workspace_readout` (hosted J-lens) | `gemma-2-2b` / not applicable | `neuronpedia-hosted:JACOBIAN_LENS`; no instrument revision | `hosted_identity_unknown` | `scripts/jlens_readout.py:44,52,60,310-324`; `scripts/export_jlens_depth.py:409-417` |
| `gemma-2-2b-it` | `workspace_readout` (hosted J-lens) | `gemma-2-2b-it` / not applicable | same | `hosted_identity_unknown` | same |
| `qwen3.5-2b-base` | `ica_component` | `qwen3.5-2b-pt` (unverified) / not recorded | not recorded | `alias_unverified_checkpoint` | engine pin `scripts/logits_eval.py:109,147`; the id comes from the owner's task brief of 2026-11-10 and has no retrievable record; page not read |
| `gemma-2-2b` | `ica_component` | none | `sida/icalens-gemma-2-2b-pile10k` | `unverified` | `patientwords-ica-lens-paper/docs/fit-and-publish.md:289-292`; `patientwords-ica-lens-paper/experiments/reconstruction/official/results/gemma2/run.json:181-183` |
| none | `ica_component` | none | `sida/icalens-gpt2-small-pile10k` (`openai-community/gpt2`) | `unverified` | `patientwords-ica-lens-paper/README.md:23` |
| none | `ica_component` | none | `sida/icalens-qwen3.5-9b-base-pile10k` (`Qwen/Qwen3.5-9B-Base`) | `unverified` | `patientwords-ica-lens-paper/docs/fit-and-publish.md:289-292` |
| none | `ica_component` | none | `sida/icalens-qwen3.5-2b-ultrachat-1m` (`Qwen/Qwen3.5-2B`, the instruct model) | `unverified` | `patientwords-ica-lens-paper/README.md:53`, `patientwords-ica-lens-paper/docs/fit-and-publish.md:167-176` |

Paths that start with `patientwords-ica-lens-paper/` are in the fork
`michaeldgreenphd/patientwords-ica-lens-paper` at `aa3b95c9e755e4374f8c9645a064e3f51d96066e`.

Notes on single rows.

- **`qwen3.5-2b-base` and `qwen3.5-2b-pt`.** The engine pins `Qwen/Qwen3.5-2B-Base` at
  `b1485b2fa6dfa1287294f269f5fb618e03d52d7c` (`scripts/logits_eval.py:147`; chosen as the head of
  `main` on 2026-10-09, `docs/model_matrix.md:285-293`). The id `qwen3.5-2b-pt` has one origin: the
  owner's task brief of 2026-11-10 for this session supplied it. The brief is not a file in the
  repository and no retrievable record of it exists here. The id is unverified against the
  service: `www.neuronpedia.org` was blocked by this environment's network policy on 2026-11-10,
  so no Neuronpedia page was read. Unverified for the same reason: the ICA source-set id, the
  layers and the commit the components were fitted on. The registry and
  `data/experiments/capability_matrix.v1.json` state the same origin. The ICA fork records no
  revision of this model, no Neuronpedia id and no released ICA basis for it. It names the model in
  places that are not a released basis: `patientwords-ica-lens-paper/notes/naming.md:24` lists
  `sida/icalens-qwen-3.5-2b` as a repository id in its naming scheme, without saying base or
  instruct and without saying that the repository exists;
  `patientwords-ica-lens-paper/integrations/r_lens/fit_qwen35.py:21-24` holds an R-lens fitting
  preset for `Qwen/Qwen3.5-2B-Base`, which is not an ICA basis. To reach `verified_exact`: read
  the Neuronpedia model record and the release manifest, record the commit, and confirm it equals
  the pin.
- **`sida/icalens-gemma-2-2b-pile10k`.** The paper's reconstruction run record names this basis
  with model revision `c5ebcd40d208330abc697524c919956e692655cf`, which is the engine's pin of
  `google/gemma-2-2b` (`scripts/logits_eval.py:132`). That is one evaluation run. The record pins no
  basis revision, and the fit revision stored in the basis manifest was not read. The status stays
  `unverified`.
- **`sida/icalens-qwen3.5-2b-ultrachat-1m`** was fitted on the instruction-tuned model. It is not
  a basis for the engine's `qwen3.5-2b-base`.
- **`gemma-2-2b` with `gemmascope-transcoder-16k`.** The status is strict on purpose. A hosted
  graph and its feature labels come from the same service under the same ids, so a link from a
  node of that graph to its feature would be id-consistent by construction. What is unknown is the
  model commit and the transcoder weights commit behind those ids, which matters as soon as a
  locally loaded model is compared with a hosted feature. The four-word vocabulary has no status
  for "ids consistent within the service, checkpoint not attested". Adding one is an owner
  decision; this change does not add it.

## Resolving and linking

```python
from scripts.experiments import neuronpedia as nps

found = nps.resolve("qwen3.5-2b-base", "ica_component")   # Resolution(status="mapped", ...)
found.verified                                            # False: an alias never reads as verified
nps.resolve("gemma-2-2b", "sae_latent").status            # "no_mapping", with the reason
nps.link_or_fallback(found, 3, layer=1, record={"signed_score": -0.5})
# {"link": None, "reason": "mapping not verified", "detail": ..., "local": {...}}
```

`resolve` returns a `Resolution` with status `mapped`, `no_mapping` or `ambiguous`. Two matching
entries give `ambiguous` with both ids; the caller narrows the query. Nothing is picked.

`build_link(entry, component_id, layer=None)` returns a URL only when both conditions hold:

1. `links_enabled` is true, which the validator allows only for `verified_exact`. Otherwise the
   reason is `mapping not verified`.
2. The entry records a `url_pattern` with the source it was read in. Otherwise the reason is
   `no recorded URL pattern`.

No text can enter a URL. The rule has five parts.

- `build_link` and `link_or_fallback` take a registry entry, an integer component id and an
  integer layer. They have no text parameter.
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
endpoint, not a page, and is not recorded as a link pattern. A page path of the form
`/<model>/<layer>-<source set>/<index>` appeared in search-result URLs on 2026-11-10. It was not
read in a page or in source code: unverified, and not in the registry.

The fixture registry holds one `verified_exact` entry for the toy model so the link path runs
under test. Its host is `registry-fixture.invalid`. A synthetic registry may link only to a
`.invalid` host and a real registry never may (`synthetic_label`), so a fixture link reaches no
site and a real entry cannot borrow the fixture pattern.

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
`medlang_circuits/feature_tagger.py:4`, `README.md:56`). No copy of it is in any checkout, and the
validator page was not read. The list is therefore the engine's reading of the contract, not the
contract.

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

Could not be read today, and so not specified here: the validator's required and optional
fields; the `qParams` contract; the `metadata.feature_details` contract beyond the one key above;
the feature-detail response schema beyond the three keys the engine reads; any size or rate limit
on upload; whether the validator accepts graphs from a source set that is not registered on the
site.

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
  and 504, four attempts (`graph_client.py:156-158`). Limits named in search summaries were not
  read in a page and are not repeated here.
- **Artifact compatibility.** That a released basis, lens or dictionary was fitted on the same
  commit, tokenizer, site and precision as a study run. The ICA fork's saved lens records no
  tokenizer identity and no tensor hashes (`docs/experiment_interface/ica_adapter.md`,
  *Identity fields*).
- **Stability of a hosted instrument.** The hosted lens changed under identical requests twice in
  2026.

The registry is where a claim of this kind becomes checkable: an entry changes status only with
an evidence item that names a source and a date.

## Roadmap

Status of each external link is "not read on 2026-11-10" for every row, because the host was
blocked. The descriptions say what the project holds, not what a post says.

| When | Item | What the project holds today | Link status |
|---|---|---|---|
| now | interp-engine | CPU eager backend used in push-to-run CI; one recorded float32 agreement audit for `gemma-2-2b` next-token behaviour (`docs/backend_agreement_20260903.md`); the fork's README says the engine powers Neuronpedia's inference (`patientwords-interp-engine/README.md:16`, fork head `2afe000d`) | `blog/interp-engine`: not read |
| now | ICA | offline adapter and toy fixtures (`ica_adapter.md`); four released bases named, none read; the Neuronpedia alias for `qwen3.5-2b-base` unverified | `blog/neurons-ica`: not read |
| now | existing lenses | hosted J-lens readouts for `gemma-2-2b` and `gemma-2-2b-it`, instrument revision not recorded; a released Qwen3-4B J++ artifact whose fit identity is unknown (capability matrix) | `blog/jpp-drift-ui`: not read |
| now | neuron / ICA comparisons | nothing run. The registry has no `neuron` entry. A comparison needs both representations on one verified checkpoint | `blog/neurons-ica`: not read |
| now | graph interchange | the reference payload and the plan above; no exporter | `graph/validator`, `blog/circuit-tracer`: not read |
| next | HeadVis | nothing. No `attention_head` entry | `blog/headvis`: not read |
| next | attention-aware graphs | the engine names one model traced with attention replacement and its two request parameters (`graph_client.py:62-64`); that model's hosted graphs are capped at 10 prompt tokens, which study prompts exceed (`neuronpedia_features.py:56-58`) | `blog/circuit-tracer`: not read |
| next | temporal analysis | nothing. To be opened only for a defined hypothesis about reference, negation or information retained over turns | none |
| optional study | NLAs | nothing | `blog/nlas`: not read |
| optional study | Assistant Axis, Drift Calibrator | nothing | `blog/assistant-axis`, `blog/jpp-drift-ui`: not read |

Conditions attached to the later rows.

- **Attention.** An attention pattern shows where a head reads from. It does not establish that
  the head causes an output. A claim about cause needs an intervention with a control, on a
  hypothesis stated before the run.
- **NLAs.** The post was not read, so this page does not define the method. Any method that
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
  that development paused in July. The brief has no retrievable record in the repository and the
  post was not read today, so this page does not confirm it.

## What was verified, and what was not

| Statement | Evidence |
|---|---|
| The registry rules, link rules, snapshot checks, record validators and graph-reference rules behave as written | `tests/test_experiments_neuronpedia.py`, offline, on a synthetic registry and the real registry file |
| Real entries agree with the engine's tables | the same tests compare study ids, Hugging Face ids and pins with `scripts/logits_eval.py`, source sets with `neuronpedia_features.MODEL_SOURCE_SETS`, the calibrated pair with `scripts/feature_models.py`, and artifact ids with the capability matrix |
| The module opens no socket | `test_importing_and_using_the_module_opens_no_socket` replaces `socket.socket`, `socket.create_connection` and `socket.getaddrinfo`, loads the module from its file, calls each of its sixteen public functions and asserts that the set it called equals the set the module defines; `test_module_imports_no_network_or_process_library` lists the imports |
| A request record holds no credential and no prompt text | checked by key name, value type, character class and the credential screen (issuer prefix; token form), on abstract placeholders and on dummy strings made of an issuer prefix and filler. Not verified: the cases listed under "What the check cannot see", which the check cannot tell from an id |
| A refusal of a request record repeats no value | a sentinel string is placed under each key, in `not_recorded`, in the endpoint and as a key, and the message is read (`test_no_refusal_of_a_request_record_repeats_a_value`, `test_a_not_recorded_entry_is_checked_as_a_pointer_and_never_repeated`, `test_a_string_with_a_credential_prefix_is_refused_wherever_it_sits`) |
| An integer in a URL is a component index or a layer number | bounded as described under *Resolving and linking*; `test_the_integers_of_a_url_are_bounded_so_a_hash_written_as_an_integer_is_refused` also builds no URL from any committed entry over layers 0 to 4095 and component ids up to 2**20 - 1 |
| Any Neuronpedia id resolves on the site | not verified. No page was read and no request was made |
| Any hosted checkpoint equals a study pin | not verified. No hosted revision is recorded anywhere |
| Any page URL pattern | not verified. None is recorded |
| The graph contract | not verified against Neuronpedia's schema or validator. The plan lists the engine's reading |
| That a fixture link works | not applicable. The fixture host is under `.invalid` |

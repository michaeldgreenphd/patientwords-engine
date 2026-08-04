# PatientAgentBench integration — as built (2026-08-04)

Companion to `docs/patientagentbench_integration_design.md`, which decides *whether*
to integrate. This one records *what exists*, so the next reader does not have to
re-derive it from two repositories.

**Status: exploratory.** Nothing is registered, nothing has been fired, nothing is
published. No CI trigger was touched. Everything below runs offline at $0, and the
running Tier B study is untouched.

## The three layers

| Layer | Where | Licence | Rule |
|---|---|---|---|
| 0 — upstream | `PatientAgentBench-patientwords/src/patient_agent_bench/`, its `tests/`, `pyproject.toml`, `data/` | CC-BY-NC-4.0 | **Never edited.** Not one file. |
| 1 — adapter | `PatientAgentBench-patientwords/src/patientwords_pab/`, `tests/test_pw_*.py` | CC-BY-NC-4.0 (imports upstream ⇒ derivative) | Lives only in the fork. |
| 2 — analysis | this repo | MIT | Reads the runner's JSON as data. Never imports their code. |

Layer 2 is the licence boundary and it is the reason the split exists. Layer 1
imports PatientAgentBench, so it is a derivative work and inherits NonCommercial
terms; keeping it in the fork stops those terms from reaching the interpretability
engine. Reading `conversations.json` and `evaluations.json` is not a derivative
work, so this repo stays MIT. Nothing here imports `patient_agent_bench`, and
nothing should.

## What Layer 1 adds

Upstream defines seven behavioural traits × three levels in `TRAIT_DEFINITIONS`,
then bundles them into six fixed presets, and `get_personality_prompt()` accepts
only a preset name. Every preset moves several traits at once, so a difference
between two presets cannot be attributed to any one trait — the identification
problem the design note diagnoses. The data structure is already factored the
right way; only the public API is preset-locked.

`src/patientwords_pab/` supplies the missing API:

- **`trait_spec.py`** — parses `pw:trait=level;...` arm labels and resolves them
  against upstream's own `TRAIT_DEFINITIONS`. Traits the spec does not name come
  from a **base**, which defaults to *all traits at `medium`* rather than a preset:
  a preset base would silently re-bundle the confounds the sweep exists to
  separate. `base=<preset>` is available for anchored ablations.
- **`free_trait_agent.py`** — `FreeTraitUserAgent(DefaultUserAgent)`, `NAME =
  "pw_free_trait"`, registered through upstream's documented
  `register_user_agent()` hook at import. A plain preset name passes through
  byte-identically to the default agent, so preset arms and free-trait arms can
  share one config.
- **`render_persona.py`** — the dry run. Prints the resolved traits, the persona
  block, a novelty report, and (for `--sweep`) a single-factor identification
  check. Builds no LLM client and makes no network call.
- **`run.py`** — CLI wrapper that registers the agent, then defers to upstream's
  `main()` unchanged.

The `personality` field carries the arm label from the benchmark JSON to the agent
as an opaque string, so no upstream plumbing had to change to move a trait spec
through the runner.

### The one workaround, and why

`DefaultUserAgent.__init__` calls `get_personality_prompt(personality)`
unconditionally while building the system prompt, and that raises `KeyError` for
anything that is not a preset key. Relaxing it would be an upstream edit, so the
subclass hands the base constructor a real preset name it can resolve and then
rebuilds `self.system_prompt` from the same template with the real trait block.
`tests/test_pw_free_trait_registry.py` asserts nothing from the placeholder
survives into the final prompt, and that a preset arm stays byte-identical to
what `agent_class="default"` would have produced.

## Upstream surfaces depended on

Pinned by `tests/test_pw_upstream_pins.py` in the fork. The second row is the one
that matters:

| Surface | Used for | If upstream moves it |
|---|---|---|
| `personalities.TRAIT_DEFINITIONS` | the trait text the block is assembled from | loud failure |
| `default_prompt.SYSTEM_PROMPT` containing `{personality_traits}` | the slot the block goes into | **silent** — `format_prompt_safe` only *logs* a warning for a keyword with no matching placeholder, so a rename would run every arm persona-free, with no error, and the sweep would measure nothing while looking healthy |
| `registry.register_user_agent(name, cls)` | registering without editing `registry.py` | loud failure |
| `DefaultUserAgent.__init__` keywords, `self.system_prompt_template` | the subclass forwards, then re-renders | loud failure |
| `get_personality_prompt()` raising `KeyError` on a non-preset | the reason for the placeholder | placeholder becomes unnecessary, stays harmless |
| `PERSONALITY_TYPES` | preset bases and the novelty comparison | loud failure |

## Layer 2 in this repo

| File | What it is |
|---|---|
| `scripts/validate_pab_contract.py` | structural + design-integrity gate over a run directory |
| `data/pab_transcript_contract.json` | everything the gate requires, declared as data |
| `tests/fixtures/pab_run/` | a committed clean two-case, three-arm run |
| `tests/test_validate_pab_contract.py` | 43 tests, each seeding one contract break |
| `scripts/pab_probe_cost.py` | $0 offline cost model for a probe |
| `tests/test_pab_probe_cost.py` | pins the figures the costing document quotes |

```bash
python scripts/validate_pab_contract.py --run <run-dir> [--strict] [--json]
```

The shape checks are the same job `validate_frontend_contract.py` does for the
site payload: required keys and types, the slot-for-slot join between
`conversations.json` and `evaluations.json`, rubric scores inside the declared
1–5 scale, no duplicate `case_id`.

The **design-integrity** checks are the reason it exists:

- **Single-factor identification.** Arm labels are decomposed and compared; more
  than one trait varying across arms is an error, as is zero (two labels that
  differ as strings but resolve to the same traits — a config that looks like a
  sweep and measures nothing). Arms using different bases are rejected, because
  traits they do not name are then not held fixed.
- **Balanced pairing.** Every clinical case must appear in every arm. Arms are
  separate benchmark entries with separate ids, so the join runs on a hash of the
  case content the sweep holds fixed — hashed, so no case text can reach a report.
- **Stimulus-level confounds.** When `benchmark_cases.json` is present, paired
  entries must agree on every attribute except the personality.

An unbalanced or multi-factor run reads as a finding just as easily as a clean
one, and nothing downstream would notice. That is the whole argument for putting
these checks in front of the analysis rather than in a reviewer's head.

The arm-label grammar is **duplicated** in `data/pab_transcript_contract.json`
rather than imported from the fork. That is the licence boundary doing its job;
the cost is that the two must be kept in step by hand, and the pinned string forms
in `tests/test_validate_pab_contract.py` are what catches drift.

## Verification

- Fork: `python -m pytest` → **1074 passed** (982 before, 92 added).
- Engine: `python -m pytest` → **643 passed** (583 before, 60 added); `ruff check .`
  clean; `python scripts/seal_check.py --site ../patientwords` CLEAN.
- **Upstream merge, simulated offline.** A synthetic upstream release editing
  `personalities.py` (including reordering `PERSONALITY_TYPE_NAMES`, which changes
  which preset the placeholder resolves to), `registry.py`, `default_prompt.py`,
  and `pyproject.toml`, plus a new upstream module, was merged into the Layer 1
  branch: **zero conflicts**, and all 91 adapter tests pass against the merged
  tree. The real `git pull upstream main` could not be run — this session is
  offline and `amazon-science/PatientAgentBench` is not among the session's
  repositories — so this is the strongest available proof.
- `tests/test_pw_layer0_boundary.py` in the fork asserts that no file present in
  the upstream baseline differs in the working tree, so hard rule 1 is enforced
  rather than trusted. Verified against a seeded violation.

## What the dry run already answered

The design note's open question 1 — *"Setting `health_literacy: low` in isolation
may produce an incoherent persona the simulator partly ignores"* — splits into two
parts, and the cheap part is now settled offline.

The block is **structurally** sound: it is byte-identical in form to what a preset
produces (same elements, levels, description text, ordering, indentation), so
there is no malformed-prompt failure mode to worry about. The `type` attribute is
held to a fixed literal across all arms, because it is the only free text in the
block and letting it carry the spec would put an uncontrolled label in the prompt
beside the trait being swept.

The **semantic** part is sharper than expected, and it changed the recommended
design. `render_persona.py` reports which trait-level pairs no upstream preset
ever attests:

| arm | unattested pairs | of which introduced by the spec | nearest preset |
|---|---|---|---|
| `pw:health_literacy=low` (neutral base) | 12 | 4 | `confused`, 4 traits away |
| `pw:health_literacy=high` (neutral base) | 10 | 2 | `skeptical`, 3 traits away |
| `pw:base=confused` | 0 | 0 | `confused`, 0 traits away |
| `pw:base=confused;health_literacy=high` | 2 | 2 | `confused`, 1 trait away |

The all-`medium` neutral base is **itself off-manifold**: no preset carries
`cooperation: medium` alongside `anxiety: medium`, so a neutral-base sweep compares
three personas upstream never validated, against a baseline it never validated
either. Clean identification, unvalidated ground. A preset base gives the opposite
trade: each arm sits one trait from a validated persona, and one arm *is* that
persona — at the cost of estimating the effect conditional on that persona rather
than at a neutral point.

For a first probe the preset base wins, and `confused` is the right anchor: it is
the only preset carrying `health_literacy: low`, and it carries `clarity: low` and
`urgency: low` with it — precisely the bundle that makes the paper's own result
(`confused` 3.15 > `skeptical` 2.52 on triage) unattributable. Sweeping literacy
from that base holds the other six traits at the levels upstream validated and
moves the one trait in question. See `docs/pab_first_probe_costing.md`.

Whether the simulator *obeys* the instruction is not answerable offline. That is
the first live stage, and it costs under a dollar.

Design-note open question 3 — *"Can the patient agent run on a non-Bedrock,
non-Claude model without harness changes?"* — is answered **yes, by config alone**.
Non-Claude on Bedrock needs only a registry key (their `MODEL_STORE` carries Qwen,
Llama, DeepSeek and GPT-OSS entries). Off Bedrock, a custom spec with
`"provider": "openai-protocol-api"` or `"anthropic-protocol-api"`, `"auth":
"api_key"`, and `base_url_env`/`api_key_env` routes to any compatible endpoint.
No harness change either way.

## Known limitations

1. **Editable install required.** `src/patientwords_pab/` is importable because the
   editable install puts `src/` on `sys.path`. A non-editable `pip install .` builds
   only `patient_agent_bench`, since the wheel's package list lives in upstream's
   `pyproject.toml` (Layer 0). Editable is upstream's own supported install path.
2. **The arm-label grammar is duplicated** across the licence boundary, by design.
3. **The evaluator stack is LLM on LLM on LLM.** Their patient is an LLM, their jury
   is an LLM, and so are ours. Their clinician validation is stronger than anything
   this study has, but the combined stack has to be disclosed plainly rather than
   treated as ground truth.
4. **Rubric subsetting is not available** without a fork-side hook. All six rubrics
   run on every conversation, which is most of the cost.

# Owner decisions — 2026-08-19

Follow-on to `docs/decisions_20260816_owner.md`, acting on the 2026-08-18
system audit (artifact "PatientWords Audit").

## Approved and implemented this session

- **S1 — workflow injection surface.** `model_evaluation.yml`'s "Run
  evaluation" step interpolated `${{ steps.params.outputs.* }}` directly into
  its `run:` body; params now reach the shell as env vars only, matching the
  pattern the other seven workflows already use. Word-splitting of the model
  list is preserved explicitly (`read -r -a`).
- **S2 — server-side daily ceiling.** New `fire_trigger.py budget-gate`
  subcommand runs the SAME `budget_check` as the client-side fire path
  (dashboard + journal in-flight + overrides, channel-aware) inside CI; exit 6
  refuses the run. Wired into the three paid workflows
  (scenario-generation, model-evaluation, advice-eval) between the params
  step and the paid step, with params passed via `toJSON(steps.params.outputs)`
  through env — covers both push-fired and dispatch-fired runs. Five
  regression tests added. The circuit-trace mitigation path is a noted
  follow-up (its paid fires carry no max_spend param; the imputed-commitment
  logic is already in the gate, wiring it into that workflow is pending).
- **S3 — journal integrity.** (a) 140 expired-unresolved journal entries
  annotated in place with factual context (never marked resolved — they stand
  as missed-harvest records; the two 2026-08-17 backfill legs and the 08-17
  drift sentinel carry their GitHub-confirmed run ids). (b) The daily
  Routine's standing prompt now instructs the cycle to WAIT (5-min polls, 35-min
  bound) for its own drift sentinel, verify + resolve it before writing the
  dashboard, with an opening-harvest backstop for a prior day's stray sentinel.
  Effective at the next 13:00Z firing — the Routine re-reads the file from the
  branch each cycle.
- **S4 (workflow half) — supply chain.** All `uses:` pins moved from major
  tags to commit SHAs (checkout, setup-python, upload/download-artifact),
  version noted in a trailing comment. The repo-settings half (secret-scanning
  push protection) is the owner's — click-path given in chat.

## Explained to the owner, awaiting their action

- S4 settings half: enable secret scanning + push protection on both repos.
- S5: (a) raw provider payloads in the published advice JSONL — owner's call,
  trade-offs laid out (append-only sha chain vs. redistribution);
  (b) meta-CSP hardening on site pages — offered, not yet commissioned;
  (c) Routine recreation with the GitHub connector — unchanged, pending.

## Commissioned

- Exploration of the clinician-facing and frontier-lab-facing presentation
  edits (audit part 3), Tufte-style figures, prototypes on real data for
  owner review before anything lands on the public site.

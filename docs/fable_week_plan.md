# Fable week plan — owner-approved 2026-07-09 (FABLE PLAN paste)

Owner decisions: A1 nightly · A2 approve · A3 approve · A4 keep ops light ·
B1–B4 all approved (B4 both) · C1 Llama-3.2-3B add · C2 Phi skip ·
C3 OLMo-2 add · C4 medical-tuned 7B add.
Owner note: Fable runs through **Tuesday 2026-07-14**, then heavy batches
downshift (agents pinned to Opus 4.8 via per-agent model override) unless
Fable access increases. Ops Routine stays on the light path throughout (A4).

## A · Autonomous streams (this session)

- **A1 Nightly research-critic (Fable), ~05:00 UTC daily:** read everything
  landed that day (Tier B batches, traces, stats), re-run
  `paired_stats_rigor.py`, evaluate like a hostile reviewer, design/queue the
  next experiments, write suggestions into `ops/dashboard.json`
  (`verdicts`/`findings_delta`/`decisions_pending`) + a dated report in
  `docs/critic/` so the 13:00 UTC digest carries them. Re-chains itself +24h.
- **A2 Verify-before-commit:** every autonomous batch ends with adversarial
  reviewer agents over the diff before I commit. (Standing policy.)
- **A3 Weekly synthesis deep-refresh:** Monday — full DRAFT rewrite of
  `docs/findings_synthesis.md` against all accumulated data, delivered as
  `docs/findings_synthesis_DRAFT_<date>.md` for the owner's voice. Never
  auto-published over the released doc.
- **A4:** daily ops Routine stays on the default light model.

## B · Interpretability experiments (all $0 compute)

- **B1 Activation patching in CI:** wire the hooking dependency
  (transformer-lens) into a CPU workflow; run the (layer × position)
  recovery grid on the downgrade set; extend batch_summary with the
  documented recovery-map schema (`docs/activation_patching_design.md`).
- **B2 gemma-2-9b universality:** probe Neuronpedia tracer support; CPU
  logits regardless. Gemma Scope exists at 9B.
- **B3 gemma-2-2b-it contrast:** same base ± instruction tuning; one logits
  run on the unified set.
- **B4 both:** cross-pair feature transfer + steering-vector vs SAE-feature
  comparison; designs then hosted-API execution ($0), small-n pre-registered.

## C · Behavioral matrix additions ($0 CPU logits)

| add | HF id | gate? |
|---|---|---|
| Llama-3.2-3B | `meta-llama/Llama-3.2-3B` | Meta license form (free) |
| OLMo-2-1B | `allenai/OLMo-2-0425-1B` | none |
| BioMistral-7B (medical-tuned) | `BioMistral/BioMistral-7B` | none (Apache-2.0) |
| gemma-2-2b-it (B3) | `google/gemma-2-2b-it` | Gemma license (likely already accepted) |
| gemma-2-9b (B2) | `google/gemma-2-9b` | Gemma license (likely already accepted) |

Rollout: probe each model with a tiny logits run first; only models that
401 as gated get surfaced to the owner as a decision item with exact
click-path instructions. **Hugging Face cost truth:** license acceptance and
weight downloads are free; no card exists on the account to charge; HF bills
only optional subscriptions/hosted endpoints, which this pipeline never uses;
CI compute is GitHub's free public-repo runners. Charge risk: none.

## Schedule anchors

- Tonight 01:00 UTC: Tier B go/no-go (unchanged).
- Friday 08:00 UTC: pre-flight handoff (unchanged).
- Daily 05:00 UTC: A1 critic · 13:00 UTC: ops digest.
- Monday: A3 synthesis draft.
- **Tuesday 2026-07-14 end-of-day: downshift** — batch agents pinned to
  Opus 4.8 (per-agent override; the session model itself is owner-controlled).

## H · Headroom streams (owner-approved 2026-07-09 evening; H6 pending)

Execution order (nightly critic works through this queue; verify-before-
commit applies to all):
1. **H1 claim-integrity CI** — engine workflow that recomputes every
   published number from committed artifacts on push and fails on drift;
   includes a deployed-site health job (fetch the live Pages URL + data
   files from the CI runner, assert 200 + parseable + spot values).
2. **H3 circuit-drift monitor** — extend the critic cycle: compare each new
   Tier B trace's named-feature composition/overlap vs the established set
   (docs/analyses_20260708.json baseline); digest flags composition shifts.
3. **H2 logit-lens depth profiles** — rides the patching CI dependency;
   layer-by-layer target trajectory clinical vs patient on the downgrade
   set; produces the companion figure to the patching heatmap.
4. **H4 feature atlas** — data-driven catalog page (label, category,
   frequency, mean layer, Neuronpedia link) from the analyses bundle;
   no owner prose needed.
5. **H5 reproducibility kit** — one-command rebuild script, dataset card,
   schema docs, CITATION.cff, fresh collaborator exports.
6. H6 preprint skeleton — HELD pending owner.

## W · Gaps closed 2026-07-09 evening

- W1 watchdog: the fresh-session Routine now verifies the orchestrator's
  artifacts are fresh and flags a stalled wake chain in the digest.
- W2 deployed-site health: folded into H1 (CI runners have open egress;
  the sandbox proxy may block github.io locally).
- W3 prereg Amendment 1: 10% confirmatory holdout by deterministic hash +
  seed provenance, committed BEFORE Tier B batch 1 (start_utc null at
  amendment commit).
- W4 STOP protocol: digest footer tells the owner one word here freezes
  all automation (this session deletes every trigger on "STOP").

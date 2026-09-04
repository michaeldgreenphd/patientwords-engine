# Audit 1: Schema and Automation Contract

Date: 2026-07-16. Auditor: read-only audit session on branch `claude/patient-words-audit-hd792y`.
Audited refs: `patientwords` @ `244c698` (07-16 republish), `patientwords-engine` @ `3447b50`
(07-16 cycle), both on `claude/gemma-clinical-colloquial-interp-mavx04`, mounted as detached
worktrees. No file in either audited tree was modified; nothing under `.github/trigger/` was
touched; holdout rows were neither analyzed nor reproduced.

## Method

Thirteen finder passes (six data contracts, five workflow groups, one global bloat sweep, one
completeness critic) built exact read maps from page JS and compared them against writer emit
sets and the live payload instances. Every candidate finding then went to an independent
adversarial verifier instructed to refute it. 123 agent runs total. Result: 110 candidate
findings, 107 confirmed, 3 refuted, 0 undecidable; 98 unique findings after merging
cross-finder duplicates. Severity: 11 high, 37 medium, 50 low.

Established priors from the main session were honored: the nine branch writers, the exporter's
holdout gate, and the by-design no-fetch status of `drift_series.json` were not re-derived or
re-filed. The previously accepted findings (the `export_archive.py` rename gap, the orphaned
`patch_profile.json`) appear below only where branch evidence deepened them.

## Companion deliverable

`scripts/validate_frontend_contract.py` plus `tests/test_validate_frontend_contract.py`
(commit `f245a4e`, this branch) encode the structural layer of the contract: required keys and
types per page read-set, scenario index contiguity, join-key uniqueness, the COMPAT mirror
equality rule, the FEATURED clinical-mass rule, `models_meta` consistency, render-path
existence, key-example join integrity, claims-manifest references, and manual-copy drift.
It complements `claim_check.py` (prose values). Against the audited data it reports 0 errors
and 2 warnings, both filed below (F-M27, F-L44). Full test suite: 209 passed. The raw read
maps back the field lists in `docs/audit1_read_maps.json`.

## Findings

Each finding: location on the working branch, category, evidence, proposed fix as a diff.
Fixes are proposals only; nothing was applied. IDs are stable for cross-referencing.

### High: wrong numbers, silent data loss, unrecorded spend

#### F-H01 · `engine:.github/workflows/archive_renders.yml:154` · silent-failure

prune=true combined with no_pngs=true git-rm's the runs' index_*.png from the branch even though the bundle excluded PNGs; the PNGs end up neither on the branch tip nor in the Release, while the prune input text promises 'full-res PNGs live in the Release' (recoverable only by git-history archaeology; manifest quietly says includes_pngs:false).

Evidence:
```
Step env (lines 129-133) carries TAG/RUNS/PRUNE/BRANCH but not NO_PNGS; lines 154-161 run `for run in $RUNS; do git rm -q --ignore-unmatch "$run"/index_*.png || true; done` whenever PRUNE=1. archive_run.py drops PNGs from the zip when --no-pngs (lines 50-52: `if not include_pngs and _matches(path.name, PNG_GLOBS): continue`). Input description line 38: '(HTML stays; full-res PNGs live in the Release)'. The `|| true` also swallows any real git rm failure.
```
Proposed fix:
```diff
--- a/.github/workflows/archive_renders.yml
+++ b/.github/workflows/archive_renders.yml
@@ -129,6 +129,7 @@
         env:
           TAG: ${{ steps.params.outputs.tag }}
           RUNS: ${{ steps.params.outputs.runs }}
           PRUNE: ${{ steps.params.outputs.prune }}
+          NO_PNGS: ${{ steps.params.outputs.no_pngs }}
           BRANCH: ${{ github.ref_name }}
@@ -153,6 +154,10 @@
+          if [ "$PRUNE" = "1" ] && [ "$NO_PNGS" = "1" ]; then
+            echo "::error::prune requested but the bundle excluded PNGs; refusing to delete PNGs that are not in the Release"
+            exit 1
+          fi
           if [ "$PRUNE" = "1" ]; then
```
Verifier correction: Two corrections. (1) Severity: high overstates it slightly; prune does not rewrite history (docs/archiving.md explicitly notes existing blobs remain in the pack), so PNGs stay recoverable from git history, and the committed manifest honestly records includes_pngs:false; this is a silent contract violation and availability loss on the branch tip, not permanent data destruction. Medium-high is more accurate. (2) The proposed fix is placed in the "Record manifest + optional prune" step, which runs AFTER the Release upload; exiting 1 there leaves the Release asset uploaded but render_archives/<tag>.manifest.json staged and never committed, breaking the workflow's own invariant that every archived bundle gets an indexed manifest. Move the validation into the "Resolve parameters" heredoc (lines 71-98), e.g. `if no_pngs and prune: raise SystemExit("prune=true with no_pngs=true would delete PNGs that are not in the Release; refuse")`; this fails before any bundle/upload work and covers both the push path and workflow_dispatch. An acceptable alternative is to keep the prune step but skip the PNG deletion with a ::warning:: when the bundle excluded PNGs. Either way, also drop the `|| true` on the git rm (--ignore-unmatch already handles missing files; || true only hides real failures). No other consumer is affected by the guard.
Found by: wf-archive-ops. Verified: CONFIRMED.

#### F-H02 · `engine:.github/workflows/model_evaluation.yml:102` · silent-failure

Paid model-evaluation runs write no cost sidecar anywhere ledger_update.py scans, so their Anthropic spend never reaches ops/dashboard.json; verified: two paid fires on 2026-07-12 (max_spend 0.5 each) and spend.entries_seen contains zero eval entries; by_day[2026-07-12]=0.2603 is generation only.

Evidence:
```
The 'Run evaluation' step (line 102) calls evaluate_models, which writes eval_out/results.json with usage.total_cost_usd (evaluate_models.py:455) — committed nowhere; the export step commits only data/evaluations/model_evaluations_frontend.json (line 156). ledger_update.py scans only `data/simulated/*.report.json` (line 90, default --simulated-dir). Once the journal entry is resolved, this spend leaves budget_check's committed = landed + in-flight calculation entirely, so the $2/day ceiling can be silently breached. CLAUDE.md line 69 claims 'every paid run writes a .report.json ... sidecar with its cost'.
```
Proposed fix:
```diff
In the 'Export frontend table + commit' step, also emit a sidecar and commit it to main alongside the frontend export, e.g.:
+          python - <<'EOF'
+          import json, datetime
+          r = json.load(open("eval_out/results.json"))
+          stamp = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
+          side = {"run_timestamp": datetime.datetime.utcnow().isoformat()+"Z",
+                  "task": "model-evaluation", "model": "${{ steps.params.outputs.model_selection }}",
+                  "cost_usd": (r.get("usage") or {}).get("total_cost_usd", 0.0),
+                  "max_spend_usd": float("${{ steps.params.outputs.max_spend }}")}
+          open(f"data/simulated/modeleval_{stamp}.report.json", "w").write(json.dumps(side, indent=2)+"\n")
+          EOF
+          git add data/simulated/modeleval_*.report.json
(and push to main the way scenario_generation.yml's archive step does, lines 290-312).
```
Verifier correction: Corrected statement: Paid model-evaluation runs write their cost only to eval_out/results.json (usage.total_cost_usd, evaluate_models.py:455), which is uploaded as a CI artifact and never committed; the only committed trace of spend is the per-model rounded cost_usd inside data/evaluations/model_evaluations_frontend.json (e.g. 0.0045 for the landed 2026-07-12 run), which is overwritten each run, lands on the dispatched branch, and is read by no ledger consumer. ledger_update.py scans only data/simulated/*.report.json, so eval spend never reaches ops/dashboard.json: entries_seen has zero eval sidecars and by_day[2026-07-12]=0.2603 despite two resolved model-evaluation fires that day (max_spend 0.5 each, trigger_journal.jsonl lines 51/54). Once a journal entry resolves, budget_check's committed = landed + in-flight undercounts by the run's ACTUAL spend (not its max_spend), so the $2/day ceiling can be silently understated for same-day follow-on fires. A run that crashes before writing results.json (the first 2026-07-12 fire, per its journal note) leaves its spend recorded nowhere at all. This contradicts CLAUDE.md:69; model-evaluation is the only paid path without a sidecar (mitigation fires do write .mitigation.report.json). Severity is better read as medium-high: mechanism real and structural, but observed dashboard leakage to date is cents. Corrected fix: emit a data/simulated/modeleval_<stamp>.report.json sidecar (task "model-evaluation" so Tier B attribution, gated on task=="pairs", stays clean) but (a) commit it to MAIN using the origin/main worktree + rebase-retry pattern of scenario_generation.yml's "Commit to the simulated-data archive" step (lines ~287-315), NOT the existing export-step commit which pushes to $BRANCH; ledger_update/the Routine scan main; (b) take run_timestamp from results["run_timestamp"] so ledger day-bucketing matches the run, rather than a fresh utcnow; (c) pass max_spend/model via env vars instead of ${{ }} interpolation inside the heredoc (repo convention, injection hygiene); (d) to also capture crashed-run spend, write the sidecar from a step that runs if: always() and falls back to max_spend-as-upper-bound or a "spend unknown" marker when results.json is absent; (e) accept or filter the side effect that study_timeline.py:39 globs data/simulated/*.report.json, so the new sidecar will appear in the public data/timeline.json as kind "modeleval" (harmless but must be deliberate; ledger_bullet renders accepted as an em-dash, and batch_file_name's phantom modeleval_*.json only matters inside tierb rows, which never trigger for this task).
Found by: wf-archive-ops. Verified: CONFIRMED.

#### F-H03 · `engine:.github/workflows/model_evaluation.yml:116` · silent-failure

model_evaluation runs never write a .report.json sidecar under data/simulated/, so their real Anthropic spend never lands in the ledger/dashboard accounting chain at all.

Evidence:
```
The workflow's only durable outputs are the eval_out/ artifact (90-day retention) and 'data/evaluations/model_evaluations_frontend.json' committed to the dispatched branch (lines 149-157) — nothing under data/simulated/. scripts/ledger_update.py:90 scans only `sim_dir.glob("*.report.json")` with --simulated-dir default 'data/simulated' (line 41-42), and dashboard spend.today is the 'landed' term in fire_trigger.py budget_check (lines 343-354). ops/README.md:70-72: '`resolve` releases the in-flight hold once the run's real cost lands via the sidecar scan.' — for model-evaluation there is no sidecar, so resolve releases the hold and the day's committed spend permanently loses the eval cost. Confirmed empirically: enumerating every data/simulated/*.report.json 'task' value yields only pairs/dialects/quadrants/txcorpus/alias/mitigation_translation — no model_evaluation entry despite landed runs (site copy updated 2026-07-12). Also doc-drift: engine CLAUDE.md promises 'every paid run writes a `.report.json` sidecar with its cost.'
```
Proposed fix:
```
Add a step after 'Run evaluation' (if: always(), guarded on eval_out/results.json existing) that writes data/simulated/modeleval_<STAMP>.report.json from results.json:
  side = {"task": "model_evaluation", "model": ",".join(r["models"]), "run_timestamp": r["run_timestamp"], "accepted": None, "cost_usd": (r.get("usage") or {}).get("total_cost_usd", 0.0), "max_spend_usd": r["max_spend_usd"], "usage": r.get("usage")}
and commit it to MAIN using the same worktree + rebase-retry block as scenario_generation.yml lines 292-312 (a branch-committed sidecar is invisible to the ledger scan on main).
```
Verifier correction: Location nit: the missing-sidecar gap sits after the 'Run evaluation' step (line 102-114); the commit block cited as 149-157 is actually lines 154-161. Fix limitation to state explicitly: results.json is written only at the END of run_evaluation, so a run that crashes after spending (exactly the first 2026-07-12 fire, journal note 'first run failed, $ spent') produces no results.json and would STILL escape the sidecar even with the proposed step; loss is bounded by max_spend (CostTracker aborts at the ceiling), but full coverage requires either checkpointing usage during the run or having the sidecar step fall back to booking max_spend_usd as a conservative estimate when eval_out/results.json is absent (with a note field marking it estimated). The fix should also land the sidecar on MAIN (as proposed; a branch-committed sidecar is invisible to the ledger scan) and should be accompanied by no doc change (CLAUDE.md's sidecar promise becomes true again); alternatively, if the fix is declined, engine CLAUDE.md and ops/README.md must be corrected to say model-evaluation spend is tracked only via the artifact and step summary. Severity high is defensible: dollar amounts are small (max_spend 0.5-5/run) but the $2/day ceiling enforcement and the single-writer spend invariant both silently depend on the sidecar scan being complete.
Found by: wf-paid. Verified: CONFIRMED.

#### F-H04 · `engine:.github/workflows/model_evaluation.yml:129` · silent-failure

The frontend export heredoc rebuilds model_evaluations_frontend.json from only the current run's by_model and overwrites the file wholesale, so any single-model run (the default is model_selection=claude-haiku-4-5) silently discards previously landed models' rows; the engine artifact has already diverged from the site copy methods.html renders.

Evidence:
```
Workflow: `models = []` then `for model, blocks in (results.get("by_model") or {}).items(): ... models.append({...})` and `pathlib.Path("data/evaluations/model_evaluations_frontend.json").write_text(json.dumps(payload...))` — no merge with the existing file. Verified divergence on this branch: engine data/evaluations/model_evaluations_frontend.json has n_models=1 ({id: claude-haiku-4-5, items: 10, patient_accuracy: 0.3, clinician_accuracy: 0.3, cost_usd: 0.0045}) while site data/model_evaluations.json has n_models=3 (claude-opus-4-8 1.0/0.8, claude-sonnet-5 1.0/0.9, claude-haiku-4-5 1.0/1.0) — both stamped updated=2026-07-12, so a later single-model run clobbered the 3-model 'all' export. The next engine->site copy will drop the opus and sonnet rows from methods.html #generation-eval and flip haiku's displayed accuracies from 1.0/1.0 to 0.3/0.3 with no error anywhere.
```
Proposed fix:
```diff
In the export heredoc, merge instead of overwrite (import pathlib before use):
-          models = []
-          for model, blocks in (results.get("by_model") or {}).items():
+          import pathlib
+          out_path = pathlib.Path("data/evaluations/model_evaluations_frontend.json")
+          merged = {m["id"]: m for m in (json.loads(out_path.read_text(encoding="utf-8")).get("models", []) if out_path.exists() else [])}
+          for model, blocks in (results.get("by_model") or {}).items():
               ts = blocks.get("two_step") or {}
               flags = ts.get("flags") or {}
-              models.append({
+              merged[model] = {
                   "id": model, ...
-              })
+              }
+          models = list(merged.values())
and drop the now-duplicate `import pathlib` below.
```
Verifier correction: Two refinements. (1) Impact framing: there is no automated engine-to-site copy for this file (no script or doc in the engine references model_evaluations_frontend.json besides the workflow itself), so the clobber reaches methods.html only at the next manual sync; the defect is real and already latent in the engine artifact, but the site is not yet wrong; severity high is defensible as silent data loss, medium-high if judged by current user-visible impact. (2) Fix hardening: the merge-by-id patch is directionally correct but (a) because the engine artifact has already lost the opus/sonnet rows, the first merged run cannot recover them; either re-seed the engine file from the site's 3-model copy or land one model_selection=all run before relying on the merge; (b) stamping top-level updated=date.today() onto merged stale rows misattributes freshness; add a per-model updated field (set only for models present in the current run) or keep the newest date per row; (c) note the merge never removes a retired model id, so retirement becomes a manual edit; acceptable, but worth a comment in the heredoc.
Found by: methods-sentinel-bundle. Verified: CONFIRMED.

#### F-H05 · `engine:.github/workflows/scenario_generation.yml:287` · silent-failure

A paid generation run that accepts 0 items skips the archive step entirely, so its cost sidecar never reaches main and the spend is never recorded; with the job fully green.

Evidence:
```
Line 287: `if: ${{ steps.gen.outputs.count != '0' }}` gates the ONLY step that commits both `${{ steps.gen.outputs.out }}` and `${{ steps.gen.outputs.report }}` to main (line 297). With 0 accepted items medlang-generate still exits 0 after paid rounds (write_generation_report always runs, scenario_gen.py:1129), COUNT=0, the archive and trace steps skip, and the job succeeds. The sidecar survives only in the run artifact (if-no-files-found: warn). ledger_update.py scans only data/simulated/*.report.json on the checkout, so this spend never enters spend.by_day / spend.today. This failure mode is real, not hypothetical: scenario_gen.py:50-52 records a prior incident — 'a 1600-token cap truncated every round of a 6-candidate run to unparseable JSON (0 accepted from 6 rounds)' — i.e. a full paid run with count=0.
```
Proposed fix:
```diff
--- a/.github/workflows/scenario_generation.yml
@@
-      - name: Commit to the simulated-data archive
-        if: ${{ steps.gen.outputs.count != '0' }}
+      - name: Commit to the simulated-data archive
@@
-          cp "${{ steps.gen.outputs.out }}" "${{ steps.gen.outputs.report }}" ../main-archive/data/simulated/
+          cp "${{ steps.gen.outputs.report }}" ../main-archive/data/simulated/
+          if [ "${{ steps.gen.outputs.count }}" != "0" ]; then
+            cp "${{ steps.gen.outputs.out }}" ../main-archive/data/simulated/
+          fi
(the sidecar is uniquely stamped, so the commit always has content; downstream collectors already skip batches with no matching .json).
```
Verifier correction: Finding stands as written, with three refinements. (a) Scope: line 316 gates the trace step on the same count check, and study_timeline.py:39 also reads sidecars from the checkout; so a count=0 paid run is lost from BOTH the spend ledger/dashboard and the public study timeline, not just spend accounting. (b) Mitigation nuance for severity calibration: while the fire's journal entry stays ACTIVE (until resolved or expire_hours), fire_trigger.py's in-flight accounting still counts its max_spend against the daily ceiling, so same-day double-spend is partially protected during that window; the loss becomes permanent and silent only after resolution/expiry, and per-run exposure is bounded by max_spend (default $2). High severity remains fair because the repo treats spend accounting as a hard invariant ("ledger_update.py is the only writer of spend numbers") and the count=0 mode has already occurred in practice. (c) Fix side effect worth a comment in the patch: with the sidecar landing on count=0, ledger_update.attribute_tierb will upsert a tierb.batches row {accepted: 0, status: "landed"} whose "file" points at a batch archive that was never committed. No script loads tierb.batches[].file from disk (tierb_split.py reads only tierb.start_utc), so this is accounting-only and arguably correct, but the "landed" status string is slightly misleading for a batch with no archive; consider "landed_empty" or leaving status untouched when accepted == 0. Also note line 300's commit message interpolates basename of the uncopied batch file on the count=0 path; harmless but worth adjusting to reference the sidecar.
Found by: wf-paid,wf-archive-ops. Verified: CONFIRMED.

#### F-H06 · `engine:medlang_circuits/batch_eval.py:1024` · silent-failure

A mid-batch failure commits a truncated batch_summary.part_NN.json that is byte-level indistinguishable from a complete smaller chunk: the summary schema has no requested-pair count or completion flag, so downstream merges silently lose the untraced pairs.

Evidence:
```
batch_eval.py:1024-1033 builds summary = {"mode", "backend", "graph_model", "source_set", "generation_params", "start_index": start_index, "screen_targets": screen_targets, "results": results} — no len(pairs), no completed marker; the per-pair checkpoint loop (1034-1063) rewrites it after each pair and a raised exception (graph_client.py:205 'if status not in RETRYABLE_HOSTED_STATUS: raise'; :209 RuntimeError after HOSTED_ATTEMPTS) leaves it truncated with no per-pair error record. circuit_trace_evaluation.yml:286 'if: ${{ always() && ...commit_outputs == 'true' }}' then runs and :297-298 'mv "$OUT_DIR/batch_summary.json" "$OUT_DIR/batch_summary.part_$(printf '%02d' "$START").json"' commits it unmarked (a re-fire of the same offset also silently mv-overwrites an existing part with a possibly shorter one). Consumers key purely on index with no expected-count check: export_frontend_simulated.py:137-138 'for r in summary.get("results", []): results[r["index"]] = r'; urgency_shift.py:172 'for r in summary.get("results", [])'. Grep for pairs_requested|completed|truncat across scripts/ finds no reconciliation anywhere (fire_trigger.py journals fires but never landed counts; daily_brief.py has no trace_out logic). The only truncation signal is the transient red/cancelled leg conclusion.
```
Proposed fix:
```diff
--- a/medlang_circuits/batch_eval.py
+++ b/medlang_circuits/batch_eval.py
@@ (run_batch summary construction, ~line 1024)
     summary = {
         "mode": mode,
         "backend": backend,
         "graph_model": graph_model,
         "source_set": source_set or getattr(fetcher, "source_set", None),
         "generation_params": generation_params or {},
         "start_index": start_index,
+        "pairs_requested": len(pairs),
+        "completed": False,
         "screen_targets": screen_targets,
         "results": results,
     }
@@ (after the for-loop, ~line 1063)
+    summary["completed"] = True
+    with open(summary_path, "w", encoding="utf-8") as f:
+        json.dump(summary, f, indent=2)
     logger.info("Batch complete: %d pairs (mode=%s), summary at %s", len(results), mode, summary_path)
Consumers ignore unknown keys, so this is backward-compatible; collectors can then warn on completed==False or len(results) < pairs_requested.
```
Verifier correction: Finding stands as written, with three refinements. (1) Known-known caveat: the truncation itself is deliberate checkpointing, documented in the engine CLAUDE.md ("a mid-batch failure just truncates results") and regression-tested (tests/test_targets_and_batch.py:161-188); the actual defect is precisely the downstream part; the truncated checkpoint is committed unmarked and no consumer or ops tool reconciles counts. (2) The proposed fix's final post-loop rewrite is load-bearing: without it the last in-loop checkpoint still says completed:false after a successful run. (3) The fix should also add pairs_requested/completed to scripts/logits_eval.py build_summary (lines 131-143), which emits the same part schema; the logits path writes its part only once after the loop (line 196) so it cannot land truncated, but collectors that warn on completed==false must treat a missing key as legacy/unknown, since all already-landed parts (and logits parts, if left unchanged) lack the keys; otherwise historical parts would false-positive as incomplete.
Found by: wf-circuit-trace. Verified: CONFIRMED.

#### F-H07 · `engine:medlang_circuits/scenario_gen.py:1129` · silent-failure

The generation cost sidecar is written only on clean completion; an unhandled API exception mid-run or a CI timeout discards all record of the rounds already paid for.

Evidence:
```
main() writes the batch (line 1078 `_write_json(out, result["pairs"])`) and the sidecar (line 1129 `write_generation_report(...)`) only after the generation function returns. Unlike evaluate_models.py (which wraps every `_call` in try/except, lines 218-223 and 310-313), generate_stress_pairs calls `_call` bare at lines 475-477 (`text, in_tok, out_tok = _call(client, model, STRESS_PAIR_SYSTEM, ...)`), as do generate_quadrant_scenarios (594) and generate_dialect_variants (673). An anthropic SDK error (e.g. overloaded after internal retries) on round N propagates: no OUT file, no .report.json, tracker state lost — spend from rounds 1..N-1 is unrecorded anywhere (artifact upload warns-only; ledger scans sidecars). The 45-minute job timeout (workflow line 107) produces the same loss. scripts/translate_corpus.py shares the pattern: its report is written only at line 150 after the loop, and >25 failures raises RuntimeError at line 112 before any sidecar exists.
```
Proposed fix:
```diff
In each generation loop, guard the call the way evaluate_models does, preserving partial results:
-        text, in_tok, out_tok = _call(client, model, STRESS_PAIR_SYSTEM, "\n\n".join(parts),
-                                      max_tokens=GEN_MAX_TOKENS)
+        try:
+            text, in_tok, out_tok = _call(client, model, STRESS_PAIR_SYSTEM, "\n\n".join(parts),
+                                          max_tokens=GEN_MAX_TOKENS)
+        except Exception as e:  # keep spend accountable: land partial results + sidecar
+            logger.warning("generation call failed on round %d: %s", rounds, e)
+            rejected.append({"candidate": None, "reason": f"api_error: {e}"})
+            break
         tracker.record(model, in_tok, out_tok)
(same change in the quadrant and dialect loops; apply the equivalent try/break in translate_corpus.py so its sidecar always lands).
```
Verifier correction: Two evidence nuances and two fix gaps. Nuances: (1) the loss is of ACTUAL spend and generated content, not of all trace of the fire; fire_trigger.py journals every paid fire with its max_spend and counts it in-flight toward the $2/day ceiling for 8h (entry_is_active/inflight_max_spend), so same-day ceiling protection survives; what is permanently lost is the true cost and the paid-for pairs. (2) Severity is better stated as medium-high: bounded by the run's max_spend ceiling (default $2), but it breaks the CLAUDE.md cost-accountability invariant and silently discards paid generation output. Fix gaps: (a) `except Exception` does not catch the 45-minute CI timeout the finding itself cites; GitHub sends SIGINT (KeyboardInterrupt, a BaseException) then SIGKILL; robust repair needs per-round checkpointing (write OUT + sidecar after each round, cheap and idempotent) or a SIGINT/SIGTERM handler, not just the try/break. (b) Even with the try/break, a run that fails with 0 accepted pairs but nonzero recorded spend still loses its sidecar on main: the workflow's commit step is gated on `steps.gen.outputs.count != '0'`; the commit condition must also land the .report.json when count is 0 but cost_usd > 0. The rejected-entry shape in the patch is safe (write_generation_report only reads r["reason"]); apply the same guard inside generate_dialect_variants so generate_dialect_sweep keeps partial variants.
Found by: wf-paid. Verified: CONFIRMED.

#### F-H08 · `engine:scripts/jlens_insights.py:264` · silent-failure

No empty-input refusal: run from a checkout without trace_out/ (or with all summaries unreadable), it silently overwrites ops/jlens_insights.json AND the site's data/jlens_insights.json with an empty census (n_pairs 0), exit 0.

Evidence:
```
main() L261-272: `per_model = collect(Path(args.trace_root))` -> `analyze(...)` -> `out.write_text(...)` -> `site_copy.write_text(...)` with no guard; collect() returns {} for a missing/empty trace_root (glob matches nothing and succeeds). Contrast the sibling collector patch_aggregate.py L132-134 which refuses: `if not pairs: print("refused: no patching parts..."); return 3`, and export_jlens_depth.py which returns 3 on a degenerate exemplar. trace_out/ is intentionally absent in sparse checkouts (this audit worktree), so the hazard is realistic; the site page then falls to its 'data pending' catch (technical/index.html L884-886) even though real data existed in the previous file version.
```
Proposed fix:
```
In main(), after `per_model = collect(...)`:
```
if not per_model:
    print(f"refused: no jlens summaries under {args.trace_root} - not overwriting outputs")
    return 3
```
(and change `main()` to `raise SystemExit(main())` at the bottom so the 3 propagates, matching patch_aggregate.py).
```
Verifier correction: Two minor corrections. (1) Line number: the unguarded writes are L265 (ops copy) and L271 (site copy); L264 is the mkdir. The guard belongs after L261. (2) The proposed `if not per_model` guard is necessary but incomplete: it still writes an n_pairs-0 payload when summaries landed only for a non-base model (e.g. --base-model typo or only *__jlens_gemma-2-2b-it dirs present). Stronger fix: after collect(), `if not per_model.get(args.base_model): print(f"refused: no jlens summaries for {args.base_model} under {args.trace_root} - not overwriting outputs"); return 3`, plus changing L276 to `raise SystemExit(main())` (required; a bare `main()` discards the 3), matching patch_aggregate.py and export_jlens_depth.py. Severity note: outputs are git-committed and recoverable, but the Routine's data-republish flow can push the empty site copy with exit 0 and no digest signal, so high/silent-failure stands.
Found by: wf-new-analyses. Verified: CONFIRMED.

#### F-H09 · `engine:scripts/jlens_readout.py:379` · silent-failure

A mid-batch 4xx (400/404/422) silently discards every already-measured pair, writes a FALSE supported=false probe, and exits 0; the matrix leg stays green.

Evidence:
```
Lines 379-385: `if unsupported:` unconditionally writes `probe = {"model": args.model, "supported": False, "detail": unsupported, ...}` to jlens_probe.json and `return 0` — unlike the RuntimeError branch above it (L369-370: `if results or responses: raise`), there is no mid-batch guard, so N measured pairs are dropped with no jlens_summary written. Prompt-specific mid-batch 400s are a documented reality here (jlens_steer.py L160-169 handles exactly this: "mid-run 4xx is an anomaly - keep what we have and stop", after 'this branch wrongly declared probe-negative' on 2026-07-14). Worse, with commit_outputs=true the false probe is committed via the workflow's `git pull --rebase -X theirs` last-writer-wins (jlens_readout.yml L209-214), so it can replace a truthful supported=true probe from an earlier chunk in the same OUT_DIR. tests/test_jlens_readout.py covers only the first-call unsupported case (L285-318); the mid-batch case is untested.
```
Proposed fix:
```
In main()'s side loop, mirror the RuntimeError guard: before writing the probe, add
```
if unsupported:
    if results or responses:
        # mid-batch 4xx is an anomaly, not a capability verdict
        # (same contract as jlens_steer.py): keep measured pairs,
        # stop, and leave the probe alone.
        print(f"mid-batch unsupported response, stopping: {unsupported}")
        aborted = True
        break
    probe = {...}
```
with `aborted = False` before the pair loop and `if aborted: break` after the side loop (before build_result), so the summary write at L395-398 still lands the measured pairs.
```
Verifier correction: Finding stands as filed with two precision adjustments. (1) Evidence nuance: the "documented mid-batch 400" in jlens_steer.py L160-169 was steer-token-specific ("Could not resolve steer token"), a request field the readout call does not send; so a prompt-specific mid-batch 4xx on the plain lens readout is plausible-but-not-yet-observed for this exact call, while the structural asymmetry (5xx path guarded at L369-370, 4xx path unguarded at L379) and the already-fixed sibling (jlens_steer.py L170-175) make the defect real regardless. (2) Fix refinement: as proposed, an aborted run falls through to L399-401 and writes a supported=true probe with pairs_measured equal to the truncated count - that is accurate (a success preceded the 4xx) and desirable, but the truncated summary should carry "partial": true (matching jlens_steer's RuntimeError partial-summary convention at L144-150) so downstream consumers and the ops brief can distinguish a truncated chunk from a complete one; also note the edge case where the abort happens on pair 1's patient side (results=[]): an empty-results summary plus supported=true/pairs_measured=0 probe is written, which is harmless to export_jlens_depth.py's index join but worth a comment. Add the missing regression test: first call 200, second call 400, assert measured pairs land in jlens_summary and the probe is not supported=false.
Found by: wf-new-analyses. Verified: CONFIRMED.

#### F-H10 · `site:simulated-scenarios/index.html:1151` · mismatched-keys

The 'still tracing' progress line ignores payload.holdout_withheld: on the live payload it displays 'In progress; 84 of 835 accepted scenarios are still tracing; the table grows as chunks land' when 62 of those 84 are confirmatory-holdout pairs permanently withheld by the exporter; the true in-flight count is 22 of 773 and the table will never grow by the other 62. A wrong, never-converging number is shown today.

Evidence:
```
Lines 1148-1154: `var accepted=batches.reduce(function(a,b){ return a+((b.generated&&b.generated.accepted)||0); },0); if(accepted>scenarios.length){ ... el('b',null,(accepted-scenarios.length)+' of '+accepted+' accepted scenarios are still tracing') ... }`. Live payload probe: sum(generated.accepted)=835, scenarios.length=751, holdout_withheld=62, so 835-751-62=22 actually in flight. The exporter emits the field precisely for this accounting (export_frontend_simulated.py:352 `"holdout_withheld": withheld_holdout,`) but no page reads it (grep across all *.html: zero hits).
```
Proposed fix:
```diff
--- a/simulated-scenarios/index.html
+++ b/simulated-scenarios/index.html
@@ -1148,4 +1148,4
       var accepted=batches.reduce(function(a,b){
         return a+((b.generated&&b.generated.accepted)||0);
-      },0);
+      },0)-(data.holdout_withheld||0);
       if(accepted>scenarios.length){
(the strings then read '22 of 773 accepted scenarios are still tracing'; optionally append a sentence naming the withheld count, e.g. `if(data.holdout_withheld)pline.appendChild(el('span',null,' '+data.holdout_withheld+' confirmatory-holdout pairs are withheld until the registered endpoint runs.'));`)
```
Verifier correction: Finding stands as written, with two refinements. (1) Fix nuance: the exporter increments withheld_holdout only for holdout pairs whose traces have already landed (counter is inside the loop over base_results), so any not-yet-traced holdout pair is still transiently counted as 'still tracing' by the corrected arithmetic; 22 of 773 is the best number available from the payload and, unlike the current display, converges to 0. (2) Sibling pattern the finder missed, informational only: /home/user/audit-wb/patientwords/index.html:720-730 computes the same raw sum but labels it '835 generated pairs', which is literally accurate (generation-time count); not a defect, but check wording consistency if the fix lands.
Found by: sim-scenarios-index. Verified: CONFIRMED.

#### F-H11 · `site:simulated-scenarios/scenario.html:396` · mismatched-keys

When the selected model did not trace a phrase, cur() falls back to the whole scenario object; the top-level gemma-2-2b COMPAT mirror; so the page renders the base model's probabilities, spreads, clinical-mass meter, and even embeds gemma's circuit render under another model's selected chip. Repro on live data: select qwen3-4b on the series index and click Sim 663 (row shown 'not traced on qwen3-4b'; its link carries &model=qwen3-4b); scenario.html?sim=663&model=qwen3-4b shows gemma-2-2b's target token, both spreads, mass meters AND gemma's embedded render while the qwen3-4b chip is highlighted; only a small statline warns.

Evidence:
```
Line 396: `function cur(){return (s.models&&s.models[currentModel])||s;}` — contrast index.html:772 `function view(s){return hasModel(s)?cur(s):{};}` with the comment "so cells read '—' instead of silently borrowing the base model's numbers". renderCard() (line 437) uses `var m=cur();` unconditionally; lines 459/465 render m.prob_clinical/m.spread_clinical and line 508 `if(m.html){...embedBlock(card,m.html,...)}`. Live payload: 89 scenarios lack models['qwen3-4b'], and 3 of them (Sim 663, 686, 741) also carry the top-level gemma render field `html`.
```
Proposed fix:
```diff
--- a/simulated-scenarios/scenario.html
+++ b/simulated-scenarios/scenario.html
@@ -396 +396
-      function cur(){return (s.models&&s.models[currentModel])||s;}
+      function cur(){return hasModelFor(currentModel)?((s.models&&s.models[currentModel])||s):{};}
```
Verifier correction: Finding accurate as stated; two refinements. (1) Scope nuance: the bad state is unreachable via in-page chip clicks (unavailable chips are disabled at line 416); it is reached via the model URL param; which index.html manufactures for untraced rows (index.html:792-793); or any shared/bookmarked link, so severity high stands. (2) The proposed one-line fix to cur() is safe (single caller; spreadDetails/massLine/pending-note all handle {} correctly, restoring the intended em-dash/pending rendering) but incomplete: the disabled selected chip still gets the 'on' class (scenario.html:413) and the spread header renders 'prob()' with an empty token. Fuller fix: also normalize the URL param at line 394; after the modelList check, add `if(!hasModelFor(currentModel))currentModel=baseModel;` (moving hasModelFor's definition above it) or, alternatively, have index.html omit &model= on rows where !hasModel(s). Either variant breaks no other consumer.
Found by: sim-scenarios-index,sim-scenarios-detail. Verified: CONFIRMED.

### Medium: contract drift, degraded fallbacks, failure without signal

#### F-M01 · `engine:.github/workflows/circuit_trace_evaluation.yml:148` · mismatched-keys

Boolean trigger values are only lowercased when they are real JSON booleans, while the workflow compares against exact lowercase 'true'; so a trigger carrying "show_mitigation": "True" or "1" is counted as a PAID mitigation fire by fire_trigger.py's budget guard yet silently traces no mitigation panel; "commit_outputs": "True"/"1" silently skips branch checkpointing entirely.

Evidence:
```
Params heredoc line 148-149: 'params.update({k: str(v).lower() if isinstance(v, bool) else str(v) ...})' — string values pass through unmodified. Consumers require exact 'true': line 260 'if [ "$MITIGATE" = "true" ]; then ARGS+=(--show-mitigation)' and line 286 'if: ${{ always() && fromJson(needs.params.outputs.config).commit_outputs == 'true' }}'. But fire_trigger.py:69 treats the same params permissively: 'return trigger == "circuit-trace" and str(params.get("show_mitigation", "")).lower() in ("true", "1")' — so "1"/"True" commits imputed Anthropic budget in the ledger for a run that never makes the translation call, and the journal says a mitigation run landed when the parts contain no translated panel. For commit_outputs the failure is worse: outputs survive only as 90-day artifacts while the operator believes they were checkpointed to the branch.
```
Proposed fix:
```diff
--- a/.github/workflows/circuit_trace_evaluation.yml
+++ b/.github/workflows/circuit_trace_evaluation.yml
@@ (params heredoc, after the push/dispatch resolution, before 'offsets = ...' at line 155)
+          for key in ("show_mitigation", "commit_outputs"):
+              v = str(params[key]).strip().lower()
+              params[key] = "true" if v in ("true", "1", "yes") else "false"
           offsets = sorted({int(x) for x in params["offsets"].replace(",", " ").split()})
```
Verifier correction: The finding is accurate, but the proposed_fix is unsafe as written: it normalizes with ("true", "1", "yes") while fire_trigger.py's is_mitigation_fire accepts only ("true", "1"). With that fix, "show_mitigation": "yes" would run the PAID mitigation panel in CI while bypassing the budget guard entirely; inverting the bug into an unbudgeted Anthropic spend. Corrected fix: (a) in the workflow heredoc, normalize with exactly the predicate's set; params[key] = "true" if str(params[key]).strip().lower() in ("true", "1") else "false" for key in ("show_mitigation", "commit_outputs"); and (b) preferably also normalize or hard-reject non-canonical boolean values in scripts/fire_trigger.py before the trigger file is written (it is the sanctioned fire path, and a local exit-3 refusal is cheaper than a silent CI mismatch), with a regression test. Also, the same permissive-bool-vs-strict-'true' pattern exists in jlens_readout.yml (line 109 vs 194), activation_patching.yml (99 vs 214), and logits_evaluation.yml (84 vs 159) for commit_outputs/save_raw; those are $0 workflows so only the silent checkpoint-skip half applies, but they should be normalized in the same pass.
Found by: wf-circuit-trace. Verified: CONFIRMED.

#### F-M02 · `engine:.github/workflows/circuit_trace_evaluation.yml:283` · silent-failure

With show_mitigation=true (or mode=translation) and a missing/empty ANTHROPIC_API_KEY secret, the 'translated' panel silently degrades to a phrase-table rewrite or the UNCHANGED patient prompt; the job stays green and mitigation_recovery/urgency_recovery are computed from the degraded panel and pooled downstream, because no consumer reads translation_method.

Evidence:
```
Workflow line 232 passes 'ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}' (empty string if the secret is absent) and line 283 runs medlang-batch-eval with no key precheck. llm_client.py:56-57 '_get_client(): if not os.environ.get("ANTHROPIC_API_KEY"): return None' -> translate_with_llm returns None -> translate.py:56-70 falls back to phrase table then '{"text": patient_text, "method": "unchanged"}' with only logger.warning. batch_eval.py:551-570 then traces that text as the third panel and records mitigation_recovery as a real measurement (~0 for 'unchanged'). urgency_shift.py:332-336 pools every row with urgency_recovery != None into mean_urgency_recovery; grep for translation_method across scripts/ returns zero consumers, so the recorded method label is never checked. CLAUDE.md also promises a '.mitigation.report.json' cost sidecar for mitigation fires — a keyless run produces the measurements without any spend record distinguishing it.
```
Proposed fix:
```diff
--- a/.github/workflows/circuit_trace_evaluation.yml
+++ b/.github/workflows/circuit_trace_evaluation.yml
@@ (start of the 'Run batch evaluation' run: block, before medlang-batch-eval)
+          MODE="${{ fromJson(needs.params.outputs.config).mode }}"
+          if { [ "$MITIGATE" = "true" ] || [ "$MODE" = "translation" ]; } && [ -z "${ANTHROPIC_API_KEY:-}" ]; then
+            echo "::error::LLM translation requested (show_mitigation/mode=translation) but ANTHROPIC_API_KEY is empty; refusing to record a phrase-table/unchanged panel as mitigation"
+            exit 1
+          fi
           medlang-batch-eval "${ARGS[@]}"
```
Verifier correction: Finding stands as written with minor citation tightening: batch_eval.py translation call is at lines 550-555 and mitigation_recovery/translation_method recording at 619-622 (not 551-570); llm_client._get_client spans 55-63. Deepening (branch evidence): mode=translation degrades identically via batch_eval.py:812 (method recorded at 851) and the proposed guard's MODE check correctly covers it, including the placebo arm (MEDLANG_TRANSLATION_PLACEBO reroutes inside translate_with_llm, same key requirement); CI installs pip install ".[llm]" (workflow line 197), so a missing/rotated secret is the sole silent-degrade path in CI; beyond urgency_shift.py pooling, the frontend translation-vs-placebo provenance display (patientwords data/provenance.json:625, referee item 6) is computed from the same trace_out dirs with no method check, so a keyless arm would silently corrupt that comparison as well.
Found by: wf-circuit-trace. Verified: CONFIRMED.

#### F-M03 · `engine:.github/workflows/circuit_trace_evaluation.yml:327` · fragile-parsing

The 'Publish summary to run page' step picks the lexicographically first batch_summary*.json in OUT_DIR, which on any second-or-later chunk is a stale part from a PREVIOUS run (or a sibling matrix cell pulled in by the commit step's rebase), so the run page shows the wrong chunk's data under this cell's heading; a complete-looking summary that masks a truncated or failed leg.

Evidence:
```
Line 327: 'SUMMARY=$(ls "$OUT_DIR"/batch_summary*.json 2>/dev/null | head -1 || true)'. With commit_outputs=true this run's summary was already renamed to part_NN (line 298), and the checkout at github.sha contains parts committed by earlier chunk runs on the branch (the trigger push is their descendant); e.g. the live trigger (.github/trigger/circuit-trace.json: offsets "15", commit_outputs "true") writes part_16 while the dir holds part_01/part_06/part_11 from earlier fires — ls|head -1 selects part_01, yet the heading printed at line 330 says 'offset 15'. Also bites when the eval step fails before pair 1 (no batch_summary.json exists) and the step runs under if: always(): it prints a stale part instead of nothing. After the commit step's 'git pull --rebase -X theirs' (line 315), sibling cells' parts are in the tree too.
```
Proposed fix:
```diff
--- a/.github/workflows/circuit_trace_evaluation.yml
+++ b/.github/workflows/circuit_trace_evaluation.yml
@@
       - name: Publish summary to run page
         if: always()
+        env:
+          OFFSET: ${{ matrix.offset }}
         run: |
-          SUMMARY=$(ls "$OUT_DIR"/batch_summary*.json 2>/dev/null | head -1 || true)
+          PART="$OUT_DIR/batch_summary.part_$(printf '%02d' $((OFFSET + 1))).json"
+          SUMMARY=""
+          [ -f "$OUT_DIR/batch_summary.json" ] && SUMMARY="$OUT_DIR/batch_summary.json"
+          [ -z "$SUMMARY" ] && [ -f "$PART" ] && SUMMARY="$PART"
           if [ -n "$SUMMARY" ]; then
```
Verifier correction: One overstatement to trim: with commit_outputs=false a successful leg still displays correctly even when stale parts are present, because batch_summary.json sorts lexicographically before batch_summary.part_* ('.j' < '.p'). The defect therefore bites specifically (a) commit_outputs=true chained/fanned runs; which is the current live trigger configuration; and (b) any leg that fails before producing batch_summary.json while stale parts sit in the checkout. Severity medium stands on observability grounds (the run page masks truncated/failed legs during chained overnight runs); no committed data or downstream consumer is corrupted. The proposed fix is correct as written; optionally guard the future offset>=99 case where printf '%02d' produces 3-digit parts (e.g. part_100), which the rename at line 298 shares, so the fix's format-matching still holds.
Found by: wf-circuit-trace. Verified: CONFIRMED.

#### F-M04 · `engine:.github/workflows/jlens_readout.yml:167` · mismatched-keys

Steering runs stamp OUT_DIR with the matrix model, but jlens_steer.py takes its model from spec["model"] and has no --model flag; a models/spec mismatch silently commits data under a directory naming a model that was never measured, and a multi-model matrix re-runs the identical steer grid once per leg.

Evidence:
```
yml L161-167: `if [ -n "$STEER_SPEC" ]; then STEM=$(basename "$STEER_SPEC" .json); KIND="jsteer"; fi` then `echo "OUT_DIR=trace_out/${STEM}__${KIND}_${MODEL}"` where `MODEL: ${{ matrix.model }}`; the steer invocation (L183-184) passes only --spec/--out/--limit/--offset/--topn, and jlens_steer.py L111 reads `model = spec["model"]` (its argparse at L94-99 defines no --model). Firing jlens-readout with the default models "qwen3-1.7b" plus a gemma-2-2b steer spec writes gemma measurements into trace_out/<spec>__jsteer_qwen3-1.7b/ (jsteer_summary's internal graph_model is correct, but every path/dir-name consumer joins on the __jsteer_<model> suffix); with two matrix models, both legs execute the same spec end-to-end (duplicate hosted calls, duplicate committed raw).
```
Proposed fix:
```
In 'Resolve output dir', derive the dir model from the spec on steering runs and pin the matrix to one leg:
```
if [ -n "$STEER_SPEC" ]; then
  STEM=$(basename "$STEER_SPEC" .json); KIND="jsteer"
  MODEL=$(python -c "import json,os;print(json.load(open(os.environ['STEER_SPEC']))['model'])")
fi
```
plus a leg guard so only the first matrix model runs steering: `if [ -n "$STEER_SPEC" ] && [ "${{ strategy.job-index }}" != "0" ]; then echo skip; exit 0; fi` (or document that steer fires must use a single-model list).
```
Verifier correction: Real latent defect, severity low-to-medium. jlens_readout.yml "Resolve output dir" (L167) names the steering output dir with matrix.model, but jlens_steer.py has no --model flag and reads the model from spec["model"] (L111); the workflow default models is qwen3-1.7b while both committed steer specs pin gemma-2-2b, so a steer fire that omits a models override commits gemma measurements under trace_out/<spec>__jsteer_qwen3-1.7b/, and an N-model matrix runs the identical steer grid N times (duplicate hosted calls and committed raw). Impact correction: no script currently consumes __jsteer_ dirs, and jsteer_summary's graph_model is correct, so the harm is mislabeled committed provenance (contradicting the naming contract in docs/lens_steering_design.md) plus duplicate execution; not corrupted automated joins; the trigger journal shows every steer fire to date used a matching single-model override, so nothing landed is mislabeled. Fix correction: do it in the params job (which has a checkout), not per-leg; when steer_spec is non-empty, read spec["model"] and emit models=[that model], collapsing the matrix to one correctly-named leg; the finder's per-step `echo skip; exit 0` guard is ineffective because a successful step exit does not skip the job's remaining steps. This params-level fix breaks no consumer (the commit step keys off $OUT_DIR; nothing else parses __jsteer_ names).
Found by: wf-new-analyses. Verified: CONFIRMED.

#### F-M05 · `engine:.github/workflows/logits_evaluation.yml:77` · silent-failure

When commit_outputs is not 'true' (the default for BOTH workflow_dispatch and a push-path trigger JSON that omits the key), a fully green multi-hour run discards every batch_summary at job end - the workflow has no upload-artifact step, so the only survivor is the human-readable GITHUB_STEP_SUMMARY text.

Evidence:
```
logits_evaluation.yml:75-77 push-path defaults: `defaults = {"models": ..., "limit": "0", "offset": "0", "commit_outputs": "false"}`; :37-40 workflow_dispatch `commit_outputs: ... default: false`. The eval job's steps are exactly: checkout, setup-python, pip install, swap provision, resolve dir, measure, conditional commit (`if: ${{ always() && needs.params.outputs.commit_outputs == 'true' }}`, line 159), job summary - there is no actions/upload-artifact anywhere in the file, so with commit_outputs=false the JSON written to $OUT_DIR dies with the runner while the run shows green. (The tracer workflow keeps heavyweight outputs as artifacts - circuit_trace_evaluation.yml:295 "*.tagged.json graphs stay artifact-only" - the logits workflow kept neither path.)
```
Proposed fix:
```
Add an unconditional artifact upload after the Measure step so results survive regardless of commit_outputs:

      - name: Keep the summary as a run artifact
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: batch-summary-${{ matrix.model }}
          path: ${{ env.OUT_DIR }}/batch_summary.*.json
          if-no-files-found: warn
          retention-days: 30
```
Verifier correction: Defect real as stated; two contextual corrections. (1) Practical exposure is narrower than the summary implies: the current .github/trigger/logits-eval.json explicitly sets "commit_outputs":"true" and the workflow's header example does too, so live push-path fires are unaffected today; the trap is a workflow_dispatch run left on defaults or a future trigger edit omitting the key. Medium severity stands as a latent silent-failure. (2) "the only survivor is the human-readable GITHUB_STEP_SUMMARY text"; job logs also retain per-pair stdout (probabilities + penalty), so partial manual recovery is possible, but the schema JSON (continuations map, metadata) is unrecoverable. Proposed fix is correct as written; one refinement for consistency with the tracer workflow's naming: include the offset in the artifact name (e.g. batch-summary-${{ matrix.model }}-offset${{ needs.params.outputs.offset }}) so artifacts from chunked reruns downloaded together stay distinguishable; not required for correctness since artifacts are per-run scoped.
Found by: wf-logits. Verified: CONFIRMED.

#### F-M06 · `engine:.github/workflows/model_evaluation.yml:150` · mismatched-keys

The evaluation publish path dead-ends in the engine repo: the workflow commits data/evaluations/model_evaluations_frontend.json to the dispatched branch, while the site serves patientwords/data/model_evaluations.json; no script or workflow bridges the copy+rename, so the public table goes silently stale.

Evidence:
```
Line 150 writes 'data/evaluations/model_evaluations_frontend.json'; grep across the engine worktree shows the ONLY references to that filename are inside this workflow (lines 150, 156) — no exporter, sync script, or Routine tooling reads it (unlike simulated scenarios, which have export_frontend_simulated.py). The frontend contract is 'data/model_evaluations.json' (patientwords/CLAUDE.md:54; fetched at patientwords/methods.html:423), whose committed copy is dated "updated": "2026-07-12" — every eval run since then updates only the engine-side file. On fetch failure/staleness the page shows 'data pending' with no freshness check, so drift produces no signal. Same shape as the accepted archive_export.*/simulated_archive.* manual-rename gap, but a distinct file pair not covered by that finding.
```
Proposed fix:
```diff
Remove the rename half of the gap so publishing is a bare copy, and document the copy step:
-          pathlib.Path("data/evaluations").mkdir(parents=True, exist_ok=True)
-          pathlib.Path("data/evaluations/model_evaluations_frontend.json").write_text(
+          pathlib.Path("data/evaluations").mkdir(parents=True, exist_ok=True)
+          pathlib.Path("data/evaluations/model_evaluations.json").write_text(
@@
-          git add data/evaluations/model_evaluations_frontend.json
+          git add data/evaluations/model_evaluations.json
plus one line in docs (routine standing prompt): after an eval run lands, `cp data/evaluations/model_evaluations.json ../patientwords/data/` — or fold the file into the existing claim_check.py manifest so staleness is detected.
```
Verifier correction: Two corrections. (1) Evidence understated: beyond staleness, the frontend's "updated": "2026-07-12" stamp was bumped by the 2026-07-14 nightly-refresh commit (f05fd7c) WITHOUT copying content (the models array is byte-identical to the 2026-07-07 import), so the page misrepresents its own freshness; and the engine-side file demonstrates concrete divergence; it holds a haiku-only single-model payload from a run that never reached the site. (2) The proposed fix is unsafe as written: the workflow rebuilds the payload from a single run's results.json listing only that run's models, and the workflow default model_selection is claude-haiku-4-5 (yml:14), so a bare rename+cp after a default run would silently replace the public 3-model table with a 1-row table (exactly the engine file's current state); methods.html would render it without complaint. The rename half is safe (only the workflow references the old name). Corrected fix: have the publish step merge per-model rows by id into the existing table (load prior file, update evaluated models, preserve the rest, bump "updated" only on content change) or gate frontend publishing on model_selection=all; and add data/model_evaluations.json to the claim_check.py staleness manifest so future drift fails loudly.
Found by: wf-paid. Verified: CONFIRMED.

#### F-M07 · `engine:.github/workflows/model_evaluation.yml:158` · silent-failure

The frontend-export push retry loop exits green when all 3 pull+push attempts fail, silently discarding the committed export (and the run's only committed cost record) with the runner.

Evidence:
```
Lines 158-161:
  for i in 1 2 3; do
    git pull --rebase origin "$BRANCH" && git push origin HEAD:"refs/heads/$BRANCH" && break
    sleep $((i * 2))
  done
The for-loop's exit status is the last `sleep` (0) when every attempt fails (e.g. a rebase conflict on the branch, or three lost push races), so under `set -euo pipefail` the step still succeeds and the job is green while data/evaluations/model_evaluations_frontend.json never reaches the remote. Contrast the deliberate pattern in scenario_generation.yml lines 305-312, which sets a `pushed` flag and emits `::error::` + exit 1 after exhaustion (added after the 2026-07-13 lost-batch incident).
```
Proposed fix:
```diff
-          for i in 1 2 3; do
-            git pull --rebase origin "$BRANCH" && git push origin HEAD:"refs/heads/$BRANCH" && break
-            sleep $((i * 2))
-          done
+          pushed=0
+          for i in 1 2 3; do
+            if git pull --rebase origin "$BRANCH" && git push origin HEAD:"refs/heads/$BRANCH"; then pushed=1; break; fi
+            git rebase --abort 2>/dev/null || true
+            sleep $((i * 2))
+          done
+          if [ "$pushed" != "1" ]; then echo "::error::frontend export push failed after 3 attempts"; exit 1; fi
```
Verifier correction: Two refinements, neither changing the verdict: (1) the defect is slightly worse than stated; a rebase conflict on attempt 1 leaves a rebase in progress, so `git pull --rebase` on attempts 2 and 3 is guaranteed to fail; the loop is effectively single-try in the conflict case (the fix's `git rebase --abort || true` correctly addresses this and should be kept); (2) "the run's only committed cost record" is accurate but should note the loss does not weaken the $2/day budget enforcement, which counts fire-journal max_spend, not this export; what is silently lost is the published per-model cost_usd record and the frontend evaluation table update. Severity medium is appropriate; line 158 and the proposed fix are correct as written.
Found by: wf-paid,wf-archive-ops. Verified: CONFIRMED.

#### F-M08 · `engine:.github/workflows/scenario_generation.yml:90` · other

Nothing mechanical guards the documented merge/copy danger: all 7 workflows fire on any push touching their trigger path with no condition on the commit, so a merge to main that carries a trigger-file change re-fires a paid workflow, un-journaled and outside fire_trigger's daily-ceiling guard (answering the audit question: the guard is documentation only).

Evidence:
```
Every workflow has `on: push: paths: [.github/trigger/<name>.json]` (scenario_generation.yml lines 90-92) with no job-level `if`; grep across .github/workflows/*.yml finds no head_commit/message/merge guard. fire_trigger.py only governs sanctioned fires and commits with message `Fire {args.trigger}: {args.note}` (line 575), which merge commits ('Merge ...') never carry — a cheap discriminator the workflows ignore.
```
Proposed fix:
```diff
Add to each workflow (shown for scenario_generation.yml; adjust the trigger name per file):
 jobs:
   generate:
+    if: >-
+      github.event_name == 'workflow_dispatch' ||
+      startsWith(github.event.head_commit.message, 'Fire scenario-generation')
     runs-on: ubuntu-latest
This makes fire_trigger.py's existing commit-message convention load-bearing and turns merge re-fires into visible skipped runs.
```
Verifier correction: Finding is correct as stated. The proposed_fix needs two adjustments: (1) place the `if` on the ROOT job of each workflow; four workflows are two-job (params → worker via needs: params), so the guard belongs on `params` (skipped needs auto-skip dependents); single-job workflows guard `generate`/`evaluate`/`archive`. Trigger names are mutually non-prefix, so startsWith is safe, and `github.event.head_commit` being null on workflow_dispatch is harmless in Actions expressions. (2) The gate makes fire_trigger.py's commit message load-bearing and fail-closed: it silently-skips (visibly, as a skipped run) the documented alternative path in the workflow headers ("push a parameters file to .github/trigger/..."), and a multi-commit push where the Fire commit is not HEAD would also skip a sanctioned fire. Update the workflow header comments and .github/trigger/README.md to state the required `Fire <trigger>:` prefix, and note that any non-fire_trigger automation pushing trigger files must adopt it. No schedule: triggers exist, so no cron path is affected.
Found by: wf-archive-ops. Verified: CONFIRMED.

#### F-M09 · `engine:.github/workflows/scenario_generation.yml:152` · fragile-parsing

The two PAID workflows' push-path heredocs are the only ones lacking JSON-list-to-CSV normalization: a list value for topics or graph_models str()s to "['a', 'b']", silently steering a paid generation run with bracket/quote-mangled topics or making every trace leg fail warn-only; fire_trigger validates key names but not value types, so nothing catches it locally.

Evidence:
```
Line 152: `params.update({k: str(v) for k, v in overrides.items() if k in defaults})` — no isinstance(list) handling; same in model_evaluation.yml line 87. All four $0 workflows normalize (activation_patching.yml:96 `# JSON lists -> CSV before str()`; circuit_trace_evaluation.yml:144-147; logits_evaluation.yml and jlens_readout.yml normalize `models`). CLAUDE.md's own tests note names this exact pitfall: 'JSON lists must be normalized to CSV before str()'.
```
Proposed fix:
```diff
--- a/.github/workflows/scenario_generation.yml
+++ b/.github/workflows/scenario_generation.yml
@@ -149,6 +149,9 @@
           if os.environ["EVENT_NAME"] == "push":
               with open(".github/trigger/scenario-generation.json", encoding="utf-8") as f:
                   overrides = json.load(f)
+              for key in ("topics", "graph_models", "dialects"):   # JSON lists -> CSV before str()
+                  if isinstance(overrides.get(key), list):
+                      overrides[key] = ",".join(str(x) for x in overrides[key])
               params.update({k: str(v) for k, v in overrides.items() if k in defaults})
(mirror for model_evaluation.yml if list-valued model_selection is ever plausible).
```
Verifier correction: Corrections: (1) model_evaluation.yml location is line 86, not 87. (2) The proposed fix's uniform ",".join is wrong for two of the three keys because each key's consumer uses a different delimiter: topics is comma-split (scenario_generation.yml:214, comma-join correct); graph_models is whitespace-split (line 338, `for M in $MODELS`) so it must be " ".join; a comma-joined multi-model value would parse as one bogus model name and reproduce exactly the warn-only all-trace-legs-fail failure the fix targets (matching how logits_evaluation.yml:83 and jlens_readout.yml:108 space-join their models key); dialects is pipe-split (line 241, labels documented as possibly containing spaces and commas) so it must be "|".join. Corrected normalization for scenario_generation.yml push path: for (key, sep) in (("topics", ","), ("graph_models", " "), ("dialects", "|")): if isinstance(overrides.get(key), list): overrides[key] = sep.join(str(x) for x in overrides[key]). For model_evaluation.yml, model_selection is whitespace-split via unquoted --models expansion (line 106), so a list would need " ".join. Also consider a belt-and-suspenders type guard in fire_trigger.py validate_params (reject or normalize list values at the mandated fire path), though the workflow-side fix is still needed because trigger files can land via direct pushes.
Found by: wf-archive-ops. Verified: CONFIRMED.

#### F-M10 · `engine:data/claims_manifest.json:288` · doc-drift

claim_check purports to police every hardcoded number in site prose, but three clusters of hardcoded methods.html numbers have no manifest entry: the worked-example percentages (30%/26%, line 291), the reading-layers depth narrative (readable from layer 10, first place by layer 19, appears 9 layers later, never above second place, lines 347-350), and 'three sentinel pairs' (line 231); all verified accurate against current data but unguarded, and the depth narrative silently breaks if export_jlens_depth.py is re-run with a different --exemplar-stem/--exemplar-index.

Evidence:
```
Manifest methods.html claims cover only: 'census, set by set' (len(blocks)>0), model-count 8, 'domain review pending', medgemma CI/n, 'at most 0.027 across the', 'every top word held'. Verified against data: provenance.json translation_cases.grandma_laxative clinical[1]=0.263 (26%) and patient[1]=0.299 (30%); jlens_depth exemplar clin_ranks min layer 10, first rank-1 layer 19, pat_ranks min layer 19 (=10+9), best patient rank 2; drift_series series has 3 pairs/day. The only jlens guard, expr `len(d['blocks']) > 0`, does not pin the exemplar. Note claim_check's eval sandbox (claim_check.py lines 23-27) lacks int(), so new exprs must avoid int-casting layer keys.
```
Proposed fix:
```diff
Append to the claims array:
+  {"page":"methods.html","snippet":"(30%, against the laxative","source":"data/provenance.json",
+   "expr":"[round(d['translation_cases']['grandma_laxative']['patient'][1]*100), round(d['translation_cases']['grandma_laxative']['clinical'][1]*100)]",
+   "expected":[30,26]},
+  {"page":"methods.html","snippet":"readable from layer 10 and reaches","source":"data/jlens_depth.json",
+   "expr":"[d['exemplar']['clin_ranks'].get('10'), d['exemplar']['clin_ranks'].get('19'), d['exemplar']['pat_ranks'].get('19'), min(d['exemplar']['pat_ranks'].values())]",
+   "expected":[8,1,2,2]},
+  {"page":"methods.html","snippet":"across the three sentinel pairs","source":"data/drift_series.json",
+   "expr":"len(d['series'][sorted(d['series'])[-1]])","expected":3}
```
Verifier correction: Finding stands as stated (file/lines/severity accurate). Proposed fix needs one correction: in the third claim entry, replace snippet "across the three sentinel pairs" (not present in the raw HTML; the phrase wraps across lines 230-231, so claim_check would only warn, not guard) with "three sentinel pairs, and every" (verified present on line 231 as a single-line substring). The other two entries are correct as proposed: snippets "(30%, against the laxative" and "readable from layer 10 and reaches" both match the page, and all three exprs evaluate to the expected values ([30,26], [8,1,2,2], 3) under claim_check's restricted eval sandbox. Additive manifest entries break no consumer (claims_manifest.json is read only by scripts/claim_check.py and tests/test_claim_check.py).
Found by: methods-sentinel-bundle. Verified: CONFIRMED.

#### F-M11 · `engine:medlang_circuits/batch_eval.py:551` · doc-drift

CLAUDE.md promises every paid run writes a `.report.json` (or `.mitigation.report.json`) sidecar, but no code path writes mitigation sidecars and the mitigation panel records no cost at all; the three `*.mitigation.report.json` files in data/simulated/ are hand-authored; a forgotten or mis-estimated hand entry means the landed side of the $2/day guard permanently undercounts real Anthropic spend.

Evidence:
```
Line 551: `translation = translate_to_clinical(patient_prompt, use_llm=use_llm_translation, model=llm_model)` — the result dict captures only translation_method/translation_model (lines 623-624), no tokens or cost_usd; repo-wide grep for `mitigation.report` matches only docs, CLAUDE.md:69, dashboard entries_seen, and the three hand-made files in data/simulated/. circuit_trace_evaluation.yml's commit glob (line 301) commits only index_* and batch_summary.part_* — even a sidecar written to $OUT_DIR would be dropped. Fire-time coverage is only the flat imputed $0.15 (fire_trigger.py:65), which expires with the journal entry.
```
Proposed fix:
```
Have the mitigation path count its translation calls/tokens and write `<out>/mitigation.report.json` (run_timestamp, model, cost_usd, batch stem) at the end of run_batch when show_mitigation is set; add that filename to the FILES glob in circuit_trace_evaluation.yml line 301 and teach the resolve flow to copy it to data/simulated/<stem>.mitigation.report.json so ledger_update.py (which already globs `*.report.json`) folds it. Until then, correct CLAUDE.md line 69 to state mitigation sidecars are hand-written.
```
Verifier correction: Finding is accurate as stated at batch_eval.py:551; add the deeper root cause: llm_client.translate_with_llm (llm_client.py:88-104) discards response.usage, so implementing the fix requires changing its return contract (or a usage callback), not just plumbing in run_batch. Fix refinements: (1) chunked offset runs share $OUT_DIR; write mitigation.report.part_NN.json (mirroring batch_summary.part_NN) and aggregate at resolve time into data/simulated/<stem>.mitigation.report.json, else chunks clobber each other; (2) ledger_update.batch_file_name maps <stem>.mitigation.report.json to a nonexistent <stem>.mitigation.json archive name; harmless today because Tier B attribution is gated on task=="pairs", but worth a comment or a task-aware mapping; (3) the interim CLAUDE.md correction should also note the imputed fire-time guard ($0.15, fire_trigger.py:65) expires with the journal entry, so landed-spend accuracy currently rests on the hand-authored estimate. Severity medium is appropriate.
Found by: wf-archive-ops. Verified: CONFIRMED.

#### F-M12 · `engine:medlang_circuits/evaluate_models.py:124` · silent-failure

CostTracker.can_afford under-estimates worst-case call cost ~20x for scenario generation (assumes 200 output tokens while generation calls allow 4096), so the 'hard' max_spend ceiling can be silently exceeded.

Evidence:
```
Line 124: `worst_case = EST_INPUT_TOKENS * in_price / 1e6 + MAX_OUTPUT_TOKENS * out_price / 1e6` with EST_INPUT_TOKENS=500, MAX_OUTPUT_TOKENS=200 (lines 88-89). scenario_gen.py passes `max_tokens=GEN_MAX_TOKENS` (4096, line 475-476) and DIALECT_MAX_TOKENS (2048, line 673), and its prompt grows every round with all seed examples plus the full 'already used' list (lines 469-474) — thousands of input tokens. On claude-sonnet-5 the check's worst case is $0.0045 while an actual round can cost ~$0.08 (6k in + 4096 out); the loop therefore admits a final call when only $0.0045 headroom remains, and `record()` (post-hoc, line 130) books spent > max_spend with no refusal, warning, or truncated flag distinction. The live trigger fires with max_spend 0.50, so overshoot of ~15% per run is possible; fire_trigger's daily-ceiling math assumes max_spend bounds actuals. The module docstring (lines 37-39) claims a 'conservative worst-case cost' check — true only for its own 200-token calls.
```
Proposed fix:
```diff
--- a/medlang_circuits/evaluate_models.py
-    def can_afford(self, model: str) -> bool:
-        in_price, out_price = _price(model)
-        worst_case = EST_INPUT_TOKENS * in_price / 1e6 + MAX_OUTPUT_TOKENS * out_price / 1e6
+    def can_afford(self, model: str, max_output_tokens: int = MAX_OUTPUT_TOKENS,
+                   est_input_tokens: int = EST_INPUT_TOKENS) -> bool:
+        in_price, out_price = _price(model)
+        worst_case = est_input_tokens * in_price / 1e6 + max_output_tokens * out_price / 1e6
--- a/medlang_circuits/scenario_gen.py (each loop condition)
-    while ... and tracker.can_afford(model):
+    while ... and tracker.can_afford(model, max_output_tokens=GEN_MAX_TOKENS,
+                                     est_input_tokens=max(2000, sum(len(p) for p in parts) // 3 if rounds else 2000)):
(dialect loops pass DIALECT_MAX_TOKENS; translate_corpus passes 256).
```
Verifier correction: Finding is accurate as stated (file, line, mechanism, severity). One correction to the proposed_fix: the can_afford signature change (optional max_output_tokens/est_input_tokens kwargs) is safe and backward compatible, but the scenario_gen call-site sketch is fragile; it references `parts` inside the while condition, which only exists from the previous iteration (estimating the prior round's prompt, not the upcoming one) and does not exist at all in generate_dialect_variants (which builds `prompt`, not `parts`). Safer fix: assemble the round's prompt first, then check tracker.can_afford(model, max_output_tokens=<the actual max_tokens for that call>, est_input_tokens=len(prompt)//3) immediately before _call, breaking out of the loop (tracker.truncated=True) when unaffordable; the existing truncated flag and report schema already handle early exit, so no downstream consumer breaks.
Found by: wf-paid. Verified: CONFIRMED.

#### F-M13 · `engine:scripts/coverage_gaps.py:68` · other

patientwords/data/specialties.json has no writer at all: it is a byte-identical manual copy of the engine's data/specialty_map.draft.json (the file specialty_breakdown.py and coverage_gaps.py only READ), so taxonomy edits that steer generation (coverage_gaps steer_topics) will not reach the site's specialty filter chips until someone remembers the undocumented copy+rename.

Evidence:
```
coverage_gaps.py: `parser.add_argument("--map", default="data/specialty_map.draft.json")` and `parser.add_argument("--out", default="ops/coverage_gaps.json")`; specialty_breakdown.py identically reads --map and writes ops/specialty_breakdown.json. Repo-wide grep finds no code writing 'specialties.json'. Verified: json.load(site data/specialties.json) == json.load(engine data/specialty_map.draft.json) exactly (14 specialties, incl. '_' and 'status': 'draft pending owner review'). simulated-scenarios/index.html line 582 fetches it and builds the topic->specialty filter map (lines 604-612); a stale copy silently mis-bins new generation topics into 'Other'.
```
Proposed fix:
```diff
Publish the map from the script that already loads it (coverage_gaps.py, after `site = Path(args.site)`):
     map_payload = json.loads(Path(args.map).read_text(encoding="utf-8"))
     site = Path(args.site)
+    # the site's filter taxonomy is this map; keep the copy scripted
+    (site / "data" / "specialties.json").write_text(
+        json.dumps(map_payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
(or add an equivalent --publish flag if unconditional writes are unwanted).
```
Verifier correction: Two refinements. Severity: closer to low-medium than medium; the engine map's own '_' field states 'Topics not in the map render under Other so new batches degrade gracefully', i.e. the Other fallback is designed degradation of a draft presentational taxonomy with no claim riding on it; the defect is the undocumented, unscripted cross-repo copy (process gap; copies are currently byte-in-sync), not a live rendering bug. Fix: prefer the finder's own alternative; a --publish flag on coverage_gaps.py (mirroring the existing urgency_shift.py --publish convention) rather than the unconditional write shown in the diff, since an ops analysis script silently writing into the sibling site repo on every run is a surprising side effect; write the loaded map payload verbatim to <site>/data/specialties.json (shape is what index.html reads; formatting irrelevant to fetch). Hosting the write in export_frontend_simulated.py would require newly loading the map there, so coverage_gaps.py is the right host. Either variant breaks no consumer.
Found by: methods-sentinel-bundle. Verified: CONFIRMED.

#### F-M14 · `engine:scripts/export_dialect_matrix.py:70` · mismatched-keys

dialect-differences reads items[].core (matrix 'core' column and the whole dialect-invariant-features section) but the payload writer never emits it, and re-running the exporter silently destroys the separate augmenter's core data; the live data/dialects.json has no core on any item, so the column is permanently em-dash and the section never renders.

Evidence:
```
Writer export_dialect_matrix.py:70-78 builds each item as items.append({"index":..., "term":..., "baseline_prompt":..., "target_token":..., "baseline_p":..., "render":..., "variants":...}) — no core — and :89-90 rewrites the whole file (json.dump(payload, f, indent=1)). core comes only from dialect_invariant_core.py:116-122 which 'augment[s] ... in place' AFTER export. Consumer dialect-differences/index.html:404 'if(it.core){ cc.textContent=it.core.invariant+"/"+it.core.baseline_clinical; ... }else{cc.textContent=String.fromCharCode(8212);}' and :532 'if(feat.core&&feat.core.top&&feat.core.top.length){ ... document.getElementById("dl-core").hidden=false;}'. Live instance check: all 5 items have keys ['index','term','baseline_prompt','target_token','baseline_p','render','variants'] — core absent, so the header column added unconditionally at :366-368 (title 'clinical features surviving every framing / clinical features in the baseline trace') shows only em-dashes and dl-core stays hidden while its caption (:277-280) promises 'Computed from the committed renders'.
```
Proposed fix:
```diff
--- a/scripts/export_dialect_matrix.py
+++ b/scripts/export_dialect_matrix.py
@@
     items.sort(key=lambda it: it.get("index") or 0)
     batch = os.path.basename(os.path.normpath(args.trace_dir))
+    # preserve dialect_invariant_core.py's in-place augmentation across re-exports
+    if os.path.exists(args.out):
+        with open(args.out, encoding="utf-8") as f:
+            prev = json.load(f)
+        if prev.get("batch") == batch:
+            prev_cores = {it.get("index"): it["core"] for it in prev.get("items", []) if it.get("core")}
+            for it in items:
+                if it["index"] in prev_cores:
+                    it["core"] = prev_cores[it["index"]]
     payload = {
(and re-run scripts/dialect_invariant_core.py against the committed dialects_20260708T120729Z renders to restore core in the live payload)
```
Verifier correction: Two trivial citation refinements: the augmenter's core assignment is at dialect_invariant_core.py:119 (item["core"] = core; file rewrite at :121-122), and the dl-core caption is at dialect-differences/index.html:278-280 (not 277). Substance, severity (medium), and proposed_fix stand as filed; the fix should also note that restoring the live payload requires the committed dialects_20260708T120729Z renders (present in the real repo; the audit worktree's sparse checkout omits trace_out/, which is why the augmenter cannot be re-run from here).
Found by: small-pages. Verified: CONFIRMED.

#### F-M15 · `engine:scripts/export_frontend_simulated.py:274` · unused-bloat

The render-publishing loop only ever copies files in (shutil.copy2) and never prunes, so nightly re-ranking of the top-25 'most consequential' set strands old renders: 51 orphan files totaling 65,072,174 bytes now sit under modes/simulated/ referenced by neither the payload nor any page.

Evidence:
```
Lines 271-297: demo = ranked[:args.max_renders]; for each, shutil.copy2 into FRONTEND/modes/simulated/<stem>/ — no deletion pass anywhere. Cross-checking every file under modes/simulated/ against (a) all 100 payload html/png refs, (b) all static page refs, (c) the dynamic joins (dialects.json items[].render; provenance.json translation_cases indices -> urgency_downgrades_20260707T1/index_NN.html): 51 unreferenced files, 65,072,174 bytes, e.g. modes/simulated/pairs_20260707T215921Z/index_14.png (2,391,433 B), pairs_20260707T023656Z/index_11.html (770,423 B), whole dirs pairs_20260707T023656Z/023704Z/023706Z and pairs_20260712T051903Z with zero live references. Frontend CLAUDE.md forbids hand-editing modes/, so pruning must live in this exporter.
```
Proposed fix:
```diff
--- a/scripts/export_frontend_simulated.py
+++ b/scripts/export_frontend_simulated.py
@@ after line 315 (end of copy loop, before the _render pop)
+# prune renders this export no longer references (pairs_* dirs only; other
+# modes/simulated content — preview.html/png, urgency_downgrades_*, featured_*,
+# dialects_* — is published by other flows)
+published = {FRONTEND / e[k] for e in scenarios for k in ("html", "png") if e.get(k)}
+published |= {FRONTEND / rec[k] for e in scenarios for rec in e["models"].values()
+              for k in ("html", "png") if rec.get(k)}
+for f in (FRONTEND / "modes/simulated").glob("pairs_*/*"):
+    if f.is_file() and f not in published:
+        f.unlink()
+        print(f"  pruned stale render {f.relative_to(FRONTEND)}")
```
Verifier correction: Finding stands as stated (severity medium, 51 orphans / 65,072,174 bytes under modes/simulated/, no prune pass in export_frontend_simulated.py and no guard elsewhere), with two corrections. (1) Mechanism is broader than nightly re-ranking: whole batch stamps dropped from --stamps orphan entire dirs (e.g. pairs_20260707T023656Z, pairs_20260712T051903Z), and later --no-pngs adoption stranded previously copied PNGs (all 17 orphan .png files are from 2026-07-07 stamps). (2) The proposed fix must not prune solely against the current export's published set: static pages hard-link renders inside pairs_* dirs (index.html line 323 and start-here/index.html lines 189/205 -> modes/simulated/pairs_20260707T171223Z/index_12.html and index_49.html), which are protected today only because the current ranking happens to include them. A safe prune should (a) union the published set with a static allowlist scanned from page hrefs (grep modes/simulated/pairs_ across *.html) or an explicit keep-list argument, (b) also clean now-empty pairs_* dirs, and (c) ideally print a summary so an operator sees what a re-rank is about to remove. Placing the prune in the exporter is correct: frontend CLAUDE.md forbids hand-editing modes/ (engine-generated, replaced wholesale).
Found by: global-sweep. Verified: CONFIRMED.

#### F-M16 · `engine:scripts/export_frontend_simulated.py:285` · mismatched-keys

scenario.html's entire 'Circuit diff: what the swap changed' view is gated on m.diff_html, but the exporter never emits diff_html: the render-copy loop only handles index_NN.{html,png}, even though the engine renders index_NN_diff.html for every 2panel pair and records it in batch_summary outputs.diff_html; so the diff embed is dead and the circuit_diff counts shipped in 520/751 scenarios are never displayed anywhere.

Evidence:
```
Exporter L285-293: `for key in ("html", "png"): ... src = base_dir / f"index_{index:02d}.{key}" ... e[key] = rel` — no diff variant; COMPAT (L59-62) and build_model_obj (L142-171) carry `circuit_diff` counts but no diff_html. Engine writer medlang_circuits/batch_eval.py L596-598: `diff_html = out_dir / f"index_{index:02d}_diff.html" ... render_panels_html(diff_panels, str(diff_html), ...)` and L628: `"outputs": {..., "diff_html": str(diff_html), ...}`. Consumer scenario.html L499-506: `if(m.diff_html){ ... +(m.circuit_diff?(' · '+m.circuit_diff.shared_features+' shared · '+m.circuit_diff.unique_to_a+' only clinical · '+m.circuit_diff.unique_to_b+' only patient'):'')); embedBlock(card,m.diff_html,...)}`. Payload instance: 0 of 751 scenarios have diff_html (top level or any models[<id>]); circuit_diff is a dict {shared_features,unique_to_a,unique_to_b} on 520 gemma entries and is thus fetched but never rendered.
```
Proposed fix:
```diff
--- a/scripts/export_frontend_simulated.py
+++ b/scripts/export_frontend_simulated.py
@@ -285,9 +285,11 @@
-        for key in ("html", "png"):
+        for key in ("html", "png", "diff_html"):
             if args.no_pngs and key == "png":
                 continue
-            src = base_dir / f"index_{index:02d}.{key}"
+            name = (f"index_{index:02d}_diff.html" if key == "diff_html"
+                    else f"index_{index:02d}.{key}")
+            src = base_dir / name
             if src.is_file():
(e[key]=rel and the models[BASE_MODEL][key]=rel mirror lines already use `key` as the payload field name, so `diff_html` flows through unchanged; alternatively, if diff renders are intentionally unpublished, delete the dead L499-507 block in scenario.html so circuit_diff stops being shipped for a view that cannot render)
```
Verifier correction: Two refinements, neither changing the verdict. (1) "never displayed anywhere" is slightly overstated: start-here/index.html L394 hand-transcribes scenario 48's circuit_diff counts as static text (panel 5 source note); no page renders the payload field at runtime, which is the substantive claim. (2) The proposed exporter patch is safe but narrower than it may appear: renders are copied only for the --max-renders cap (25 published html renders in the current payload) and only for the base model, so the fix revives the diff view for at most those 25 scenarios; the other ~495 circuit_diff dicts remain shipped-but-unrendered because the counts line sits inside the m.diff_html gate in scenario.html; to surface all 520 counts, move the counts text outside that gate (or accept counts-without-embed). Also note the fix roughly doubles published render weight per scenario, which the exporter's own --no-pngs help text suggests the owner cares about; if diff renders are intentionally unpublished, the alternative (deleting scenario.html L499-507) must also update the L512 condition (!m.html&&!m.diff_html) to stay consistent.
Found by: sim-scenarios-detail,global-sweep,sim-scenarios-index. Verified: CONFIRMED.

#### F-M17 · `engine:scripts/export_frontend_simulated.py:345` · mismatched-keys

models_meta is built by iterating the hardcoded MODELS constant, not the models actually merged, so the expanded-matrix logits models the live trigger measures (llama-3.2-3b, olmo-2-1b, medgemma-4b-it, gemma-2-2b-it) can never get a models_meta entry: exported with --models their measurements land in scenario.models but no selector chip exists (the frontend selector is driven solely by models_meta), and with the default --models their trace dirs are skipped entirely while urgency_shift ingests them - the two published artifacts silently disagree on the model set.

Evidence:
```
export_frontend_simulated.py:48 `MODELS = ["gemma-2-2b", "gemma-3-4b-it", "qwen3-4b", "qwen3-1.7b"]`; :345-346 `for m in MODELS\n    if any(m in s.get("models", {}) for s in scenarios)` (WANT_MODELS from --models is used only for reading dirs at :189). Live trigger .github/trigger/logits-eval.json fires `"models":"llama-3.2-3b,olmo-2-1b,medgemma-4b-it,gemma-2-2b-it"` with `"commit_outputs":"true"`. Live divergence in the frontend worktree: data/urgency_shift.json summary.per_model keys = [gemma-2-2b, gemma-2-2b-it, gemma-3-4b-it, llama-3.2-3b, medgemma-4b-it, olmo-2-1b, qwen3-1.7b, qwen3-4b] while data/simulated_scenarios.json models_meta ids = [gemma-2-2b, gemma-3-4b-it, qwen3-4b, qwen3-1.7b]. Frontend CLAUDE.md: "payload.models_meta drives the model-selector chips" and urgency rows join on (batch, batch_index, model) - rows for the four unlisted models can never join a visible model.
```
Proposed fix:
```diff
Build models_meta from the union of the registry order and what was actually merged:
-    for m in MODELS
+    for m in dict.fromkeys([*MODELS, *WANT_MODELS])
     if any(m in s.get("models", {}) for s in scenarios)
(LABELS.get(m, m) already falls back to the id for unlabeled models; FEATURED/QK membership stays correct because the new models have neither transcoders nor LoRSA.)
```
Verifier correction: One nuance to the summary: in the currently published payload only the default---models branch is live; the four logits models are absent from scenario.models as well as models_meta (their trace dirs were skipped at merge time), while urgency_shift.py independently globbed their trace_out part files. The "measurements land in scenario.models but no selector chip exists" branch is latent, materializing on the first export invoked with the expanded --models list. Severity medium stands: the two published artifacts disagree on the model set today, and the scenario page's aggregate urgency line (built from urgency_shift.json summary "across models") already counts models that have no chip and no joinable rows.
Found by: wf-logits. Verified: CONFIRMED.

#### F-M18 · `engine:scripts/export_jlens_depth.py:46` · silent-failure

load_summary hardcodes jlens_summary.part_01.json, so any chunked lens run (offset>0 -> part_02+) is silently dropped from the site's unit rows, examples, and translation split; counts under-report with no error.

Evidence:
```
L45-47: `path = Path("trace_out") / f"{stem}__jlens_{model}" / "jlens_summary.part_01.json"`. jlens_readout.py deliberately emits `jlens_summary.part_{offset+1:02d}.json` for chunked fires (L352, workflow input `offset: "Skip the first N pairs (chunking; part number = offset+1)"`), and the repo convention (CLAUDE.md, mirrored from batch_summary) is that "all consumers must glob" part files. build_block's docstring claims "one batch, all pairs" but a two-chunk batch yields a partial block; translation_split's `except OSError: continue` (L138-140) even hides the case where part_01 is absent entirely but later parts exist.
```
Proposed fix:
```
Glob and merge parts:
```
def load_summary(stem, model="gemma-2-2b"):
    d = Path("trace_out") / f"{stem}__jlens_{model}"
    parts = sorted(d.glob("jlens_summary.part_*.json"))
    if not parts:
        raise OSError(f"no jlens_summary parts under {d}")
    merged, results = None, {}
    for p in parts:
        s = json.loads(p.read_text(encoding="utf-8"))
        merged = merged or s
        for r in s.get("results", []):
            results[r["index"]] = r   # later parts win on re-runs
    merged["results"] = [results[k] for k in sorted(results)]
    return merged, ";".join(str(p) for p in parts)
```
```
Verifier correction: Two precision corrections, neither changing the verdict. (1) The except OSError: continue in translation_split is at lines 136-137, not 138-140; and the failure mode it hides is narrower than implied; if part_01 is absent but later parts exist, translation_split silently drops the stem, but build_block for that same stem raises FileNotFoundError uncaught by main's except ValueError, so that specific scenario crashes loudly rather than publishing; the truly silent case is parts >01 existing alongside part_01. (2) The defect is latent: every source path in the committed data/jlens_depth.json is a part_01 file, so all landed lens runs to date were single-chunk and no published number is currently wrong; medium severity as a silent-failure trap is defensible, but frame it as a latent under-count, not an active one. Fix nit: the proposed raise OSError on zero parts is not caught by main (which only catches ValueError for the exit-3 refusal path), so it fails with a traceback instead of the polished refused: message; either catch OSError in main or raise ValueError instead.
Found by: wf-new-analyses. Verified: CONFIRMED.

#### F-M19 · `engine:scripts/export_jlens_depth.py:77` · mismatched-keys

patch_join conflates the part number (chunk 1-based START offset) with the pair index; the exemplar only resolves when its index happens to be a chunk start, and a stale chunk file with that number can silently supply an outdated grid over a fresh consolidated part_01.

Evidence:
```
L77: `path = Path("trace_out") / f"{stem}__patch" / f"batch_summary.part_{index:02d}.json"`. Per the checkpoint convention (activation_patching.yml L192-195: "part_NN = 1-based start offset ... all consumers can glob batch_summary*.json"), part_01 from an offsets=0,limit=13 run contains pairs 1-13; `--exemplar-index 4` then opens the nonexistent part_04 (unhandled FileNotFoundError), while an index that matches a leftover chunk start (e.g. a superseded part_06 from an older grid run sitting next to a fresh full part_01) is read silently even though part_01 holds the current measurement for that pair.
```
Proposed fix:
```
Glob all parts and select by result index, newest-part-wins:
```
hits = []
for path in sorted((Path("trace_out") / f"{stem}__patch").glob("batch_summary.part_*.json")):
    summary = json.loads(path.read_text(encoding="utf-8"))
    hits += [(r, path) for r in summary["results"] if r["index"] == index]
if not hits:
    raise ValueError(f"pair {index}: no patching part contains it")
result, path = hits[-1]
```
```
Verifier correction: The finding stands, but the proposed_fix is unsafe as written: sorted() on filenames plus hits[-1] is highest-part-number-wins, not 'newest-part-wins'; in the finding's own stale scenario (fresh consolidated part_01 covering pairs 1-13 beside a leftover part_06), pair 6 appears in both and hits[-1] selects the STALE part_06. Corrected fix: glob trace_out/<stem>__patch/batch_summary.part_*.json, collect every result with r['index'] == index, and (a) raise ValueError (not FileNotFoundError) when none is found so main()'s exit-3 refusal path handles it, (b) resolve duplicates by file mtime (newest file wins) or hard-error when duplicate measurements disagree; overlapping parts from a single run (current trigger: offsets 12,13,14,15, limit 4) legitimately contain the same pair with identical data, so exact duplicates must not error. Also update tests/test_export_jlens_depth.py's _write_patch_part helper, which currently encodes the same part-number/index conflation and would otherwise keep masking regressions. The fix breaks no other consumer: patch_join is called only from build_payload in the same file, and patch_aggregate.py already uses the glob-and-join pattern.
Found by: wf-new-analyses. Verified: CONFIRMED.

#### F-M20 · `engine:scripts/fire_trigger.py:433` · silent-failure

git_publish retries the push 5 times without ever rebasing, so the documented common failure (non-fast-forward after CI committed to the branch; 'expect the two to interleave, and git pull --rebase before pushing') fails identically on every attempt; the fire ends exit-1 with the trigger file and an active journal entry committed locally but never pushed; CI never fires, yet the phantom entry occupies a queue slot for up to 8h and counts as in-flight spend.

Evidence:
```
Lines 429-437: `for attempt, delay in enumerate((0,) + tuple(backoff)): ... proc = _git(repo, "push", "-u", "origin", branch)` — no fetch/rebase between attempts. Contrast circuit_trace_evaluation.yml:315 and scenario_generation.yml:306-311, both of which rebase inside the retry loop. cmd_fire has already written trigger file + journal + dashboard (lines 567-570) before publish and rolls nothing back on failure.
```
Proposed fix:
```diff
--- a/scripts/fire_trigger.py
+++ b/scripts/fire_trigger.py
@@ -430,6 +430,9 @@
         if delay:
             print(f"push retry {attempt}/{len(backoff)} in {delay}s", file=sys.stderr)
             time.sleep(delay)
+        pull = _git(repo, "pull", "--rebase", "origin", branch)
+        if pull.returncode != 0:
+            print(f"git pull --rebase failed: {pull.stderr.strip()}", file=sys.stderr)
         proc = _git(repo, "push", "-u", "origin", branch)
```
Verifier correction: Corrected statement: git_publish (scripts/fire_trigger.py:429-437) retries the push 5 times without ever rebasing, so the documented common failure; non-fast-forward after CI committed trace outputs to the same branch; fails identically on every attempt. The failure is loud at fire time (stderr 'fire written locally but git publish failed - resolve by hand', exit 1), but cmd_fire has already written the trigger file, journal entry, and dashboard queue (lines 567-570) and rolls nothing back: CI never fires, yet unless the operator manually resolves, the phantom entry occupies a queue slot and (for paid triggers) counts as in-flight max_spend for up to 8h (DEFAULT_EXPIRE_HOURS). Corrected fix; rebase only after a failed push, and abort a conflicted rebase so the checkout is never left mid-rebase (mirroring circuit_trace_evaluation.yml:315-319):

--- a/scripts/fire_trigger.py
+++ b/scripts/fire_trigger.py
@@ -430,10 +430,17 @@
         if delay:
             print(f"push retry {attempt}/{len(backoff)} in {delay}s", file=sys.stderr)
             time.sleep(delay)
+            # The documented common failure is non-fast-forward after CI
+            # committed to this branch; rebase before retrying, and never
+            # leave the checkout mid-rebase on conflict.
+            pull = _git(repo, "pull", "--rebase", "origin", branch)
+            if pull.returncode != 0:
+                _git(repo, "rebase", "--abort")
+                print(f"git pull --rebase failed: {pull.stderr.strip()}", file=sys.stderr)
         proc = _git(repo, "push", "-u", "origin", branch)
         if proc.returncode == 0:
             return True
         print(f"git push failed: {proc.stderr.strip()}", file=sys.stderr)
     return False

(Placing the pull under `if delay:` keeps the first attempt pull-free, so firing onto a branch with no upstream yet; the `push -u` new-branch case; does not emit a spurious 'couldn't find remote ref' failure. Add an offline regression test with a stubbed _git per repo convention.)
Found by: wf-archive-ops. Verified: CONFIRMED.

#### F-M21 · `engine:scripts/fire_trigger.py:467` · silent-failure

The queue and budget guards read the local journal with no git sync and no file lock: a stale checkout (another session's fire already pushed) or two concurrent local fires both pass the 2-active check, producing exactly the third-push silent eviction the script exists to prevent; concurrently, save_journal's whole-file rewrite (line 224/569) can erase the other fire's entry, undercounting in-flight paid spend.

Evidence:
```
cmd_fire: `entries = load_journal(journal_path)` (line 467) — the only git operation in the fire path is git_publish at line 574, after all guard decisions and after save_journal (line 569) rewrites the whole file via os.replace. Nothing fetches origin before the read and there is no flock, so the guard window spans params validation, settle check, budget check, and file writes. load_journal's own docstring (lines 191-196) acknowledges 'the next whole-file rewrite would erase it'.
```
Proposed fix:
```diff
--- a/scripts/fire_trigger.py
+++ b/scripts/fire_trigger.py
@@ -465,6 +465,11 @@
     # 3. Queue guard: one running + one pending; a third push evicts the pending run.
     journal_path = repo / JOURNAL_RELPATH
+    if not args.no_git:
+        sync = _git(repo, "pull", "--rebase", "--autostash")
+        if sync.returncode != 0:
+            print(f"refused: cannot sync journal before the queue check: {sync.stderr.strip()}", file=sys.stderr)
+            return 1
     entries = load_journal(journal_path)
Additionally hold an exclusive fcntl.flock on journal_path + '.lock' from load_journal through save_journal to serialize concurrent local fires.
```
Verifier correction: Corrected statement: cmd_fire evaluates all guards (queue, settle, budget) on a journal snapshot read at scripts/fire_trigger.py:467 with no prior git sync and no file lock, and save_journal (218-225, called at 569) is an unserialized read-modify-write of the whole file. Two concurrent local fires in the same checkout can both pass the 2-active check and the later save erases the earlier fire's journal entry; silently dropping a paid entry's in-flight max_spend from all subsequent budget checks. A stale checkout (another session's fire already pushed to the same branch) also passes the guards on undercounted state, but does NOT silently evict by itself: git_publish's plain push fails non-fast-forward, cmd_fire exits 1 with an explicit message, and CI never sees the unpushed trigger change; the eviction/double-count hazard is the guard-bypassing manual recovery (pull --rebase && push per the repo's own standing advice), which the script neither blocks nor warns about. Severity: low-to-medium (medium is defensible for the paid-spend undercount); the documented single-writer rule (ops/README.md) and the Routine prompt's mandatory pull --rebase (docs/routine_standing_prompt.md:29) make both scenarios process violations, but the script's stated purpose is mechanical enforcement against exactly such errors. Corrected fix: the proposed `git pull --rebase --autostash` before the journal read is directionally right and fails closed, but it must be gated on `not args.no_git and not args.dry_run` (as written, --dry-run; documented 'write nothing'; would mutate the checkout); note it will also hard-refuse fires from detached-HEAD/no-upstream/dirty-conflict checkouts (acceptable fail-closed). The fcntl.flock on journal_path + '.lock' held from load through save correctly serializes same-checkout races (its proper scope; cross-checkout is already backstopped by the non-FF push); also, print an explicit warning on git-publish failure that recovery must re-run fire_trigger.py rather than hand-pushing the rebased trigger change. Neither change affects cmd_resolve/cmd_status or any other consumer.
Found by: wf-archive-ops. Verified: CONFIRMED.

#### F-M22 · `engine:scripts/jlens_readout.py:294` · silent-failure

A pair with an empty/missing target_clinical_token is silently classified patient_depth_class="absent" (parse_status "ok") instead of being recorded as unmeasurable, corrupting the site's "never formed" counts.

Evidence:
```
build_result L294: `target = pair.get("target_clinical_token") or ""` with no guard; target_variants("") returns set() (L112-114) so target_match always returns None (L134: `if not isinstance(token_str, str) or not variants: return None`), every target_rank is None, and classify() L275-277 yields "absent" for a non-empty profile — a fabricated measurement. Both sibling measurers guard this exact case: activation_patch.py L429-434 ("empty/untokenizable target: nothing measurable; keep the placeholder block") and logits_eval.py L103-111 (probabilities None). Downstream, export_jlens_depth.build_block counts it in `counts["absent"]` for the simulated-scenarios depth badges, and jlens_insights.classify feeds it into the taxonomy.
```
Proposed fix:
```
In build_result (or better, in main() before the two hosted calls):
```
target = pair.get("target_clinical_token") or ""
if not target.strip():
    return {"index": index,
            "prompts": {"clinical": pair["top_prompt"], "patient": pair["bottom_prompt"]},
            "target_token": None, "depth": {"clinical": [], "patient": []},
            "parse_status": {"clinical": "no target", "patient": "no target"},
            "first_layer": {"clinical": None, "patient": None},
            "last_layer_rank": {"clinical": None, "patient": None},
            "patient_depth_class": None}
```
(class None is already handled by classify()'s `if not pat_profile` arm and skipped by jlens_insights.collect's parse_status filter).
```
Verifier correction: Corrections to the finding, not the verdict: (1) The corruption is latent, not live; the currently published data/jlens_depth.json blocks (pairs_20260713T050939Z, pairs_20260712T163501Z, pairs_20260712T051903Z, pairs_20260711T131752Z, pairs_20260711T051145Z, urgency_downgrades_20260707T1) contain zero empty-target pairs, so no site number is wrong today; it fires the first time a set containing the 6 missing-target pairs is lens-traced. (2) In jlens_insights the fabricated row lands in the "unreadable" taxonomy class (clin_formed is also None, checked before pat_formed in classify), not "capture"; it still inflates the formation-census denominator and carries endpoint_class "absent". (3) Fix nit: with the proposed placeholder, export_jlens_depth.build_block folds patient_depth_class=None into counts under a JSON "null" key (pre-existing behavior for unparsed rows); consider also skipping None-class rows in build_block. The fix otherwise breaks no consumer; jlens_insights skips per-side status "no target" (any value != "ok"), and main()'s per-pair print handles the dict shape.
Found by: wf-new-analyses. Verified: CONFIRMED.

#### F-M23 · `engine:scripts/jlens_readout.py:370` · silent-failure

A mid-batch persistent 5xx raises without writing a partial summary, and the workflow has no upload-artifact step; every measured pair of the chunk is unrecorded (jlens_steer.py already writes a partial file for this exact case).

Evidence:
```
L363-370: `except RuntimeError as err: ... if results or responses: raise` — the raise discards `results` (nothing on disk unless --save-raw). jlens_steer.py L142-151 fixed the same hole after real data loss: "abort loudly, but never discard completed items again (the 20:43 grid run lost 10 measured items this way)" and writes `jsteer_summary.{part}.json` with `"partial": True` before re-raising; the always()-gated commit step (jlens_readout.yml L193-204) would then land it. jlens_readout.yml also has no `actions/upload-artifact` step (activation_patching.yml L262-268 does), so nothing survives the runner.
```
Proposed fix:
```
Mirror the steer contract before the raise:
```
if results or responses:
    if results:
        partial = build_summary(args.model, results, start_index=args.offset + 1,
                                topn=args.topn, lens_type=args.lens_type)
        partial["partial"] = True
        partial["_"] = f"partial: aborted mid-run ({err})"
        (out_dir / f"jlens_summary.{part}.json").write_text(
            json.dumps(partial, indent=1) + "\n", encoding="utf-8")
    raise
```
and add an `if: always()` upload-artifact step for $OUT_DIR to jlens_readout.yml.
```
Verifier correction: Two citation refinements, no substantive change: (1) the always()-gated commit step in jlens_readout.yml spans L193-220, not L193-204, and it only runs when commit_outputs=='true'; so the partial-write half of the fix rescues data only on commit_outputs=true runs, and the upload-artifact half is what covers commit_outputs=false runs; both halves are needed. (2) The fix inherits a pre-existing jsteer caveat worth noting in its docstring/comment: no consumer (jlens_insights.py, export_jlens_depth.py, translation_scale.py) checks the "partial" flag, so a partial part file that lands and is never re-run at the same offset will be consumed as if complete; acceptable per the established jsteer contract, but the fix should keep the "partial": True and "_" marker keys exactly as proposed so the condition stays visible in the committed artifact.
Found by: wf-new-analyses. Verified: CONFIRMED.

#### F-M24 · `engine:scripts/logits_eval.py:158` · other

The logits backend records a top-10 predictive_spread while the tracer records top-5 (TOP_K_SPREAD_DEFAULT), and the workflow never passes --topk; urgency_shift's expected_tier/coverage math normalizes over total spread mass, so the two backends are scored against systematically different denominators - a quiet cross-backend bias in the published tier metrics, confirmed live in the frontend payload.

Evidence:
```
scripts/logits_eval.py:158: `parser.add_argument("--topk", type=int, default=10, help="spread size per phrasing")`; the workflow measure step (logits_evaluation.yml:155-156) passes only --pairs/--model/--out/--limit/--offset. Tracer side: medlang_circuits/targets.py:37 `TOP_K_SPREAD_DEFAULT = 5` and batch_eval.py:625 `"predictive_spread": {role: logit_spread(g) ...}` (default k=5). Consumer: scripts/urgency_shift.py:67-78 computes coverage as tier-assigned mass / TOTAL spread mass and nulls expected_tier below --min-coverage 0.3, so spread depth changes both the gate and the weighting. Live confirmation from /home/user/audit-wb/patientwords/data/simulated_scenarios.json: spread_clinical lengths are {1..5} for gemma-2-2b (hosted) but {8,9,10} for gemma-3-4b-it, qwen3-4b, qwen3-1.7b (logits).
```
Proposed fix:
```diff
Align the default with the tracer's spread size:
-    parser.add_argument("--topk", type=int, default=10, help="spread size per phrasing")
+    # match medlang_circuits.targets.TOP_K_SPREAD_DEFAULT so cross-backend
+    # coverage/expected-tier math sees the same spread depth
+    parser.add_argument("--topk", type=int, default=5, help="spread size per phrasing")
(For the already-landed 10-deep part files, also cap spreads at a common depth in urgency_shift.py's clean(): `(sp.get(side) or [])[:5]` - otherwise the historical logits rows keep the deeper denominator.)
```
Verifier correction: Finding stands as stated (file/line/severity correct). Two corrections to the proposed_fix: (1) The retroactive cap must not live only in urgency_shift.py's clean(); that covers only the trace_out/* ingestion path. The site-payload fallback (urgency_shift.py:199-203) feeds the same 10-deep spreads from data/simulated_scenarios.json into add(), and on a checkout without trace_out/ that fallback is the primary source. Cap at a common depth inside add() or expected_tier (e.g. spread = (spread or [])[:5]) so both ingestion paths and all historical rows share one denominator; spreads are rank-sorted on both backends (torch.topk / ranked logit_spread), so [:5] is the true top-5. (2) Minor tradeoff to document: paired_stats.py:213-218 uses the patient spread's minimum probability as a censoring floor; a top-5 spread raises that floor, weakening (but keeping conservative) the censored penalty upper bounds for future logits runs. Nothing else consumes spread depth: translation_scale.py and the exporter's top() use index 0 only, and the frontend spread display renders whatever array length arrives. Also note top-1 flip/downgrade metrics are unaffected; the bias is confined to expected_tier/coverage/tier_shift and the per-model aggregates built from them.
Found by: wf-logits. Verified: CONFIRMED.

#### F-M25 · `engine:scripts/logits_eval.py:197` · silent-failure

logits_eval.py writes batch_summary only after the full loop finishes, so a CI timeout or OOM-kill discards every measured pair; the workflow's always()-guarded commit step then greens out with 'No summary to commit', salvaging nothing - unlike the tracer path whose per-pair checkpointing this workflow's salvage step was copied from.

Evidence:
```
scripts/logits_eval.py:187-200: the measure loop appends to `results` with no intermediate write; only after it completes does `summary_path.write_text(json.dumps(build_summary(...)...)` run. Contrast medlang_circuits/batch_eval.py:985-986/1061-1062: "``batch_summary.json`` is checkpointed after every pair - ... a crash, cancellation, or CI timeout must not lose the pairs already traced" / `with open(summary_path, "w", ...) as f:  # checkpoint per pair`. The workflow's salvage step (logits_evaluation.yml:159-165) runs `if: ${{ always() && ... }}` but exits green on the missing file: `if [ ! -f "$OUT_DIR/batch_summary.$PART.json" ]; then echo "No summary to commit"; exit 0; fi`. This failure mode is documented as having actually occurred: tests/test_logits_registry.py:86-88 "Regression for the run-14 timeout: a 119-pair gemma-3 batch cannot finish inside the 4h CI timeout" - that leg ran up to timeout-minutes: 240 (yml:110) and landed zero of its finished measurements.
```
Proposed fix:
```diff
In scripts/logits_eval.py main(), move the summary write inside the loop (mirroring run_batch):
-    start_index = args.offset + 1  # global 1-based join key, matching the trace path
-    results = []
-    for i, pair in enumerate(pairs, start=start_index):
-        results.append(build_result(i, pair, tokenizer, measure_fn, args.topk))
+    start_index = args.offset + 1  # global 1-based join key, matching the trace path
+    out = Path(args.out)
+    out.mkdir(parents=True, exist_ok=True)
+    summary_path = out / f"batch_summary.part_{start_index:02d}.json"
+    revision = getattr(model.config, "_commit_hash", None)
+    results = []
+    for i, pair in enumerate(pairs, start=start_index):
+        results.append(build_result(i, pair, tokenizer, measure_fn, args.topk))
+        summary_path.write_text(  # checkpoint per pair, like batch_eval.run_batch
+            json.dumps(build_summary(model_id, hf_id, results, start_index,
+                                     revision=revision), indent=2) + "\n",
+            encoding="utf-8")
and delete the now-redundant end-of-run mkdir/write (keep the final print). The existing always()-commit step then salvages partial chunks exactly as the tracer path does.
```
Verifier correction: Finding accurate as filed (cited line 197 is the write; the unguarded loop is 188-192). One refinement to the proposed_fix before applying: the per-pair `summary_path.write_text(...)` should be atomic; write to a sibling temp file and `os.replace` it over summary_path; otherwise a mid-write SIGKILL leaves truncated JSON that the always() salvage step WILL commit (it only checks file existence), crashing every downstream json.load (urgency_shift.py collector, export_frontend_simulated.py). run_batch shares this non-atomicity, so plain write_text achieves parity, but atomic replace is the correct form when the file is explicitly intended to be salvaged after kills. Also note: deleting the end-of-run write means an empty pairs slice writes no file at all; this matches run_batch behavior and the salvage step handles it cleanly, so it is acceptable. Per-pair rewrite cost is negligible (~1 min/pair CPU inference dominates).
Found by: wf-logits. Verified: CONFIRMED.

#### F-M26 · `engine:scripts/retrace_consistency.py:113` · other

retrace_consistency.py writes only ops/retrace_consistency.json and has no --site publish path, yet methods.html and simulated-scenarios/index.html both fetch data/retrace_consistency.json; the site copy is an unautomated manual copy that will silently go stale on the next retrace collection.

Evidence:
```
`parser.add_argument("--out", default="ops/retrace_consistency.json")` with no site-copy code, unlike drift_sentinel.py lines 96-97/112-115 (`--site ... site_copy = Path(args.site) / "data" / "drift_series.json"`), study_timeline.py lines 116-119, and export_jlens_depth.py lines 275-278. Today ops and site copies are byte-identical (pairs_retraced=68), but docs/routine_standing_prompt.md automates only the drift sentinel's --site copy; nothing copies retrace output. Two pages plus the methods prose ('Zero repeat variation was observed through July 14, 2026') depend on the site copy staying current.
```
Proposed fix:
```diff
Mirror drift_sentinel's site copy:
     parser.add_argument("--out", default="ops/retrace_consistency.json")
+    parser.add_argument("--site", default=None,
+                        help="site repo root; also writes data/retrace_consistency.json there")
...
     out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
+    if args.site:
+        site_copy = Path(args.site) / "data" / "retrace_consistency.json"
+        site_copy.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
+        print(f"site copy -> {site_copy}")
```
Verifier correction: Finding is accurate as stated (severity medium is fair: public methods-page repeatability claim can silently go stale, but data is currently consistent). One completeness note on the proposed_fix: adding an optional --site flag is safe (defaults to None; ops output and payload shape unchanged; page JS reads the same keys, so no consumer breaks), but it is insufficient alone; nothing currently invokes retrace collection with --site, so docs/routine_standing_prompt.md must also gain a step to run `python scripts/retrace_consistency.py --site ../patientwords` after retrace-bearing trace runs land, mirroring the drift_sentinel step at line 108. Without the prompt update the flag exists but the site copy still never refreshes automatically.
Found by: methods-sentinel-bundle. Verified: CONFIRMED.

#### F-M27 · `engine:scripts/specialty_breakdown.py:75` · silent-failure

specialty_breakdown.py never writes the site copy the technical page fetches: it writes only ops/specialty_breakdown.json, so data/specialty_breakdown.json goes silently stale on every regen (manual-copy gap, same class as the accepted archive_export rename gap).

Evidence:
```
parser.add_argument("--out", default="ops/specialty_breakdown.json") — and main() uses args.site only to READ inputs: scenarios = json.loads((site / "data" / "simulated_scenarios.json").read_text(...)); the only write is out.write_text(...). Docstring L6-8 says 'Owner-facing decision data (ops/, not the site)' and the payload '_' says 'nothing here publishes without pre-registration' — yet technical/index.html:1068 fetches ../data/specialty_breakdown.json and renders it. Today ops copy == site copy (verified byte-equal via python3), but docs/routine_standing_prompt.md has explicit --site republish steps for jlens_insights.py and translation_scale.py and none for this script.
```
Proposed fix:
```diff
--- a/scripts/specialty_breakdown.py
+++ b/scripts/specialty_breakdown.py
@@ (end of main, after the ops write)
     out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
     print(f"specialty breakdown: {len(shown)} specialties with cells >= n{args.min_n} -> {out}")
+    site_copy = site / "data" / "specialty_breakdown.json"
+    site_copy.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
+    print(f"site copy -> {site_copy}")
Also update the docstring ('ops/, not the site' → 'ops/ plus the site copy the technical page reads') and add the step to docs/routine_standing_prompt.md — or, if the owner intends ops-only, remove the fetch+#sp-block from technical/index.html.
```
Verifier correction: Finding stands as filed with one strengthening and two fix refinements. Strengthening: the finder's either/or closing ('or, if the owner intends ops-only, remove the fetch') can be dropped; ops/dashboard.json:297 records the owner decision '(2) specialty breakdown published as exploratory fold on model-evaluations', so the site publication is sanctioned and adding the site write is the correct branch. Fix refinements: (a) prefer the existing jlens_insights.py pattern (scripts/jlens_insights.py L257-271: optional --site arg gating the site-copy write) over an unconditional write, for consistency with the repo's established republish convention; though an unconditional write is safe here since the script already hard-requires the site checkout to read its inputs; (b) when adding the step to docs/routine_standing_prompt.md, keep it in the data-republish section (data-payload commits are sanctioned for the Routine; page-HTML edits are not); (c) optionally add data/specialty_breakdown.json to the frontend CLAUDE.md data-contracts list, which currently omits it. Docstring lines 6-8 and the payload '_' sentence ('nothing here publishes without pre-registration') should be updated to reflect the 'published as exploratory, owner-sanctioned' status.
Found by: technical-bundle. Verified: CONFIRMED.

#### F-M28 · `engine:scripts/study_timeline.py:39` · other

batch_entries() globs data/simulated/*.report.json, which also matches *.mitigation.report.json translation-cost sidecars and timestamped zero-cost alias/drift sidecars, so the public timeline strip draws 42 dots while its aria-label and visible summary announce totals.generation_batches = 39, counts three mitigation (translation-panel) spends as 'generation batches', and folds their $0.126 into 'generation $11.71 total'; mislabeling translation spend as generation spend on a page whose hard rule is that every number traces accurately.

Evidence:
```
data/timeline.json: 42 batch entries, all with utc, vs totals.generation_batches 39 and totals.generation_usd 11.7057. The three cost>0 mitigation entries (pairs_20260711T051145Z.mitigation $0.02, pairs_20260711T051145Z_txopus.mitigation $0.075, pairs_20260711T051145Z_txplacebo.mitigation $0.031; accepted null) pass the cost>0 filter at study_timeline.py:89-90 and thus inflate generation_batches and generation_usd by $0.126; stem.split('_')[0] at :45 assigns them kind 'pairs' so simulated-scenarios/index.html:434-438 draws them as large hollow 'Tier A pairs' dots (the '.mitigation' suffix also fails the tierb regex at :77 despite the base batch being Tier B era). The zero-cost alias arms (…_txopus, …_txplacebo) and drift_sentinel (kind 'drift') survive the ts-null guard at :49 because they carry timestamps, so they are drawn but not counted — hence 42 dots under a '39 generation batches' aria-label (simulated-scenarios/index.html:414) and summary line (:458).
```
Proposed fix:
```diff
In batch_entries(), before parsing each sidecar add:
    if p.endswith(".mitigation.report.json"):
        continue  # translation-panel cost sidecars, not generation events
and extend the existing alias guard at line 49 to also skip timestamped non-generation stubs:
-        if ts is None and cost in (0, 0.0):
+        if cost in (0, 0.0) and d.get("accepted") is None:
            continue  # alias/drift sidecars carry no generation event
After this the batches array equals gen_batches for counting purposes and the strip's dot count matches totals.generation_batches; if the owner wants mitigation/drift events kept on the strip, instead emit them with an explicit kind ('mitigation'/'drift'), exclude them from gen_batches via `not b['batch'].endswith('.mitigation')`, and have the page style/legend them separately rather than as pairs dots.
```
Verifier correction: Finding stands as written with one evidence update: the published site copy (generated_utc 2026-07-14T13:42:38Z) predates the latest sidecars, so its numbers are 42 dots vs 39 counted / $11.7057. At the audited engine HEAD (3447b50) a regeneration would keep 46 entries vs gen_batches 43 / $12.3566; same defect, same 3 mitigation entries and $0.126 mislabeled, slightly larger dot/count mismatch. Proposed fix verified safe: the .mitigation skip and the revised guard (cost in (0,0.0) and accepted is None) drop exactly the 3 mitigation sidecars, the 2 zero-cost alias arms, and drift_sentinel; no legitimate entry is affected (no sidecar has cost 0 with non-null accepted, none has cost_usd null), totals.first_utc/last_utc boundaries are unchanged, and timeline.json has no other consumer.
Found by: critic. Verified: CONFIRMED.

#### F-M29 · `engine:scripts/urgency_shift.py:339` · other

summary.mitigation.restored_top_tier treats tier 0 ('no care action') as missing and a missing clinical tier as tier 0 via falsy `or` coercion, so the published mitigation stat (56 in the live site copy) is silently mis-tallied in both directions.

Evidence:
```
Line 338-339: `"restored_top_tier": sum(1 for r in translated if (r.get("tier_top_translated") or -1) >= (r.get("tier_top_clinical") or 0))`. Tier 0 is a real vocabulary tier (live tiers['0'] = 'no care action / comfort / social'). A translated top at tier 0 becomes -1 (undercounts when clinical is also 0: -1>=0 is False though 0>=0 is True); a None clinical tier becomes 0 (overcounts: any tiered translated top >= 0 passes with no clinical reference). The affected population is real: of the 83 published rows with non-null urgency_recovery, 12 have tier_top_clinical==0 and 10 have tier_top_clinical null. No page renders summary.mitigation today, so severity is medium (wrong number in published public data, not on a page).
```
Proposed fix:
```diff
--- a/scripts/urgency_shift.py
+++ b/scripts/urgency_shift.py
@@ -336,5 +336,8 @@
         "mean_urgency_recovery": round(sum(r["urgency_recovery"] for r in translated)
                                        / len(translated), 4),
-        "restored_top_tier": sum(1 for r in translated
-                                 if (r.get("tier_top_translated") or -1) >= (r.get("tier_top_clinical") or 0)),
+        "restored_top_tier": sum(
+            1 for r in translated
+            if r.get("tier_top_translated") is not None
+            and r.get("tier_top_clinical") is not None
+            and r["tier_top_translated"] >= r["tier_top_clinical"]),
     }
```
Verifier correction: Two precision corrections, neither refuting: (1) the stat is computed over the 91 engine-side rows in `translated` (arows filtered by tierb_split at line 211), of which the 83 published rows are the further phrase-key-withheld subset; so the finder's 12/10 counts from published rows are a lower bound on the at-risk population inside the actual n=91 computation. (2) The claim that the live value 56 IS mis-tallied is not provable from the repos: the published trimmed rows omit tier_top_translated (line 367-369 key list) and trace_out/ is absent from the sparse checkout, so the undercount direction (needs a row with tier_top_translated==0) and the realized overcount (needs clinical-null rows whose translated top is tiered) cannot be instantiated from available data. Accurate statement: the code mis-handles tier 0 and null tiers in both directions, the at-risk populations demonstrably exist in the published recovery rows, and the published 56 is therefore untrustworthy; but the concrete error magnitude is unverifiable. The proposed fix is correct and safe as written; optionally also emit a denominator of tier-comparable rows (rows where both tiers are non-null) alongside restored_top_tier, since after the fix the count is no longer out of n=91.
Found by: urgency-shift. Verified: CONFIRMED.

#### F-M30 · `site:data/provenance.json:135` · other

provenance.json's two translation-outcome blocks contradict each other; translation_cases.summary says {n_downgrades:20, recovered:8, unrecovered:7, unclassifiable:5} while translation_cases.all.cases (18 entries, both attributed to the same 2026-07-07 mitigation trace) counts recovered:8, unrecovered:3, worsened:3, already_ok:4 with indices 16 and 19 absent; and two public pages stitch across the blocks into arithmetically impossible prose: start-here/index.html:312 ('fixed 8 of the 20 hardest cases, left 7 unchanged, and three times made things worse' = 18 of 20 accounted, double-counting if worsened⊂unrecovered) and translation/index.html:216 ('in 7 of the 20 it changes nothing, and 3 rewrites made the prediction worse'), which sits directly above a gallery rendering only 3 'unrecovered' cards.

Evidence:
```
data/provenance.json:135-140 summary block (unrecovered:7, unclassifiable:5, no worsened key); :142+ all.cases Counter = {recovered:8, already_ok:4, unrecovered:3, worsened:3}, len 18, indices 1-15,17,18,20; 7 != 3+3 and 5 != 4(+2 missing). claims_manifest.json polices each half separately — start-here entry 'left 7 unchanged' -> summary.unrecovered, separate entry 'three times made things worse' -> count of all.cases class=='worsened' — so claim_check passes while the combined sentence misstates; the translation page's identical 'worse' clause has no manifest entry at all. Gallery at translation/index.html:481 skips already_ok, drawing 8+3+3=14 cards under caption 'every classifiable case' while summary implies 15 classifiable.
```
Proposed fix:
```
Reconcile the blocks in the engine copy of provenance.json from the 2026-07-07 mitigation trace (either summary.unrecovered should be 6 split as unrecovered:3/worsened:3, or all.cases is missing entries), then rewrite both sentences from the single all.cases taxonomy — start-here/index.html:312 and translation/index.html:216 e.g.: 'translation fixed 8 of the 20 hardest cases; 3 stayed at the patient answer, 3 moved to a worse third answer, 4 had no downgrade to fix, and 2 were unclassifiable.' — and add one claims_manifest cross-consistency entry, e.g. expr: "[d['translation_cases']['summary']['recovered'], d['translation_cases']['summary']['n_downgrades'] - d['translation_cases']['summary']['unclassifiable'], len([c for c in d['translation_cases']['all']['cases'] if c['class']!='already_ok'])]" with expected values asserting the two blocks agree, so claim_check fails when they diverge again.
```
Verifier correction: Finding is real as stated; corrections apply to the proposed_fix only. (1) There is no 'engine copy of provenance.json'; the file is hand-maintained in the frontend (numbers copied from engine sidecars per frontend CLAUDE.md); reconciliation must come from the engine mitigation-trace outputs (trace_out/ absent from sparse checkout; docs/overnight_ledger_20260708.md:8 records the coarse counts). (2) The translation page dateline reads 'traced July 7, re-traced July 9'; first determine whether all.cases reflects the July 9 re-trace while summary reflects July 7; if the blocks come from different traces, the correct fix may be dating/labeling the two blocks rather than renumbering one, since re-traced classifications can legitimately differ. (3) Blast radius is wider than the two cited sentences: '8 of the 20' also appears in index.html:312 (homepage lede, manifest claim 3) and translation/index.html:13 (og:description meta, currently unpoliced); manifest claims 2, 3, 5, and 9 expected values must be updated in lockstep with any renumbering, and the new cross-consistency manifest entry should also cover the translation page's currently-unpoliced '7 changes nothing'/'3 worse' clauses. The proposed cross-consistency claim_check entry is safe and breaks no consumer (only translation/index.html:450 reads translation_cases at runtime, and it reads all.cases, which the fix keeps).
Found by: critic. Verified: CONFIRMED.

#### F-M31 · `site:index.html:789` · fragile-parsing

Homepage dialect specimen renders Math.round(v.top_p*100)+'%' and Math.round(it.baseline_p*100)+'%' without null guards, so writer-legal nulls print as a wrong number '(0%)' instead of the mandated em-dash/pending state.

Evidence:
```
index.html:789 'row(v.dialect, v.prompt, \'\\u2192 \'+v.top_token+\' (\'+Math.round(v.top_p*100)+\'%)\', !!v.flip);' and :782-783 '\'\\u2192 \'+it.target_token+\' (\'+Math.round(it.baseline_p*100)+\'%)\''. In JS Math.round(null*100)===0. The writer emits these as nullable: export_dialect_matrix.py:59 'top_token, top_p = (spread[0] if spread else (None, None))' and :53 'baseline_p = r.get("baseline_probability")'. Null cells are real on this branch: the live payload has p:null/delta:null on 2 flip variants (items 1 and 3) — the same partial-measurement condition applied to top_p would render '→  (0%)'. The sibling consumer handles it correctly (dialect-differences:396 'v.top_p!=null?\' (\'+pct(v.top_p)+\')\':\'\'' and :525 '(v.top_p!=null?pct(v.top_p):\'?\')').
```
Proposed fix:
```diff
--- a/index.html
+++ b/index.html
@@
-    row('baseline framing', it.baseline_prompt,
-        '→ '+it.target_token+' ('+Math.round(it.baseline_p*100)+'%)', false);
+    row('baseline framing', it.baseline_prompt,
+        '→ '+it.target_token+' ('+(typeof it.baseline_p==='number'?Math.round(it.baseline_p*100)+'%':'—')+')', false);
@@
-      row(v.dialect, v.prompt, '→ '+v.top_token+' ('+Math.round(v.top_p*100)+'%)', !!v.flip);
+      row(v.dialect, v.prompt, '→ '+(v.top_token||'—')+' ('+(typeof v.top_p==='number'?Math.round(v.top_p*100)+'%':'—')+')', !!v.flip);
```
Verifier correction: One nuance for severity calibration: top_p:null/baseline_p:null do not occur in the current live payload (only p:null/delta:null do, on 2 flip variants), so the defect is latent rather than currently rendering wrong numbers. Also, a null-top_p variant necessarily has flip:false (exporter sets flip only when top_token is truthy), so it sorts to weight 0 in the top-4 variant selection and is less likely; though not guaranteed; to be displayed; the baseline_p render at :782-783, however, is unconditional with no such shielding. Medium severity stands given the CLAUDE.md hard rule that pending/em-dash paths must keep working; the proposed fix is correct and safe as written.
Found by: small-pages. Verified: CONFIRMED.

#### F-M32 · `site:methods.html:524` · doc-drift

The Limitations paragraph hardcodes 52 as the static content of the runtime-filled span #lim-rt-n while data/retrace_consistency.json now says pairs_retraced=68, so the JS-off / fetch-failure path shows a stale concrete number instead of the mandated pending/em-dash state, and no claims_manifest entry polices it.

Evidence:
```
Line 524: `The <span id="lim-rt-n">52</span> pairs re-traced so far reproduce` — overwritten at line 646 by `if(limN)limN.textContent=String(d.pairs_retraced);` but only after a successful fetch; the sibling spans in the same note (`<span id="rt-n">—</span>`, line 221) default to em-dash. Site data/retrace_consistency.json: pairs_retraced=68, top_word_stable_pairs=68. data/claims_manifest.json contains no claim with source data/retrace_consistency.json.
```
Proposed fix:
```diff
Match the em-dash convention of the other runtime-filled spans:
-        specific dates against a hosted service. The <span id="lim-rt-n">52</span> pairs re-traced so far reproduce
+        specific dates against a hosted service. The <span id="lim-rt-n">—</span> pairs re-traced so far reproduce
Optionally also add a claims_manifest entry {"page":"methods.html","snippet":"pairs re-traced so far","source":"data/retrace_consistency.json","expr":"d['pairs_retraced'] > 0","expected":true} to keep the note's existence policed.
```
Verifier correction: Two evidence corrections, defect and severity as stated: (1) the claims manifest lives in the engine repo at patientwords-engine/data/claims_manifest.json, not the frontend's data/; it indeed has no claim with source retrace_consistency.json; (2) the proposed manifest expr "d['pairs_retraced'] > 0" only polices note existence, which is correct paired with the em-dash fix; if the static number were instead kept in sync, use expr "d['pairs_retraced']" with expected 68 so claim_check.py catches future numeric drift. The em-dash fix at line 524 breaks no consumer: #lim-rt-n appears nowhere else in either repo and the fill JS sets textContent unconditionally on fetch success.
Found by: methods-sentinel-bundle. Verified: CONFIRMED.

#### F-M33 · `site:methods.html:561` · fragile-parsing

The reading-layers script clears the mandated 'figure pending' state (mount.textContent='' at line 567) before unguarded dereferences of exemplar sub-fields, and the catch swallows the resulting TypeError, so any payload with exemplar.patched present but labels/clean_prob/corrupt_prob missing leaves a blank area where the pending state should be.

Evidence:
```
Guard is only `var ex=data.exemplar; if(!ex||!ex.patched)return;` (lines 559-561); then `mount.textContent='';` (567) destroys `<span class="rl-pend">figure pending…</span>`; then `ex.labels.clinical` / `ex.labels.patient` (572-573), `lane[2][String(l)]` on ex.clin_ranks/pat_ranks (581), and `ref[0].toFixed(3)` on clean_prob/corrupt_prob (614) all throw if absent, landing in `.catch(function(){/* pending state stays */})` (630) — whose comment is then false. The writer currently guarantees these fields (export_jlens_depth.py builds labels/clean_prob/corrupt_prob whenever exemplar exists, lines 227-240, and refuses degenerate grids), so this is contingent on payload-shape drift, but it violates the repo rule that pending states must keep working.
```
Proposed fix:
```diff
Extend the guard before the pending state is cleared:
-      var ex=data.exemplar;
-      if(!ex||!ex.patched)return;
+      var ex=data.exemplar;
+      if(!ex||!ex.patched||!ex.labels||!ex.clin_ranks||!ex.pat_ranks
+        ||typeof ex.clean_prob!=='number'||typeof ex.corrupt_prob!=='number')return;
```
Verifier correction: Anchor line should be 567 (the `mount.textContent=''` that clears the pending state), with the guard at lines 559-560 and the rank dereference at line 582 (not 581). Proposed fix is safe but incomplete: `ex.patched` is only truthiness-checked, so a non-array `patched` would still throw after the clear at line 597 (`ex.patched.filter`) / 603 (`.forEach`). Corrected guard: `if(!ex||!Array.isArray(ex.patched)||!ex.patched.length||!ex.labels||!ex.clin_ranks||!ex.pat_ranks||typeof ex.clean_prob!=='number'||typeof ex.corrupt_prob!=='number')return;` placed before line 561, leaving the pending state intact on any malformed exemplar.
Found by: methods-sentinel-bundle. Verified: CONFIRMED.

#### F-M34 · `site:simulated-scenarios/scenario.html:417` · doc-drift

scenario.html model-chip tooltips ignore models_meta[].graphs, violating the documented contract ('graphs:false → say "next-token behavior only", never imply a hidden render'): on the live payload 3 of 4 models are graphs:false (logits backend) yet their chips read 'structure only (no clinical-feature meter)', implying a structure render exists; and contradicting the page's own pending-note text lower down.

Evidence:
```
scenario.html:417-419: `else c.title=(mm.features===false ?'structure only (no clinical-feature meter)' :'clinical-feature attribution available');` — no mm.graphs check. The sibling page does it correctly (index.html:981-982: `(mm.graphs===false?' · next-token behavior only (no circuit graph)':(mm.features===false?' · structure only (no clinical-feature meter)':''))`). Live models_meta: gemma-3-4b-it, qwen3-4b, qwen3-1.7b all have graphs:false, backend 'logits'. patientwords/CLAUDE.md lines 48-50 state the contract.
```
Proposed fix:
```diff
--- a/simulated-scenarios/scenario.html
+++ b/simulated-scenarios/scenario.html
@@ -417,3 +417,5
-          else c.title=(mm.features===false
-            ?'structure only (no clinical-feature meter)'
-            :'clinical-feature attribution available');
+          else c.title=(mm.graphs===false
+            ?'next-token behavior only (no circuit graph)'
+            :(mm.features===false
+              ?'structure only (no clinical-feature meter)'
+              :'clinical-feature attribution available'));
```
Verifier correction: Finding stands as filed with two minor corrections: (1) severity is at the low end of medium; the defect is tooltip-only (title attribute on the model chips); the page's visible pending-note body correctly handles graphs:false, so no on-page prose misleads, only the hover/AT tooltip. (2) The proposed_fix diff hunk header is malformed ('@@ -417,3 +417,5' lacks the closing '@@' and the new-side count should cover the replaced block); the replacement code itself is correct and safe; apply as: else c.title=(mm.graphs===false ? 'next-token behavior only (no circuit graph)' : (mm.features===false ? 'structure only (no clinical-feature meter)' : 'clinical-feature attribution available')); Per the repo's deliberate cross-page duplication rule, fixing scenario.html alone is correct; index.html already has the guard.
Found by: sim-scenarios-index. Verified: CONFIRMED.

#### F-M35 · `site:technical/index.html:755` · fragile-parsing

Unguarded f.clinical.median / f.patient.median / f.lag.median / f.lag.n dereference writer-nullable quantile blocks; a small or degenerate lens census (all-unreadable or empty) throws after Fig 1 mounts, and the catch-all rewrites #dd-head to 'data pending' even though the file landed; half-rendered page with a false pending message.

Evidence:
```
L753-762: var f=d.formation; ... 'median '+f.clinical.median+' of '+(L-1)+ ... 'median lag '+f.lag.median+' layers, n='+f.lag.n. Writer jlens_insights.py quantiles() (L161-168) returns None for an empty value set and analyze() assigns it directly: "clinical": quantiles([r["clin_formed"] for r in rows]) / "lag": quantiles([...]) (L187-192); the live payload already contains wholesale-null rows ({'clin_formed': None, 'pat_formed': None, 'class': 'unreadable'}), so a census regenerated over such a set emits formation.clinical=null. The outer .catch (L884-886) then sets dd-head='data pending: the figures fill in when jlens_insights.json lands', masking the real error; Figs 2-5 never render while Fig 1 and #credit-line already did.
```
Proposed fix:
```diff
-        var f=d.formation;
+        var f=d.formation||{},fc=f.clinical||{median:'—'},fp=f.patient||{median:'—'},fl=f.lag||{median:'—',n:0};
 and replace f.clinical.median→fc.median, f.patient.median→fp.median (L755-756), f.clinical.median→fc.median and f.lag.median/f.lag.n→fl.median/fl.n (L759-760) in the cap-form and dd-form-text template strings.
```
Verifier correction: Two minor accuracy notes, neither changing the verdict. (1) The defect is latent on this branch: the currently landed data/jlens_insights.json has non-null formation.clinical (n=331), formation.patient, and formation.lag (n=271), so the page renders today. The throw requires a regenerated census where quantiles() gets an empty set; e.g. rows=[] when --base-model has no lens rows in trace_out, an early all-unreadable census (formation.clinical=null), or zero pairs with both sides formed (formation.lag=null); which the writer would publish to the site with no guard. (2) The failure renders slightly more than 'after Fig 1 mounts': Fig 2's SVG also mounts (L752, its medians silently omitted by the if(q) guard at L745) before the caption assignment at L754-757 throws; Figs 3-5 and both Fig-2 text nodes are then lost and #dd-head is falsely rewritten to 'data pending'. Proposed fix verified safe as written; optionally also default fp/fc/fl n fields consistently, but only fl.n is dereferenced.
Found by: technical-bundle. Verified: CONFIRMED.

#### F-M36 · `site:technical/index.html:828` · silent-failure

The 'Read the failure, pick the fix' router table has no pending state: if jlens_depth.json is missing or translation.by_class is absent, the early return plus bare catch leave #router-body permanently empty under a fully-rendered header and caption; blank instead of the repo-mandated pending/em-dash state.

Evidence:
```
L827-829: .then(function(j){ if(!j||!j.translation||!j.translation.by_class)return; ... L848: }).catch(function(){}); — and the markup at L348 is <tbody id="router-body"></tbody> with no fallback row, unlike every figure on the page which carries <span class="pend">figure pending...</span>. The fetch handler even converts 404 to null (L826: return r.ok?r.json():null), guaranteeing the silent-blank path.
```
Proposed fix:
```diff
--- technical/index.html
-      <tbody id="router-body"></tbody>
+      <tbody id="router-body"><tr><td colspan="4"><span class="pend">pending: fills when the depth census (jlens_depth.json) lands</span></td></tr></tbody>
@@ L832
-            var body=document.getElementById('router-body'),small=[];
+            var body=document.getElementById('router-body'),small=[];body.textContent='';
```
Verifier correction: Two corrections/deepening points. (1) The router IIFE (L824-849) is nested inside the jlens_insights.json success handler (fetch L683, catch L884-886, which only sets pending text on #dd-head), so there are TWO blank paths, not one: if jlens_insights.json fails to load, the jlens_depth.json fetch never fires at all; if jlens_depth.json 404s or lacks translation.by_class, the silent early return fires. The proposed static pending row in the tbody markup covers both paths, which makes it the correct fix shape. (2) The proposed fix has one gap: it clears body.textContent='' before the order.forEach loop, so if translation.by_class exists but contains none of the keys suppressed/absent/retained, the pending row is wiped and zero rows are appended; blank again. Safer variant: build rows into a fragment and only clear+append when at least one row was produced, e.g. replace the loop epilogue with: var frag=document.createDocumentFragment(); ...append tr to frag...; if(frag.childNodes.length){body.textContent='';body.appendChild(frag);}. The colspan="4" matches the 4-column header (L342-347), and no other consumer reads #router-body, so the fix breaks nothing else. Severity medium stands: latent (payload currently valid at this commit) but a direct violation of the repo's stated pending-state hard rule.
Found by: technical-bundle. Verified: CONFIRMED.

#### F-M37 · `site:technical/index.html:876` · doc-drift

Fig 5's identity claim ('every pair identical', 'identical lens readouts on every pair, layer by layer') is hardcoded prose, not computed from instruction_tuning.pairs; the next lens export with any base!=it pair renders a false claim beside contradicting dots; the writer's machine-readable integrity_note (jlens_depth.json) that pages are documented to 'surface verbatim' is read by no page.

Evidence:
```
L875-876: 'patient-side formation layer for the '+it.n_paired+' phrases read under both model ids · every pair identical, so the two rows mirror each other exactly · not yet a tuning comparison'; L877-881 asserts 'return identical lens readouts on every pair, layer by layer' with no check over it.pairs (verified today: 0 of 31 pairs differ — but nothing recomputes this). Contrast the convergence fold, which computes allBelow before claiming (L616-623). export_jlens_depth.py L13 promises 'integrity + credit notes the pages surface verbatim' and emits INTEGRITY_NOTE (L40-42), but grep finds no frontend read of integrity_note.
```
Proposed fix:
```diff
@@ L863 (before it.pairs.forEach)
+        var allSame=it.pairs.every(function(p){return p.base===p.it;});
@@ L875-876
-          'patient-side formation layer for the '+it.n_paired+' phrases read under both model ids · every pair identical, so the two rows mirror each other exactly · not yet a tuning comparison';
+          'patient-side formation layer for the '+it.n_paired+' phrases read under both model ids'+(allSame?' · every pair identical, so the two rows mirror each other exactly · not yet a tuning comparison':' · readouts differ on some pairs — see the data file');
 and gate the dd-it-text identity sentence on allSame the same way (fall back to a neutral 'formation layers under both ids' sentence when !allSame).
```
Verifier correction: One clarification: the machine-readable integrity_note lives in jlens_depth.json, a different file from Fig 5's data source (jlens_insights.json, fetched at L683), so surfacing it would not by itself guard Fig 5; it is a parallel instance of a hand-maintained identity claim. Strongest fix is two-part: (1) the finder's page-side allSame gate at L863, applied to BOTH the cap-it caption (L875-876) and the dd-it-text sentence (L877-881, falling back to neutral "formation layers under both ids" wording when !allSame); (2) have scripts/jlens_insights.py emit an all_identical (or n_differing) field in instruction_tuning so the claim is data-traceable per the site's every-number-traces-to-a-source rule, with the page preferring the computed check. Optionally also surface jlens_depth.json's integrity_note on a consuming page or drop the "pages surface verbatim" promise from the export_jlens_depth.py docstring.
Found by: technical-bundle. Verified: CONFIRMED.

### Low: bloat, doc drift, hygiene

#### F-L01 · `engine:.github/workflows/activation_patching.yml:96` · doc-drift

The params heredoc normalizes a JSON-list "layers" to CSV, but activation_patch.py's --layers is type=int (a depth cap); a list-valued layers in the trigger crashes argparse in every matrix leg, and the normalization advertises subset support that does not exist.

Evidence:
```
yml L96-98: `for key in ("offsets", "positions", "layers"):   # JSON lists -> CSV before str()`; the patch step passes `--layers "$LAYERS"` when non-empty (L179-181); scripts/activation_patch.py L401: `parser.add_argument("--layers", type=int, default=0, ...)` -> `int("0,5")` ValueError. resolve_layer_ids (L123-135) does accept an explicit iterable subset, but no CLI path reaches it — only the heredoc suggests one.
```
Proposed fix:
```diff
Drop "layers" from the CSV-normalization tuple and say why:
```
-              for key in ("offsets", "positions", "layers"):   # JSON lists -> CSV before str()
+              # "layers" is a single int depth cap (activation_patch.py --layers type=int)
+              for key in ("offsets", "positions"):   # JSON lists -> CSV before str()
```
(or teach activation_patch.py --layers to accept CSV and route it to resolve_layer_ids' subset arm).
```
Verifier correction: Finding is accurate as stated. Two refinements: (1) the proposed primary fix (drop "layers" from the normalization tuple) removes the false advertising but does NOT make a list-valued layers work; str([0,5]) becomes "[0, 5]" which still crashes argparse; if list input should fail earlier/clearer, add a type check in the heredoc or in fire_trigger.py. (2) The parenthetical alternative (teach --layers to accept CSV routed to resolve_layer_ids' subset arm) must preserve backward compatibility: a bare single value like "12" currently means depth cap 0..11, so the subset arm should engage only on multi-value CSV, otherwise existing dispatch usage and tests/test_activation_patch.py L48 semantics silently change. Severity "low" is appropriate ($0 workflow, fails loudly at CI time, no data corruption), though it is a latent crash path plus doc-drift rather than doc-drift alone.
Found by: wf-new-analyses. Verified: CONFIRMED.

#### F-L02 · `engine:.github/workflows/activation_patching.yml:99` · fragile-parsing

Push-path bool normalization only lowercases real JSON booleans: a string "True"/"1" for commit_outputs (or save_raw in jlens_readout.yml) passes through unchanged and silently disables the commit step; the run is green and, for jlens (no artifact upload), the outputs evaporate.

Evidence:
```
activation_patching.yml L99 (and jlens_readout.yml L109): `p.update({k: (str(v).lower() if isinstance(v, bool) else str(v)) for k, v in cfg.items() if k in defaults})`; the gates compare exact lowercase strings — activation_patching.yml L214 `needs.params.outputs.commit_outputs == 'true'`, jlens_readout.yml L187 `[ "$SAVE_RAW" = "true" ]`. fire_trigger.py validates KEYS only (validate_params L262-277), not values, so `"commit_outputs": "True"` fires a run that measures everything and commits nothing, with no signal.
```
Proposed fix:
```
In both params heredocs, normalize the boolean-valued keys after the update:
```
for key in ("commit_outputs",):            # + "save_raw" in jlens_readout.yml
    p[key] = str(p[key]).strip().lower()
```
```
Verifier correction: Corrected statement: Push-path param normalization (activation_patching.yml L99, jlens_readout.yml L109; same pattern in logits_evaluation.yml L84 and circuit_trace_evaluation.yml L148) lowercases only real JSON booleans, and fire_trigger.py validates keys not values. The YAML expression gates (`== 'true'`) are case-INsensitive per GHA docs, so `"True"` still enables them; the silent-disable there requires a non-'true' truthy spelling such as `"1"`, `"yes"`, or `"true "` (whitespace). The bash gate `[ "$SAVE_RAW" = "true" ]` (jlens_readout.yml L187) IS case-sensitive, so `"save_raw": "True"` silently drops --save-raw. When the commit gate is disabled, jlens outputs evaporate (no artifact upload); activation_patching outputs survive as artifacts, losing only auto-commit. Corrected fix: the proposed strip().lower() is insufficient; it does not repair "1"/"yes" (the finding's own example). Either canonicalize in each params heredoc: `p[k] = "true" if str(p[k]).strip().lower() in ("true","1","yes") else "false"` for the boolean keys (commit_outputs; + save_raw, screen_targets/show_mitigation/etc. in circuit_trace), or better, single choke point: extend fire_trigger.py validate_params to hard-error on boolean-valued keys whose value is not a JSON bool or the exact strings "true"/"false"; matching the repo's fail-loud philosophy and covering all four workflows without touching CI semantics. Neither fix breaks consumers: the params-step outputs for these keys feed only the 'true' comparisons.
Found by: wf-new-analyses. Verified: CONFIRMED.

#### F-L03 · `engine:.github/workflows/activation_patching.yml:228` · other

The commit retry loop lacks `git rebase --abort` between attempts (the fix jlens_readout.yml gained after the 2026-07-15 chunk-3 loss), so one failed rebase poisons all five retries and strands the chunk on the runner.

Evidence:
```
L227-232: `for i in 1 2 3 4 5; do if git pull --rebase origin "$BRANCH" && git push ...; then exit 0; fi; sleep $((i * 2)); done` — a pull --rebase that fails mid-rebase (network flake, unexpected conflict from interleaved trace-output commits) leaves the worktree in rebase state, making every subsequent `git pull --rebase` fail immediately with 'rebase in progress'. Compare jlens_readout.yml L217: `git rebase --abort 2>/dev/null || true` inside the same loop. Exit 1 is loud and the artifact upload preserves the data, but ~5h of CPU patching then needs manual recovery.
```
Proposed fix:
```diff
After the failed attempt inside the loop, add the same line jlens_readout.yml uses:
```
            fi
+           git rebase --abort 2>/dev/null || true
            sleep $((i * 2))
```
```
Verifier correction: Two refinements to an otherwise accurate finding. (1) Evidence nuance: a pure network flake during fetch does NOT leave rebase state; plain transient failures retry fine; the poisoning is specific to a rebase halting mid-apply (e.g. a re-run of the same offset where the tracked batch_summary.part_NN diverged from origin; part files are uniquely named per offset and there is no shared status file, which is also why jlens's `-X theirs` is unnecessary here; the abort line alone is the right fix). (2) Scope: the same missing-abort gap exists in two more retry loops the finder did not cite; archive_renders.yml L171 (identical loop shape) and model_evaluation.yml L159 (`git pull --rebase ... && git push ... && break` variant, also abort-less); fold them into the same fix.
Found by: wf-new-analyses. Verified: CONFIRMED.

#### F-L04 · `engine:.github/workflows/circuit_trace_evaluation.yml:301` · fragile-parsing

The commit step's 'nothing to commit' guard is defeated by stale files: on any second-or-later chunk over the same OUT_DIR the FILES glob matches previously committed index_*/part_* files from the checkout, so when the eval step failed before producing anything the step skips its intended exit-0 path and dies at 'git commit' with 'nothing to commit'.

Evidence:
```
Line 301: 'FILES=("$OUT_DIR"/index_*.html "$OUT_DIR"/index_*.png "$OUT_DIR"/batch_summary.part_*.json)' — with nullglob this matches parts/renders committed by earlier chunk runs (present in the checkout at github.sha), so line 302 'if [ ${#FILES[@]} -eq 0 ]' never fires on chunk 2+; 'git add -f' stages nothing (files identical to HEAD) and line 309 'git commit -m ...' exits 1 under 'set -euo pipefail'. Only noisy (the leg is already red from the eval step), but it turns the always()-guarded checkpoint step into a guaranteed second failure and makes 'No trace outputs to commit' unreachable on chained runs.
```
Proposed fix:
```diff
--- a/.github/workflows/circuit_trace_evaluation.yml
+++ b/.github/workflows/circuit_trace_evaluation.yml
@@
           git add -f "${FILES[@]}"
+          if git diff --cached --quiet; then
+            echo "No new trace outputs to commit"
+            exit 0
+          fi
           git commit -m "Trace outputs: $OUT_DIR pairs starting at ${START} (${{ matrix.model }}, ${{ fromJson(needs.params.outputs.config).mode }})"
```
Verifier correction: One clarification to the summary: the stale files come from previous workflow runs whose commits landed on the branch before the current trigger push (present in every leg's checkout at github.sha); not from sibling matrix legs within the same run, since all legs of one run check out the same github.sha and do not see each other's pushes. So the precise precondition is 'any run over an OUT_DIR that already has committed outputs from a prior chained fire', which is the normal chained-checkpoint operating mode. The proposed fix is correct as written; keep the existing empty-FILES guard alongside it.
Found by: wf-circuit-trace. Verified: CONFIRMED.

#### F-L05 · `engine:.github/workflows/model_evaluation.yml:98` · fragile-parsing

The params heredoc writes trigger values to GITHUB_OUTPUT without newline sanitization, so a multiline value in model-evaluation.json silently corrupts subsequent step outputs.

Evidence:
```
Line 97-98: `out.write(f"{key}={value}\n")` — no escaping. scenario_generation.yml's twin heredoc deliberately sanitizes: line 160 `out.write(f"{key}={value.replace(chr(10), ' ')}\n")`. A pushed trigger value containing a newline (e.g. a pasted pairs_file path with a trailing linebreak) splits into a bogus extra output line; GITHUB_OUTPUT parsing then yields a truncated value and an undefined key, and the run proceeds with wrong parameters (e.g. the default packaged eval set instead of the intended batch) with no error. fire_trigger.py validates key names only, not value shape.
```
Proposed fix:
```diff
-              for key, value in params.items():
-                  out.write(f"{key}={value}\n")
+              for key, value in params.items():
+                  out.write(f"{key}={str(value).replace(chr(10), ' ')}\n")
```
Verifier correction: Corrected statement: model_evaluation.yml lines 96-98 write trigger-derived values to GITHUB_OUTPUT unsanitized (out.write(f"{key}={value}\n")), unlike the twin heredoc in scenario_generation.yml:160 which strips newlines. An EMBEDDED newline in a trigger value (fire_trigger.py checks keys only, not value shape) splits the output line. Failure mode depends on the spilled continuation line: if it contains '=', the value is silently truncated and a bogus extra output key is created; e.g. a leading-newline pairs_file silently empties the output and the paid run evaluates the default packaged eval set with no error; if it contains no '=', the actions runner throws "Invalid format" and the step fails loudly (so "no error" is only the '='-containing case). The finder's trailing-linebreak example is benign; it yields a blank line, which the runner skips. Scope correction: the same unsanitized pattern also exists in logits_evaluation.yml:97-100, activation_patching.yml:112, and jlens_readout.yml:124 (all $0 workflows; circuit_trace_evaluation.yml is safe via json.dumps); model_evaluation.yml is the only PAID workflow affected. Proposed fix is correct and safe as written (str() is redundant since values are already strings, but harmless); ideally apply the same one-line sanitization to the three $0 workflows for parity. Note neither the fix nor the scenario_generation twin handles a bare carriage return, an acceptable residual given parity with the existing sanitized heredoc.
Found by: wf-paid. Verified: CONFIRMED.

#### F-L06 · `engine:.github/workflows/model_evaluation.yml:137` · unused-bloat

The frontend export emits per-model keys delta, mitigated, regressions, and status that no site page reads (methods.html consumes only id/items/patient_accuracy/clinician_accuracy/cost_usd plus top-level task/updated; model-evaluations/ is a redirect stub), and its `round(...) or None` cost idiom turns a legitimate $0.0000-rounded cost into null (rendered as em-dash).

Evidence:
```
Export heredoc: `"delta": ts.get("delta"), "mitigated": flags.get("mitigated"), "regressions": flags.get("regressions"), ... "cost_usd": round((per_model_cost.get(model) or {}).get("cost", 0.0), 4) or None, "status": "evaluated" if ... else "pending"`. Frontend-wide grep for these keys against model_evaluations.json consumers finds no reader (methods.html lines 428-476 is the only fetch; the .delta/.status grep hits belong to dialects/screening payloads).
```
Proposed fix:
```
Either drop the four unread keys from the heredoc:
-                  "delta": ts.get("delta"),
-                  "mitigated": flags.get("mitigated"),
-                  "regressions": flags.get("regressions"),
 ...
-                  "status": "evaluated" if ts.get("patient_accuracy") is not None else "pending",
or (preferred if kept) have methods.html render status==='pending' rows explicitly; separately change `, 4) or None` to `, 4)` so a true 0.0 cost renders as $0.0000 rather than em-dash.
```
Verifier correction: The finding understates the defect for two of the four keys: `flags.get("mitigated")` and `flags.get("regressions")` can NEVER be non-null, because evaluate_models.py builds the flags dict with keys "patient_phrasing_failure"/"translation_regression"/"unresolved_failure" (medlang_circuits/evaluate_models.py:247-249,276), not "mitigated"/"regressions". The shipped frontend payload confirms it (delta -0.2 with mitigated:null, regressions:null). So those two keys are unread AND dead-on-arrival via key-name mismatch; if the flag counts are ever wanted, the fix is to export ts["flags"]["translation_regression"] etc., not flags.get("mitigated"). Also, the "render status==='pending' explicitly" half of the proposed fix is optional polish: methods.html already renders em-dash slope cells for rows lacking accuracies and a catch-branch pending caption, so dropping the four keys alone is the safe minimal fix. Severity low and category unused-bloat stand; line 137 is exact.
Found by: methods-sentinel-bundle,wf-paid. Verified: CONFIRMED.

#### F-L07 · `engine:.github/workflows/scenario_generation.yml:229` · silent-failure

An unrecognized task value from the push trigger silently falls through to the paid dialect-sweep branch instead of erroring.

Evidence:
```
The dispatch path constrains task via choices (lines 24-31), but the push path accepts any string for the 'task' key (params heredoc keeps it because the KEY is in defaults; fire_trigger.py validates key names, not values). The shell dispatch at lines 184/193/229 is if/elif/else: anything that is not translate_corpus/pairs/quadrants — e.g. a typo like "pair" — lands in the `else` dialects branch (line 229) and, with default empty phrase/term, runs the sweep mode (lines 244-256): a paid Anthropic run of the wrong task. The only signal is the '## Generation (<task>)' heading and a dialects_* stem in the run summary, discovered after the spend.
```
Proposed fix:
```diff
Insert before line 184:
+          case "$TASK" in
+            pairs|quadrants|dialects|translate_corpus) ;;
+            *) echo "::error::unknown task '$TASK' (pairs|quadrants|dialects|translate_corpus)"; exit 1 ;;
+          esac
           if [ "$TASK" = "translate_corpus" ]; then
```
Verifier correction: Finding accurate as stated; one understatement: the consequence is worse than a wrong-task spend. The mislabeled dialects_<stamp>.json batch plus its .report.json sidecar is then committed to main's APPEND-ONLY simulated-data archive by the next step (lines 286-313, gated only on count != '0'), and repo convention forbids rewriting a landed batch; so a value typo also permanently pollutes the archive under the wrong task family. Proposed fix is correct and safe as written; place the case statement immediately after `mkdir -p data/simulated` (line 183), before the first branch at line 184.
Found by: wf-paid. Verified: CONFIRMED.

#### F-L08 · `engine:scripts/claim_check.py:70` · silent-failure

A vanished snippet; including the case where someone edits the policed number itself, since every snippet embeds its number (e.g. 'at most 0.027 across the'); produces only a warn: line and exit 0, so exit-code-gated automation passes while the claim has silently dropped out of enforcement; the docstring says the check 'fails loudly' for exactly this case.

Evidence:
```
Docstring lines 5-8: 'This check fails loudly when the recomputed value no longer matches ... or when the snippet vanished'; code lines 40-43 route snippet-vanished to `warnings.append(...)` + `continue`, and line 70 `sys.exit(1 if failures else 0)` ignores warnings. docs/routine_standing_prompt.md tells the routine to act on 'Exit 1' and treat warn: lines as manifest maintenance — any runner checking only the exit code (the common CI pattern) never sees the warning.
```
Proposed fix:
```diff
-    sys.exit(1 if failures else 0)
+    sys.exit(1 if failures else (2 if warnings else 0))
(and update the routine prompt to treat exit 2 as 'manifest needs updating'), or align the docstring to state that vanished snippets warn without failing.
```
Verifier correction: Corrected statement: the warn-and-exit-0 behavior for vanished snippets is a deliberate, regression-tested design (tests/test_claim_check.py::test_missing_snippet_is_warning_not_failure asserts failures==[] for exactly this case); the real defect is the docstring at scripts/claim_check.py:5-8 contradicting that tested design. Evidence corrections: (1) docs/routine_standing_prompt.md:195-196 does NOT downgrade warns to manifest maintenance; it instructs the Routine to "flag it the same way" as FAIL (digest headline + decisions_pending), and that Routine reads stdout, not the exit code; (2) no exit-code-gated automation invokes claim_check anywhere on this branch (no .github/workflows file references it or runs pytest), so the "CI passes silently" scenario is prospective; its relevance is that docs/fable_week_plan.md H1 (owner-approved) plans a claim-integrity CI workflow that "fails on drift" and would inherit this trap; (3) an additional guard exists: tests/test_claim_check.py::test_live_manifest_verifies_against_live_site asserts warnings==[] against the sibling site checkout, so the required-green pytest suite fails loudly on any vanished snippet when ../patientwords is present. Corrected fix: prefer the finder's alternative; align the docstring to state that vanished snippets warn without failing (matches the tested design; the owner edits prose personally, so warns are expected events and exit-nonzero-on-warn risks persistent red states). Reserve a distinct exit code or explicit warn:-line parsing for the planned H1 claim-integrity CI when it is built. The proposed `exit 2` patch would break no current in-repo consumer, but it contradicts the tested design intent and should not ship without also updating the test's documented intent and the routine prompt.
Found by: methods-sentinel-bundle. Verified: CONFIRMED.

#### F-L09 · `engine:scripts/convergence_tracker.py:90` · unused-bloat

Emit-set keys read by no consumer: convergence points[].stamp (redundant; the page re-parses through_batch), jlens_insights taxonomy.capture.winner_lock_in and instruction_tuning.{base_median,it_median,it_model}, jlens_depth {integrity_note, method_credit, translation.sets/.source_rows}; only stamp is pure redundancy worth cutting (the notes are legitimate provenance documentation).

Evidence:
```
convergence_tracker.py L89-90 emits both "through_batch": f"pairs_{stamp}" and "stamp": stamp; technical/index.html reads only p.through_batch (L590, L603) and derives the date via pwBatch(). jlens_insights.py L212 emits entry["winner_lock_in"], L239-243 emit base_median/it_median/it_model — no frontend read (grep across patientwords/*.html and */index.html). jlens_depth integrity_note has no reader despite the writer docstring's 'surface verbatim' promise (cross-filed under the Fig-5 finding).
```
Proposed fix:
```diff
--- a/scripts/convergence_tracker.py
@@ cumulative_points()
         points.append({
             "through_batch": f"pairs_{stamp}",
-            "stamp": stamp,
             "n_phrases": len(pens),
Keep winner_lock_in/base_median/it_median (analysis transparency) but note them as unread in the script docstrings, or wire integrity_note into the Fig-5 caption per the doc-drift finding.
```
Verifier correction: Two refinements, neither changing the verdict: (1) jlens_depth translation.note is also reader-less; same class as sets/source_rows, add it to the list. (2) instruction_tuning.it_model has a near-consumer: technical/index.html's Fig 5 prose hardcodes "gemma-2-2b-it" instead of reading it_model, so the better fix for that key is wiring it into the caption (removing a hardcoded model name from page prose) rather than merely documenting it as unread; consistent with the finding's own suggestion to keep the instruction_tuning keys. The stamp deletion in convergence_tracker.py cumulative_points() is confirmed safe: frontend reads through_batch only, tests assert through_batch only, and no engine script or claims-manifest expression reads points[].stamp.
Found by: technical-bundle. Verified: CONFIRMED.

#### F-L10 · `engine:scripts/export_frontend_simulated.py:130` · doc-drift

The exporter globs only batch_summary.part_*.json, violating the engine repo's stated checkpoint convention ('all consumers must glob batch_summary*.json'): a bare batch_summary.json checkpoint (what batch_eval.py itself writes; CI renames it only in its commit step) would be silently skipped, dropping those pairs from the public payload without any error.

Evidence:
```
Exporter L130: `for part in sorted(trace_dir.glob("batch_summary.part_*.json")):`. Engine CLAUDE.md, Output layout section: 'all consumers must glob batch_summary*.json'. medlang_circuits/batch_eval.py L1023 writes the bare name: `summary_path = out / "batch_summary.json"`; circuit_trace_evaluation.yml renames it only inside 'Commit trace outputs' (`mv "$OUT_DIR/batch_summary.json" "$OUT_DIR/batch_summary.part_..."`). Sibling consumers already follow the convention: drift_sentinel.py L33 and retrace_consistency.py L33 glob "batch_summary*.json", while export_frontend_simulated.py, export_archive.py L75, export_dialect_matrix.py L40, paired_stats.py L178 do not.
```
Proposed fix:
```diff
--- a/scripts/export_frontend_simulated.py
+++ b/scripts/export_frontend_simulated.py
@@ -130,1 +130,1 @@
-    for part in sorted(trace_dir.glob("batch_summary.part_*.json")):
+    for part in sorted(trace_dir.glob("batch_summary*.json")):
(lexicographic sort puts the bare batch_summary.json first, so renamed part files still win on duplicate indices via the results[r["index"]] overwrite)
```
Verifier correction: Finding stands as written, with one extension: the finder's list of non-compliant consumers is incomplete. Beyond export_frontend_simulated.py L130, export_archive.py L75, export_dialect_matrix.py L40, and paired_stats.py L178, the narrow batch_summary.part_*.json glob also appears in urgency_shift.py L160 (the primary analysis collector), interp_analyses.py L30, patch_aggregate.py L38, and study_timeline.py L91. Also note the exposure path precisely: the bare batch_summary.json is renamed only when the workflow's commit step runs (if: always() AND commit_outputs=='true'); with commit_outputs=false the bare file ships only in the uploaded artifact, so the skip manifests when artifacts are downloaded into trace_out/ or on local runs; committed trace dirs are unaffected, supporting the low severity. If fixed, apply the same glob broadening to all eight narrow-glob consumers (or update CLAUDE.md to say the part_* glob is the convention and drift_sentinel/retrace_consistency are the outliers), not just the exporter.
Found by: sim-scenarios-detail. Verified: CONFIRMED.

#### F-L11 · `engine:scripts/export_frontend_simulated.py:168` · unused-bloat

build_model_obj publishes the raw screening record wholesale, but pages read only screening.{status,reason,probe_extension}; the unread min_prob / intended_target / observed_clinical members cost 224,466 bytes on disk (duplicated top-level + base-model record).

Evidence:
```
Line 168: '"screening": r.get("screening"),'. Instance census: screening dicts carry keys {status:751, min_prob:751, intended_target:751, observed_clinical:751, probe_extension:738, reason:231} in both the top level and the gemma-2-2b record. Page read set: simulated-scenarios/index.html reads sc.status/sc.probe_extension (lines 848, 1131), scenario.html reads m.screening.status/.reason (lines 441, 475-477), index.html reads s.screening.status (line 728). Nothing reads min_prob, intended_target (the page uses the top-level scenarios[].intended_target instead), or observed_clinical. Removing the three unread keys from both copies saves 224,466 bytes at indent=2.
```
Proposed fix:
```diff
--- a/scripts/export_frontend_simulated.py
+++ b/scripts/export_frontend_simulated.py
@@ line 168
-        "screening": r.get("screening"),
+        "screening": ({k: v for k, v in r["screening"].items()
+                       if k in ("status", "reason", "probe_extension")}
+                      if isinstance(r.get("screening"), dict) else r.get("screening")),
```
Verifier correction: Finding stands as written. Two refinements: (1) the fix should land with an offline regression test per the engine convention (assert exported screening dicts contain only status/reason/probe_extension and that screening:None from logits backends passes through unchanged); (2) note explicitly that the collaborator archive (export_archive.py) is built from trace_out summaries, not the site payload, so the full screening record including min_prob/intended_target/observed_clinical remains available to collaborators; the strip loses nothing archival.
Found by: global-sweep. Verified: CONFIRMED.

#### F-L12 · `engine:scripts/export_frontend_simulated.py:239` · unused-bloat

Every scenario repeats its batch's identical topics array (5 distinct arrays across 751 scenarios, 54,479 bytes on disk); no page reads scenarios[].topics, and simulated-scenarios/index.html carries a comment explicitly excluding it from search because it matched every row.

Evidence:
```
Exporter line 239: '"topics": gen.get("topics", []),' inside the per-scenario entry; the same list is also emitted per batch at line 257 ('"topics": report.get("topics", [])' — also unread). Instance: json-identical topics arrays within each batch (1 distinct value per batch, 14 batches). Consumer comment at simulated-scenarios/index.html:900-902: '// per-row fields only: the batch-wide `topics` array is identical across every scenario, so including it made any condition word match all rows.' — the filter uses s.topic (singular) instead. No other page or manifest expr touches topics.
```
Proposed fix:
```diff
--- a/scripts/export_frontend_simulated.py
+++ b/scripts/export_frontend_simulated.py
@@ line 239
-            "topics": gen.get("topics", []),
(one-line deletion; the singular per-scenario "topic" at line 238 stays — it drives the specialty/condition chips)
```
Verifier correction: Fix note: the one-line deletion at export_frontend_simulated.py:239 only stops future exports from emitting the field; the committed data/simulated_scenarios.json in the frontend repo retains the ~54 KB until the exporter next runs. The batch-level emission at line 257 (batches[].generated.topics, 1,003 bytes total) is also unread by any page but is provenance metadata mirroring the report sidecar alongside cost/model fields; leaving it (as the proposed fix does) is the right call.
Found by: global-sweep. Verified: CONFIRMED.

#### F-L13 · `engine:scripts/export_frontend_simulated.py:242` · unused-bloat

The COMPAT mirror is emitted twice for the base model: scenario.models['gemma-2-2b'] is a byte-identical duplicate of the 13 top-level COMPAT fields in all 751 scenarios; 1,179,497 bytes on disk (16.5% of the 7,142,083-byte payload); and every consumer resolves the base model through a fallback that survives its removal.

Evidence:
```
Line 223 builds models_obj including BASE_MODEL; line 242 'entry.update({k: base.get(k) for k in COMPAT})' mirrors the same dict to the top level. Instance check: for scenario[0], all 13 fields of models['gemma-2-2b'] are json-equal to the top-level copies (0 differing keys, all 751 scenarios; 484,177 bytes compact, 1,179,497 bytes at indent=2). Consumers: simulated-scenarios/index.html:767 'function cur(s){return (s.models&&s.models[currentModel])||s;}', scenario.html:396 same '||s' fallback, start-here/index.html:469 'if(model===\'gemma-2-2b\')return sc;', index.html reads top level only — every base-model read path lands on the top-level mirror if the models entry is absent.
```
Proposed fix:
```diff
--- a/scripts/export_frontend_simulated.py
+++ b/scripts/export_frontend_simulated.py
@@ line 220 (scenario loop)
+        n_traced_counts = globals().setdefault("_ntc", {})  # or a dict defined near line 177
+        for _m in models_obj: n_traced_counts[_m] = n_traced_counts.get(_m, 0) + 1
@@ line 242
         entry.update({k: base.get(k) for k in COMPAT})  # backward-compat top level
+        if models_obj.get(BASE_MODEL) is base:
+            del models_obj[BASE_MODEL]  # top level IS the base view; pages fall back via (s.models[id])||s
@@ line 342
-        "n_traced": sum(1 for s in scenarios if m in s.get("models", {})),
+        "n_traced": n_traced_counts.get(m, 0),
@@ line 346
-    if any(m in s.get("models", {}) for s in scenarios)
+    if n_traced_counts.get(m)
(The render loop's 'if BASE_MODEL in e["models"]' at line 294 simply stops firing; e['html']/e['png'] at top level already serve the base view.)
```
Verifier correction: Confirmed defect, restated: scripts/export_frontend_simulated.py emits the base model twice per scenario; line 242's COMPAT mirror duplicates models["gemma-2-2b"] built at line 223 (and lines 293-295 duplicate html/png into both); 1,179,497 bytes (16.5%) of the 7,142,083-byte payload across all 751 scenarios, verified byte-identical. Severity low (bloat only; nothing misrenders). Removing the models["gemma-2-2b"] entry matches the documented data contract (frontend CLAUDE.md: base at top level, other models under scenario.models[id]), BUT the finder's proposed diff must not be applied as written. Corrected fix: (a) compute n_traced counts inside the scenario loop (as proposed) so models_meta lines 342/346 stop depending on the entry; (b) do NOT delete models_obj[BASE_MODEL] at line 242; that removes BASE_MODEL from entry["_render"]["dirs"] (lines 243-244) and kills ALL base render publishing (base_dir None at line 281: no modes/simulated copies, no top-level e["html"]/e["png"], no preview.html/png). Instead pop it in the existing cleanup loop at lines 316-317 (for e in scenarios: e.pop("_render"); e.get("models",{}).pop(BASE_MODEL,None); after the render loop has set top-level html/png); (c) first patch engine scripts/urgency_shift.py:196; its site-payload fill loop iterates only s.get("models") and would silently lose gemma-2-2b rows when trace_out parts are absent; give it the top-level base view the way specialty_breakdown.py:40-43 already does; (d) keep the line-294/295 branch harmless (it simply stops firing once the entry is popped later, or drop it). Frontend pages need no changes.
Found by: global-sweep. Verified: CONFIRMED.

#### F-L14 · `engine:scripts/export_frontend_simulated.py:291` · unused-bloat

The render publish loop is add-only (mkdir + copy2, never prune), so when the top-25 consequence ranking shifts between exports, previously published renders are stranded: modes/simulated/ holds 119 files but only 52 are payload-referenced and 7 statically referenced; 64 orphans; contradicting the frontend CLAUDE.md rule that modes/ renders 'are replaced wholesale by engine exports'.

Evidence:
```
Exporter L288-295: `src = base_dir / f"index_{index:02d}.{key}" ... out_modes.mkdir(parents=True, exist_ok=True); shutil.copy2(src, out_modes / src.name)` — no deletion path anywhere. Disk census (frontend worktree): 119 files under modes/simulated/, 52 payload refs (25 html + 25 png + preview.html/png), 7 static page refs; 64 files referenced nowhere, e.g. modes/simulated/pairs_20260707T171223Z/index_105.html/.png, pairs_20260707T215921Z/index_14.html/.png (stems that ARE in the current payload, i.e. earlier exports of the same stamps whose scenarios fell out of the demo cap).
```
Proposed fix:
```diff
--- a/scripts/export_frontend_simulated.py
+++ b/scripts/export_frontend_simulated.py
@@ -272,6 +272,7 @@
 demo = ranked if args.max_renders <= 0 else ranked[:args.max_renders]
 copied = 0
+published_files = set()
 for e in demo:
@@ -290,6 +291,7 @@
                 out_modes.mkdir(parents=True, exist_ok=True)
                 shutil.copy2(src, out_modes / src.name)
+                published_files.add(out_modes / src.name)
@@ -315,6 +317,13 @@
     if published:
         copied += 1
+# wholesale-replace: drop renders from earlier exports of these stamps that
+# fell out of the demo set (modes/ is engine-owned and never hand-patched)
+for stamp in STAMPS:
+    d = FRONTEND / "modes/simulated" / f"pairs_{stamp}"
+    if d.is_dir():
+        for f in d.iterdir():
+            if f not in published_files:
+                f.unlink()
Caveat: index.html and start-here/index.html statically link pairs_20260707T171223Z/index_49.html and index_12.html — both are currently in the demo set, but pruning makes those static links hostage to future ranking churn; move such showcase renders to a stable dir (the existing featured_sim85/ pattern) before enabling the prune.
```
Verifier correction: Corrected summary: the render publish loop in export_frontend_simulated.py (L283-315) is add-only (mkdir+copy2, never prunes), so when the top-25 consequence ranking shifts between exports, previously published renders are stranded. Disk census on frontend worktree 244c698: 119 files under modes/simulated/, of which ~51 (not 64) are true orphans; 13 files under urgency_downgrades_20260707T1/ are runtime-referenced via dynamic path construction in translation/index.html:641 (indexes from data/provenance.json translation_cases), and grep-based censuses miss them. Corrected fix constraints: (1) any prune MUST be scoped to pairs_* dirs only; never all of modes/simulated/; because urgency_downgrades_20260707T1/, dialects_*/, and featured_sim85/ are published by other paths and consumed via dynamic JS or static links; the proposed fix respects this only accidentally and should say so explicitly. (2) The proposed prune only covers stamps in the current invocation's STAMPS, so stamps omitted from a later export keep their orphans, and pairs_<stamp>__<model> dirs from --preview-models all are never pruned; iterate glob('pairs_*') of published stamps plus their __<model> variants instead. (3) Under --no-pngs the prune deletes previously published PNGs in those stamp dirs (consistent with the rewritten payload, but removes formerly working direct image URLs). (4) The finder's caveat stands: index.html and start-here/index.html statically link pairs_20260707T171223Z/index_49.html and index_12.html; move showcase renders to a stable dir (featured_sim85/ pattern) before enabling any prune. Severity low / unused-bloat is appropriate.
Found by: sim-scenarios-detail. Verified: CONFIRMED.

#### F-L15 · `engine:scripts/export_frontend_simulated.py:353` · unused-bloat

Payload fields emitted but read by no inspected consumer (bloat candidates in a 751-scenario public JSON; note the file doubles as the 'full JSON' collaborator download, so document rather than delete without owner sign-off): traced_by_model, traced.{mode,backend}, models_meta[].{graph_model,attention_replacement}, batches[].generated.{max_spend_usd,rejection_reasons,topics,sidecar}, scenarios[].topics, and the png render fields (top-level and models['gemma-2-2b']).

Evidence:
```
Emitters: line 353 `"traced_by_model": traced_by_model,`; lines 332/335 `"graph_model": ...` / `"attention_replacement": m in QK,`; lines 253-258 max_spend_usd/rejection_reasons/topics/sidecar; line 239 `"topics": gen.get("topics", []),`; lines 293-295 `e[key] = rel` for png. Greps across all four consumer pages find zero reads of any of these; scenarios[].topics is explicitly excluded from search with a comment (index.html:900-902 "the batch-wide `topics` array is identical across every scenario"); png is only referenced as the static modes/simulated/preview.png og:image, never from the payload. holdout_withheld, also unread, is filed separately.
```
Proposed fix:
```diff
Documentation-only minimal fix — patientwords/CLAUDE.md, simulated_scenarios.json bullet, append:
+  Download-only fields no page reads (kept for the "full JSON" collaborator link):
+  `traced_by_model`, `traced.{mode,backend}`, `models_meta[].{graph_model,attention_replacement}`,
+  `batches[].generated.{max_spend_usd,rejection_reasons,topics,sidecar}`, `scenarios[].topics`,
+  `scenarios[].png`.
```
Verifier correction: Two minor corrections, neither affecting severity or fix. (1) The payload is fetched by five pages, not four: root index.html, start-here/index.html, share/card.html, simulated-scenarios/index.html, simulated-scenarios/scenario.html; all verified clean of the listed fields. (2) Missed propagation path: scripts/paired_stats_rigor.py:566 copies payload.models_meta wholesale into data/model_stats.json, whose embedded copy technical/index.html reads (lines 913, 1013-1024); but only the id/label/graphs/features subfields, so graph_model and attention_replacement remain unrendered while now existing in a second published file. The proposed CLAUDE.md documentation fix is safe as-is; any future actual pruning of models_meta subfields must prune or account for the model_stats.json copy too.
Found by: sim-scenarios-index,sim-scenarios-detail,global-sweep. Verified: CONFIRMED.

#### F-L16 · `engine:scripts/export_frontend_simulated.py:360` · unused-bloat

simulated_scenarios.json is written with indent=2, so 4,238,198 of its 7,142,083 bytes (59%) are indentation; fetched at page load by four pages (index, simulated-scenarios index + scenario, start-here).

Evidence:
```
Line 360: 'out_data.write_text(json.dumps(payload, indent=2) + "\n", ...)'. Measured: on-disk 7,142,083 B; identical payload compact via separators=(",",":") = 2,903,884 B. (The sibling writer urgency_shift.py already uses the tighter indent=1; this is the only multi-MB fetched-on-load file in data/.)
```
Proposed fix:
```diff
--- a/scripts/export_frontend_simulated.py
+++ b/scripts/export_frontend_simulated.py
@@ line 360
-out_data.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
+out_data.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")
(The simulated-scenarios page's 'full JSON' download link keeps working; if human-diffability on GitHub matters more than 4.2 MB per fetch, indent=1 recovers half the saving.)
```
Verifier correction: One severity framing correction: GitHub Pages serves gzip, and indentation compresses well; measured gzipped sizes are 674,651 B (indent=2) vs 469,892 B (compact), so the real over-the-wire saving is ~205 KB per page load (~30%), not 4.2 MB. The browser still allocates and JSON.parses the full 7.1 MB string, so the fix retains value (transfer + parse/memory), but the finding's raw-bytes framing overstates network impact. Severity 'low' is correct; proposed_fix is safe as written.
Found by: global-sweep. Verified: CONFIRMED.

#### F-L17 · `engine:scripts/export_jlens_depth.py:4` · doc-drift

export_jlens_depth.py docstring names 'start-here unit rows' as a consumer, but start-here/index.html fetches only urgency_shift.json and simulated_scenarios.json; the unit rows live on technical/ (and depth badges on simulated-scenarios/).

Evidence:
```
Docstring L3-5: 'into the single file the frontend's depth figures read (start-here unit rows, methods combined lens + causal figure)'. start-here/index.html L463-464 fetch list: ../data/urgency_shift.json and ../data/simulated_scenarios.json only; actual jlens_depth.json consumers are technical/index.html (L825, L1107), methods.html (L556), simulated-scenarios/index.html (L580).
```
Proposed fix:
```diff
- into the single file the frontend's depth figures read (start-here unit rows,
- methods combined lens + causal figure).
+ into the single file the frontend's depth figures read (technical/ census unit
+ rows, per-pair table and router; simulated-scenarios depth badges; methods
+ combined lens + causal figure).
```
Verifier correction: Minor wording nit in the proposed fix only: technical/ renders the unit-rows census (L1107, one SVG cell per pair) and the router table (L825); "per-pair table and router" slightly misdescribes the census. Tighter replacement docstring text: "into the single file the frontend's depth figures read (technical/ unit-rows census and router table, simulated-scenarios depth badges, methods combined lens + causal figure)."
Found by: technical-bundle. Verified: CONFIRMED.

#### F-L18 · `engine:scripts/fire_trigger.py:402` · other

update_dashboard_queue stamps `updated_by = "session"` unconditionally on every fire/resolve, stomping a "routine" stamp, while ledger_update.py deliberately uses setdefault to preserve it; the two writers disagree about the provenance convention on the same file.

Evidence:
```
fire_trigger.py line 402: `dashboard["updated_by"] = "session"` (unconditional). ledger_update.py line 242: `dashboard.setdefault("updated_by", "session")  # preserve e.g. "routine" when present`.
```
Proposed fix:
```diff
--- a/scripts/fire_trigger.py
+++ b/scripts/fire_trigger.py
@@ -402 +402 @@
-    dashboard["updated_by"] = "session"
+    dashboard.setdefault("updated_by", "session")  # match ledger_update.py: preserve e.g. "routine"
```
Verifier correction: Finding stands as written. Minor sharpening: the impact is stronger than a mere convention mismatch; because the daily Routine session itself invokes scripts/fire_trigger.py for fire/resolve (per ops/README.md queue row and docs/routine_standing_prompt.md), Routine-driven fires actively mislabel the dashboard write as "session", contradicting ops/README.md:41's documented semantics and the committed ops/dashboard.json value ("routine"). The mislabel persists until the Routine's step-6 dashboard rewrite. The proposed one-line setdefault fix is verified test-safe: tests/test_fire_trigger.py:66 seeds a dashboard with no updated_by key, so the assertion of "session" still passes.
Found by: wf-archive-ops. Verified: CONFIRMED.

#### F-L19 · `engine:scripts/fire_trigger.py:546` · other

Journal entries are created with `"commit": ""` and the field is never back-filled after the push, so ops/trigger_journal.jsonl (whose schema includes commit precisely for joining fires to pushes/Actions runs) carries empty commit fields for every scripted fire; only hand-edited early entries have one.

Evidence:
```
Line 546: `"commit": "",` in the entry dict; git_publish (lines 412-437) returns a bare bool and never surfaces the pushed SHA; the live journal shows `"commit": ""` on all recent entries (e.g. every 2026-07-16 entry) vs. hand-filled `"commit": "0755730"` on 2026-07-09.
```
Proposed fix:
```diff
--- a/scripts/fire_trigger.py
+++ b/scripts/fire_trigger.py
@@ -574,6 +574,10 @@
     if not args.no_git:
         if not git_publish(repo, [trigger_path, journal_path, repo / DASHBOARD_RELPATH],
                            f"Fire {args.trigger}: {args.note}"):
             print("fire written locally but git publish failed - resolve by hand", file=sys.stderr)
             return 1
+        head = _git(repo, "rev-parse", "--short", "HEAD")
+        if head.returncode == 0:
+            entry["commit"] = head.stdout.strip()
+            save_journal(journal_path, entries)
```
Verifier correction: Finding stands as written. Two corrections to the proposed_fix only: (1) It back-fills the journal AFTER git_publish, so the SHA-bearing journal entry is written locally but not committed/pushed; the published journal on GitHub keeps "commit": "" until the next fire's git add sweeps the change in, and the working tree sits dirty in between (risky given the repo's documented pull --rebase habits around trigger branches). This is inherent: a commit's SHA cannot appear inside that same commit, and amending would change the SHA. (2) The fix does not refresh ops/dashboard.json; update_dashboard_queue already ran at line 570 with the empty commit, so the dashboard's {fired_utc, commit, note} queue mirror stays empty; the fix should re-call update_dashboard_queue after setting entry["commit"] (dashboard.json is not committed by the Routine-owned path here, but fire_trigger already publishes it at line 574, so the same one-push-behind caveat applies). A cleaner alternative that avoids both caveats: record the pre-fire parent SHA (rev-parse --short HEAD BEFORE git_publish commits), which is knowable in advance, lands inside the fire commit itself, and still uniquely joins the fire to its push (the fire commit is parent+1); at the documented cost of being the parent rather than the fire commit.
Found by: wf-archive-ops. Verified: CONFIRMED.

#### F-L20 · `engine:scripts/jlens_insights.py:71` · silent-failure

collect() silently skips a landed-but-unreadable summary (OSError/JSONDecodeError -> continue), so a truncated committed part quietly shrinks the census with no warning anywhere.

Evidence:
```
L69-71: `try: summary = json.loads(part.read_text(encoding="utf-8"))\nexcept (OSError, json.JSONDecodeError): continue` — no message, no counter; a partially-committed or merge-mangled jlens_summary part just vanishes from n_pairs/taxonomy and the site figures regenerate smaller.
```
Proposed fix:
```
Log the skip so the nightly regen surfaces it:
```
except (OSError, json.JSONDecodeError) as err:
    print(f"WARNING: skipping unreadable {part}: {err}")
    continue
```
```
Verifier correction: Finding is accurate as filed. Minor refinements: (1) for consistency with the repo's existing warning style, emit to stderr and include the exception, e.g. `except (OSError, json.JSONDecodeError) as err: print(f"WARNING: skipping unreadable {part}: {err}", file=sys.stderr); continue` (daily_brief.py and dialect_invariant_core.py use stderr; ledger_update.py uses stdout; either works, nothing parses this script's output). (2) The identical silent-skip pattern also exists in scripts/retrace_consistency.py:36, scripts/drift_sentinel.py:36, and scripts/interp_analyses.py:33; the fix should be applied to all four collectors, since none of their outputs are count-checked by claim_check.py either.
Found by: wf-new-analyses. Verified: CONFIRMED.

#### F-L21 · `engine:scripts/jlens_readout.py:170` · fragile-parsing

The positional layer-numbering fallback engages silently (parse_status stays "ok"), so a hosted schema change in meta.layers_by_type would silently relabel every depth number shown on the site.

Evidence:
```
L169-171: `if not isinstance(layers, list) or len(layers) != len(per_layer): layers = list(range(len(per_layer)))  # positional fallback` — no marker is recorded; depth_profile returns status "ok" (L251). If Neuronpedia ever returns a layer subset or reordered meta, first_layer/formation/lock-in numbers shift silently through jlens_insights.py and export_jlens_depth.py onto technical/index.html and methods.html.
```
Proposed fix:
```
Surface the fallback in parse_status so consumers can filter:
```
# in depth_profile, before `return profile, "ok"`:
meta = response.get("meta") if isinstance(response, dict) else None
has_meta = isinstance(meta, dict) and isinstance(meta.get("layers_by_type"), dict)
return profile, "ok" if has_meta else "ok (positional layer numbering)"
```
(jlens_insights.collect's `any(v != "ok" ...)` filter then excludes fallback rows rather than mislabeling them.)
```
Verifier correction: The proposed fix is wrong in three ways: (1) its has_meta check (layers_by_type is a dict) does not match the actual fallback condition; in the length-mismatch case (exactly the one pinned by test_confirmed_schema_layer_numbers_fall_back_positional_on_meta_mismatch, meta {"JACOBIAN_LENS": [5]} vs 2 layers) layers_by_type IS a dict, so the fix would still return plain "ok" while the fallback engaged; (2) when entries come from the legacy _iter_layer_entries path (explicit layer numbers, no meta), the fix would falsely label real layer numbers as positional; (3) it breaks the pinning test, and export_jlens_depth.py remains unprotected since it never reads parse_status. Correct fix: signal the fallback where it occurs; have _layer_entries_from_results expose a positional flag (e.g. yield entries and set a caller-visible marker), have depth_profile return a distinct status like "ok (positional layer numbering)" only when that flag fired, update the pinning test to the new status, and add a parse_status (or at minimum a loud stderr) check in export_jlens_depth.build_block/build_payload. Side effect to state explicitly: jlens_insights.collect and translation_scale._lens_profiles will then EXCLUDE fallback rows (any v != "ok"), which is the finder's stated intent but is a data-coverage change, not just a label.
Found by: wf-new-analyses. Verified: CONFIRMED.

#### F-L22 · `engine:scripts/jlens_readout.py:349` · silent-failure

An offset at/past the end of the batch yields an empty chunk and a green run that lands an empty jlens_summary part plus a probe claiming pairs_measured=0; a mistyped chunk fire looks successful.

Evidence:
```
L349: `chunk = pairs[args.offset:args.offset + args.limit] if args.limit else pairs[args.offset:]` — an out-of-range offset slices to []; the loop body never runs, L395-401 still write `jlens_summary.part_NN.json` with `"results": []` and `probe = {..., "supported": True, "pairs_measured": 0}`, exit 0. (activation_patch.py load_pairs L88-93 has the same empty-chunk pass-through.)
```
Proposed fix:
```
After slicing:
```
if not chunk:
    raise SystemExit(f"offset {args.offset} is beyond the {len(pairs)}-pair batch - nothing to read")
```
(and the analogous guard after load_pairs in activation_patch.py main).
```
Verifier correction: The finding understates one consequence: with an empty chunk the script makes zero endpoint POSTs, yet still writes jlens_probe.json claiming supported: true; and the workflow's commit step merges the shared jlens_probe.json last-writer-wins (git pull --rebase -X theirs, jlens_readout.yml L209-214), so a mistyped chunk fire can overwrite a genuine probe result with an untested vacuous one. Corrected fix (same as proposed, with a message covering both scripts): in jlens_readout.py after L349 `if not chunk: raise SystemExit(f"offset {args.offset} is at/past the end of the {len(pairs)}-pair batch - nothing to read")`; in activation_patch.py after main's load_pairs call (L415) `if not pairs: raise SystemExit(f"start-index {args.start_index} is past the end of the batch - nothing to patch")` (guard main, not load_pairs itself, so the message can name the CLI flag). Severity low is fair; line 349 and the activation_patch L88-93 citation are both accurate.
Found by: wf-new-analyses. Verified: CONFIRMED.

#### F-L23 · `engine:scripts/ledger_update.py:238` · silent-failure

The deliberate ledger-append-before-dashboard ordering has an unhandled inverse: if append_ledger succeeds and write_dashboard then fails, entries_seen is not committed, so the next run re-scans the same sidecars and appends duplicate bullets to the spend log.

Evidence:
```
Lines 236-243: `if bullets: append_ledger(ledger_path, bullets)` precedes `write_dashboard(dashboard_path, dashboard)`; the module docstring promises only 'bullets are never lost' — nothing dedupes on re-append, and a crash between the two writes leaves the ledger ahead of entries_seen.
```
Proposed fix:
```diff
--- a/scripts/ledger_update.py
+++ b/scripts/ledger_update.py
@@ -181,4 +181,7 @@
 def append_ledger(path: Path, bullets):
     text = path.read_text(encoding="utf-8") if path.exists() else DEFAULT_LEDGER_HEADER
+    bullets = [b for b in bullets if b not in text]  # re-run after a partial failure: skip bullets already landed
+    if not bullets:
+        return
     if text and not text.endswith("\n"):
```
Verifier correction: Corrected statement: if append_ledger succeeds and write_dashboard then fails (crash, disk error, SIGKILL between lines 238 and 243), entries_seen is never committed, so the next run re-scans the same sidecars and appends duplicate bullets to the spend-log markdown. Spend numbers themselves are not double-counted; the dashboard increments are lost together with entries_seen; so this is cosmetic ledger noise plus a violated implicit uniqueness expectation, severity low. Corrected fix (whole-line dedup instead of substring, plus docstring update): in append_ledger, after reading `text`, compute `existing = set(text.splitlines())` and filter `bullets = [b for b in bullets if b not in existing]`; return early if empty. Substring matching (`b not in text`) as proposed could false-positive if one bullet line ever embeds another; line-set matching cannot. Also amend the module docstring line 'bullets are never lost' to add 'and re-appends after a partial failure are deduplicated by exact line', and add a regression test: run once, simulate write_dashboard failure (monkeypatch to raise), run again, assert each bullet appears exactly once and dashboard totals count each sidecar once.
Found by: wf-archive-ops. Verified: CONFIRMED.

#### F-L24 · `engine:scripts/logits_eval.py:11` · doc-drift

The module docstring promises the graph-only fields 'are null', but clinical_mass, error_share, top_path and outputs are omitted entirely (only circuit_diff and screening are explicit nulls, and the tracer omits the screening key rather than nulling it); the merge only survives because both consumers happen to use .get() for every one of these keys - any future consumer indexing them per the stated 'same schema' contract breaks on logits parts only.

Evidence:
```
scripts/logits_eval.py:11-13 docstring: "there is no feature attribution (clinical_mass) and no circuit render - those fields are null"; build_result (:116-128) contains no clinical_mass/error_share/top_path/outputs keys at all, while emitting `"screening": None` where evaluate_pair emits no screening key outside --screen-targets runs (batch_eval.py:601 `result_screening = {"screening": screening} if screening else {}`). Current consumers tolerate it: export_frontend_simulated.py:168-170 `r.get("screening")` / `r.get("circuit_diff")` / `r.get("clinical_mass") if featured else None`; urgency_shift.py:175/180 `r.get("predictive_spread")` / `r.get("continuations")`.
```
Proposed fix:
```diff
Either fix the docstring to state the real contract:
-no circuit render - those fields are null and the model's chip greys the
+no circuit render - clinical_mass/error_share/top_path/outputs are omitted
+entirely (consumers must .get() them; circuit_diff and screening are explicit
+nulls) and the model's chip greys the
or emit the keys as explicit nulls in build_result for byte-level schema parity:
+        "clinical_mass": None, "error_share": None, "top_path": None,
         "circuit_diff": None,   # no graph -> no circuit diff
```
Verifier correction: Finding is accurate but understates its own support: beyond the two cited consumers (export_frontend_simulated.py:168-170, urgency_shift.py:~175-185), logits parts are also read by export_archive.py:128/133, retrace_consistency.py:50-52, interp_analyses.py:51/149, screen_sensitivity.py, translation_scale.py, and drift_sentinel.py; all likewise .get()-guarded, so the "same schema by convention, not contract" defect applies to ~8 consumers, not 2. Note also that CLAUDE.md's "emitting the same batch_summary schema" line carries the same drift. On the proposed alternate fix: the added-nulls diff should also include "outputs": None for the parity it claims (retrace_consistency.py:50 reads outputs), and true parity on screening would mean omitting the key rather than emitting None; the docstring-rewrite option is the cleaner fix and breaks nothing. Severity low / doc-drift is correct.
Found by: wf-logits. Verified: CONFIRMED.

#### F-L25 · `engine:scripts/logits_eval.py:165` · silent-failure

A model id containing '/' (explicitly allowed: 'short model id ... or a Hugging Face repo id') makes the workflow's OUT_DIR nest one directory deeper (trace_out/<stem>__<org>/<repo>/), where every consumer's single-level glob never looks - the part file commits green and is invisible to urgency_shift and the exporter forever.

Evidence:
```
scripts/logits_eval.py:165 `hf_id = HF_IDS.get(model_id, model_id)` with help text "or a Hugging Face repo id" (:151); logits_evaluation.yml:144 `echo "OUT_DIR=trace_out/${STEM}__${MODEL}" >> "$GITHUB_ENV"` - MODEL="meta-llama/Llama-3.2-3B" yields trace_out/pairs_X__meta-llama/Llama-3.2-3B/. Consumers glob exactly one level: urgency_shift.py:160 `glob.glob("trace_out/*/batch_summary.part_*.json")` and export_frontend_simulated.py:122 `ENGINE / f"trace_out/{stem}__{model}"` keyed by the short id. The commit step (yml:169) still `git add -f`s the nested path successfully, so the run is green end-to-end while the data is unreachable.
```
Proposed fix:
```diff
Reject slashed ids in the params step (after the models list is built, logits_evaluation.yml heredoc, after line 91):
           models = [m.strip() for m in p["models"].replace(",", " ").split() if m.strip()]
+          bad = [m for m in models if "/" in m]
+          if bad:
+              raise SystemExit(f"model ids must be short registry ids from HF_IDS (no '/'): {bad}")
           if not models:
```
Verifier correction: One evidence overstatement: export_frontend_simulated.py:122 misses the data only under the default invocation (--models defaults to the hardcoded MODELS list, :48/:69). If an operator passed the same slashed id via --models, the f-string `trace_out/{stem}__{model}` resolves to the identical nested path and the exporter WOULD read it; though the model would still get no models_meta entry (built from the hardcoded MODELS list at :345) and hence no frontend chip. The unconditional silent losses are urgency_shift.py and the other single-level-glob collectors (study_timeline, interp_analyses, retrace_consistency, screen_sensitivity). Proposed fix stands as written (reject slashed ids in the params heredoc after yml line 91); optionally also validate `args.model in HF_IDS or "/" not in args.model` is NOT needed in logits_eval.py itself, since local runs pass --out explicitly.
Found by: wf-logits. Verified: CONFIRMED.

#### F-L26 · `engine:scripts/paired_stats_rigor.py:566` · mismatched-keys

model_stats.json models_meta covers only 4 of 8 per_model ids (it is copied from the exporter payload, which lists traced models only); the ev-table's Measurement/Circuit-features columns for the other four render correct text only because missing-meta defaults coincide with graphs:false/features:false.

Evidence:
```
L563-566: payload = json.loads(payload_path.read_text(...)); site_bundle["models_meta"] = payload.get("models_meta") — live instance has models_meta ids ['gemma-2-2b','gemma-3-4b-it','qwen3-4b','qwen3-1.7b'] against per_model's 8 models. Page L1013+L1023: var m=meta[id]||{}; td(null,m.graphs?'hosted attribution graphs':'CPU next-token behavior only'); — for gemma-2-2b-it/llama-3.2-3b/medgemma-4b-it/olmo-2-1b the label is right by accident of the undefined→falsy default, not by contract.
```
Proposed fix:
```diff
@@ scripts/paired_stats_rigor.py main(), after the except block (L567-568)
         except (OSError, ValueError):
             site_bundle["models_meta"] = None
+        known = {m.get("id") for m in (site_bundle["models_meta"] or [])}
+        site_bundle["models_meta"] = (site_bundle["models_meta"] or []) + [
+            {"id": m, "label": m, "graphs": False, "features": False,
+             "note": "behavioral (logits) measurement; not in exporter payload"}
+            for m in site_bundle["models"] if m not in known]
```
Verifier correction: Two corrections. (1) Evidence wording: the exporter's models_meta does NOT list 'traced models only'; it lists models present in the exported scenario payload (export_frontend_simulated.py L328-347 filters MODELS by presence in scenarios; qwen3-4b/qwen3-1.7b are in meta with graphs:false). The 4 missing models are absent because their measurements come from batches not included in the site scenario export, reaching per_model via urgency_shift rows. Cosmetic addendum: the page's model-name cell (L1017, m.label||id) also falls back to the raw id for these rows. (2) Fix scope: the proposed patch is safe for the only consumer of model_stats.json models_meta (technical/index.html reads just label/graphs/features, and synthetic graphs:false/features:false entries render identically to today's falsy defaults), but it should synthesize only when models_meta loaded as a list; as written it also runs on the payload-read-failure path (models_meta=None), replacing None with an all-synthetic list that stamps gemma-2-2b graphs:false plus a 'behavioral (logits) measurement' note, storing actively wrong metadata for the one graphs-capable model and going against the documented 'None when the payload is absent' semantics (tests/test_paired_stats_rigor.py L190). I.e. guard with: if site_bundle["models_meta"] is not None: known = {...}; site_bundle["models_meta"] += [synthetic entries for m in site_bundle["models"] if m not in known].
Found by: technical-bundle. Verified: CONFIRMED.

#### F-L27 · `engine:scripts/patch_aggregate.py:90` · doc-drift

"term_adjacent" is implemented as the first PATCHED column, but the payload's term_adjacent_rule claims "first aligned position after the divergent span"; a chunk run with --positions restricting columns silently shifts the site-facing split.

Evidence:
```
L89-90: `cols = patched_columns(grid); first = cols[0]` — patched_columns reflects only cells that carry values, and activation_patch.py's `--positions` intersects the patched columns with the aligned suffix (activation_patch.py L353: `columns = sorted(aligned if positions is None else set(positions) & set(aligned))`), so a positions-restricted run makes `first` a later position than the rule states; payload L140-141 hardcodes: `"term_adjacent_rule": ("first aligned position after the divergent span; the swapped span itself is never patchable")`.
```
Proposed fix:
```
Derive `first` from the recorded alignment instead of the patched columns:
```
aligned = [pos["index"] for pos in p.get("positions", [])
           if isinstance(pos, dict) and pos.get("aligned_clean_index") is not None]
cols = patched_columns(grid)
first = min(aligned) if aligned else cols[0]
```
```
Verifier correction: Finding stands as written (severity low, doc-drift). Two refinements: (1) impact scoping; no landed run has ever used a positions restriction (ops/trigger_journal.jsonl, current .github/trigger/activation-patching.json), so the published data/patch_profile.json in both repos is unaffected; the defect only bites future --positions chunks, which then merge silently with unrestricted chunks in the same stem. (2) The proposed fix is correct and backward-compatible, with one behavioral consequence worth documenting: a restricted run that excludes the first aligned position will yield term_adjacent_best = null and classify its best cell as downstream, which matches the stated rule; the `else cols[0]` fallback only fires for legacy parts lacking positions metadata. Add a regression test with a positions-restricted grid (first aligned column all-None, later columns valued) pinning first = min(aligned).
Found by: wf-new-analyses. Verified: CONFIRMED.

#### F-L28 · `engine:scripts/patch_aggregate.py:149` · unused-bloat

Deepened orphan: the site copy of patch_profile.json is dead weight, not a not-yet-built page; the activation-patching story already reaches the site through jlens_depth.json's exemplar (methods.html causal-patch lane), which export_jlens_depth.py builds directly from trace_out patch grids, and nothing (page, claims manifest, frontend doc) references the site patch_profile path.

Evidence:
```
patch_aggregate.py:149-152 'if args.site: site = Path(args.site) / "data" / "patch_profile.json"; site.write_text(...)'. No frontend fetch ('patch_profile' absent from all *.html/*.md in patientwords), no claims_manifest source entry. The rendered patch figure is methods.html:556 fetch('data/jlens_depth.json') → :597-621 reading ex.patched/ex.clean_prob; the exemplar's patched array is produced by export_jlens_depth.py:74-89 ('path = Path("trace_out") / f"{stem}__patch" / f"batch_summary.part_{index:02d}.json"') and :238 '"patched": patched' — patch_profile.json is bypassed. Engine docs cite only the engine copy (findings_synthesis_DRAFT_20260713.md:90 'data/patch_profile.json, exploratory, 7 usable downgrade pairs').
```
Proposed fix:
```diff
--- a/scripts/patch_aggregate.py
+++ b/scripts/patch_aggregate.py
@@
-    parser.add_argument("--site", default="", help="frontend repo root; '' skips the site copy")
@@
-    if args.site:
-        site = Path(args.site) / "data" / "patch_profile.json"
-        site.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
-        print(f"site copy -> {site}")
(keep the engine-side data/patch_profile.json for the findings docs; separately delete patientwords/data/patch_profile.json, or if a technical-page fold is actually planned, add the fetch + a claims-manifest entry instead)
```
Verifier correction: File as a deepening/amendment of the accepted prior 'patch_profile.json is fetched by no page', not a standalone new finding. The proposed diff is safe (no caller passes --site; tests untouched) but incomplete in one spot: also update the module docstring usage line at scripts/patch_aggregate.py:23, which documents '[--site ../patientwords]' and would go stale after removing the flag. Keep the engine-side data/patch_profile.json (referenced by docs/findings_synthesis_DRAFT_20260713.md:90 and :215); delete patientwords/data/patch_profile.json in a separate frontend commit, or if a technical-page fold is planned, add the fetch plus a claims-manifest source entry instead. Severity low / unused-bloat is correct.
Found by: small-pages. Verified: CONFIRMED.

#### F-L29 · `engine:scripts/translation_scale.py:171` · unused-bloat

translation_scale.json ships five fields no consumer reads: per_model.median_recovery, per_model.n_with_headroom, per_model.mean_gap_closed, top-level corpora[], and lens_recovery.formed_both; the translation page reads only n/mean_recovery/share_recovery_positive/top_restored/top_lost + three lens counts, and the claims manifest has no translation_scale entries (dialects.json has the same in miniature: payload.source_set is read by no page or claim).

Evidence:
```
Writer translation_scale.py:171-181 emits '"median_recovery": round(statistics.median(recs), 4), ... "n_with_headroom": len(gaps), "mean_gap_closed": (round(statistics.fmean([...]), 4) if gaps else None)' and :190 '"corpora": [c.stem for c in corpora]', :122-123 '"formed_both": sum(...)'. Sole page consumer translation/index.html:325-329 reads only 'td(\'num\',String(s.n)); td(\'num\',pp(s.mean_recovery)); td(\'num\',Math.round(s.share_recovery_positive*100)+\'%\'); td(\'num\',String(s.top_restored)); td(\'num\',String(s.top_lost));' and :343-345 only patient_never_formed/recovered_to_formed/lost_by_translation. grep of claims_manifest.json: no source 'data/translation_scale.json'.
```
Proposed fix:
```diff
Either surface the strongest unused stat (gap closed is the headline of the writer's own docstring) or drop the site-copy fields. Minimal wiring diff:
--- a/translation/index.html
+++ b/translation/index.html
@@
         <th scope="col" class="num">Helped</th>
+        <th scope="col" class="num">Gap closed</th>
@@
           td('num',Math.round(s.share_recovery_positive*100)+'%');
+          td('num',s.mean_gap_closed==null?'—':Math.round(s.mean_gap_closed*100)+'%');
(otherwise: add data/translation_scale.json entries to data/claims_manifest.json so claim_check pins them, or stop emitting the fields in the --site copy)
```
Verifier correction: Two corrections. (1) Line cite: the per-model summary dict opens at scripts/translation_scale.py:169; the unused fields sit at 172-181 (median_recovery 172, n_with_headroom 174, mean_gap_closed 175-177), corpora at 190, formed_both at 122-123. (2) The third fix option ("stop emitting the fields in the --site copy") is unsafe as stated: the site copy is a verbatim json.dumps of the same `result` dict written to ops/translation_scale.json (main() lines 205 and 218), the writer's own stdout prints mean_gap_closed (line 209), tests/test_translate_corpus.py:104 asserts mean_gap_closed, and the ops copy is a standing input to the daily Routine (docs/routine_standing_prompt.md:131); so dropping the fields from analyze() breaks the regression test and the print, and pruning only the site copy requires new divergence logic. Prefer the first two options: surface mean_gap_closed on the translation page (the proposed th/td diff is safe; the tx-scale table at translation/index.html:242-251 is a plain 6-column table, no colspans, and the new number traces to a fetched data field per the frontend hard rule) and/or add data/translation_scale.json entries to the claims manifest so claim_check pins the values.
Found by: small-pages. Verified: CONFIRMED.

#### F-L30 · `engine:scripts/urgency_shift.py:197` · silent-failure

The site-payload fill loop checks `seen` but never adds to it, so a malformed scenarios export containing duplicate (batch,batch_index) entries would emit duplicate batch#index#model row triples that the frontend's urgMap then silently last-write-wins (simulated-scenarios/index.html:594); the live file is currently clean (3759 rows, 3759 distinct triples) and scenarios have 0 duplicate keys, so this is latent hardening, not an active defect.

Evidence:
```
Lines 195-203: `for s in payload.get("scenarios", []): for mid, m in (s.get("models") or {}).items(): if (mid, s.get("batch"), s.get("batch_index")) in seen: continue; add(mid, ...)` — no `seen.add(...)` after a row lands, unlike the trace_out loop which does `seen.add((model, stem, r["index"]))` at line 190. Consumer side has no duplicate detection: line 594 `urgMap[u.batch+'#'+u.index+'#'+u.model]=u;` overwrites silently.
```
Proposed fix:
```diff
--- a/scripts/urgency_shift.py
+++ b/scripts/urgency_shift.py
@@ -198,6 +198,9 @@
-            add(mid, s.get("batch"), s.get("batch_index"),
+            n_before = len(rows)
+            add(mid, s.get("batch"), s.get("batch_index"),
                 {"clinical": s.get("clinical_prompt")},
                 m.get("spread_clinical"), m.get("spread_patient"),
                 topic=s.get("topic") or topics.get((s.get("batch"), s.get("batch_index"))),
                 penalty=m.get("language_penalty"))
+            if len(rows) > n_before:
+                seen.add((mid, s.get("batch"), s.get("batch_index")))
```
Verifier correction: Two refinements, neither changing the verdict: (1) Impact is understated on the engine side and slightly overstated on the frontend side. Duplicate payload scenarios would be identical objects, so urgMap's last-write-wins at index.html:594 is cosmetically benign; the real damage is upstream in urgency_shift.py itself, whose row-level aggregates (summary at lines 218-230: measurements, flips, flip_classes, mean_tier_shift, and the exact sign test) would double-count duplicated rows before publication. Partial downstream mitigation the finder missed: paired_stats_rigor.py dedupes by (model, clinical_prompt) (dedupe_by_phrase, line 112), so claim-grade phrase-level stats would collapse the duplicates; but row-level counts and the published rows array would not. (2) The realistic trigger is a duplicated stamp in export_frontend_simulated.py's --stamps argument (line 94, no dedup) rather than an arbitrary "malformed export"; a complementary one-line hardening would be deduplicating STAMPS in the exporter. The proposed seen.add fix is correct and safe as written.
Found by: urgency-shift. Verified: CONFIRMED.

#### F-L31 · `engine:scripts/urgency_shift.py:367` · unused-bloat

rows[].urgency_recovery is emitted on every published row (null on 3676 of 3759) yet read by no consumer anywhere (no page, no engine site-copy reader, no claims-manifest expr); summary.mitigation, summary.concordance, summary.measurements, and all summary.per_model value fields are likewise unread from the site copy (only per_model's key list, per_model_deduped counts, flips, flip_classes.downgrade/upgrade, tiers, tier_examples, vocabulary_status, and 5 row keys are load-bearing).

Evidence:
```
Lines 367-369 include "urgency_recovery" in the trimmed key tuple with `r.get(k)`, materializing `"urgency_recovery": null` 3676 times. `grep -rln 'urgency_recovery|mean_urgency_recovery|restored_top_tier|concordance' /home/user/audit-wb/patientwords --include=*.html` returns nothing; engine site-copy readers (specialty_breakdown.py:31-33, coverage_gaps.py:38-40) touch only batch/index/model/flip_class/tier_top_clinical; claims_manifest exprs touch only vocabulary_status.
```
Proposed fix:
```diff
--- a/scripts/urgency_shift.py
+++ b/scripts/urgency_shift.py
@@ -367,4 +367,10 @@
-    trimmed = [{k: r.get(k) for k in ("batch", "index", "model", "tier_top_clinical",
-                                      "tier_top_patient", "flip_class", "tier_shift",
-                                      "urgency_recovery")}
-               for r in pub_rows if r["flipped"] or r.get("tier_shift") is not None]
+    def _trim(r):
+        t = {k: r.get(k) for k in ("batch", "index", "model", "tier_top_clinical",
+                                   "tier_top_patient", "flip_class", "tier_shift")}
+        if r.get("urgency_recovery") is not None:
+            t["urgency_recovery"] = r["urgency_recovery"]
+        return t
+    trimmed = [_trim(r) for r in pub_rows
+               if r["flipped"] or r.get("tier_shift") is not None]
```
Verifier correction: Two misstatements, neither fatal. (1) "read by no consumer anywhere" is overstated for the field as such: scripts/export_jlens_depth.py:140-148 (translation_split, default rows_path="urgency_shift.json") reads rows[].urgency_recovery; but from the ENGINE-ROOT full row file (urgency_shift.py --out default, 4858 rows, 94 non-null), not from the site copy; convergence_tracker.py, paired_stats.py, and paired_stats_rigor.py likewise read the full file. So urgency_recovery is a live field engine-side; only its copy in the published data/urgency_shift.json rows is dead. The finder's scoped parenthetical (no page, no engine site-copy reader, no claims-manifest expr) is exactly right. (2) "5 row keys are load-bearing" undercounts: 7 of the 8 trimmed keys are read (batch, index, model as the join key; flip_class, tier_top_clinical, tier_top_patient, tier_shift for badges and sorting); urgency_recovery is the only dead one. The proposed diff is safe as written and would also keep the 83 non-null values available; a companion cleanup could drop "measurements", "concordance", and "mitigation" from the site summary dict at urgency_shift.py:400-403 and reduce per_model to its keys or a model list, but per_model itself must not be removed outright (index.html:658 derives the model count/gate from Object.keys(per_model)). Severity low / unused-bloat is appropriate.
Found by: urgency-shift. Verified: CONFIRMED.

#### F-L32 · `engine:scripts/urgency_shift.py:369` · unused-bloat

The published site copy of urgency_shift.json carries rows[].urgency_recovery (109,071 bytes at indent=1, non-null in only 83 of 3,759 rows) plus summary.concordance/mitigation/measurements (3,693 bytes); none of which any page or claims-manifest expr reads.

Evidence:
```
Publish block trims rows to the tuple at lines 367-369: ("batch", "index", "model", "tier_top_clinical", "tier_top_patient", "flip_class", "tier_shift", "urgency_recovery") and the summary allowlist at lines 400-402 includes "measurements", "concordance", "mitigation". Site read set (all four consumer pages walked): rows[].{batch,index,model,flip_class,tier_top_clinical,tier_top_patient,tier_shift}, summary.{flips,flip_classes,per_model,per_model_deduped}, tiers, tier_examples, vocabulary_status. Claims manifest touches only vocabulary_status. The engine-side consumer of urgency_recovery (export_jlens_depth.py translation_split, line 127 default rows_path="urgency_shift.json") reads the engine-root full rows file, not the site copy; the site's translation-recovery story is served by data/translation_scale.json instead.
```
Proposed fix:
```diff
--- a/scripts/urgency_shift.py
+++ b/scripts/urgency_shift.py
@@ lines 367-369
     trimmed = [{k: r.get(k) for k in ("batch", "index", "model", "tier_top_clinical",
-                                      "tier_top_patient", "flip_class", "tier_shift",
-                                      "urgency_recovery")}
+                                      "tier_top_patient", "flip_class", "tier_shift")}
@@ lines 400-402
-        "summary": {k: summary[k] for k in ("measurements", "flips", "flip_classes",
-                                            "per_model", "per_model_deduped",
-                                            "concordance", "mitigation")
+        "summary": {k: summary[k] for k in ("flips", "flip_classes",
+                                            "per_model", "per_model_deduped")
                     if k in summary},
```
Verifier correction: Minor corrections only. (1) The trim tuple spans lines 367-370 and the summary allowlist lines 400-403 (the finding's 367-369/400-402 omit the closing lines). (2) The summary-trio size is ~3.5 KB by direct measurement (3,517 bytes wrapping each key at indent=1) vs the claimed 3,693; same order, measurement-method dependent. (3) The evidence should note two additional consumers of the SITE copy that the finder missed but that are unaffected: engine scripts/coverage_gaps.py:82 and scripts/specialty_breakdown.py:82 read the site data/urgency_shift.json rows using only {batch,index,model,flip_class,tier_top_clinical}; the proposed fix must keep those five row keys (it does). Proposed fix is otherwise safe as written; tests/test_tierb_split.py's '"measurements": len(arows)' tripwire targets summary construction, not the publish allowlist, so no test changes are needed.
Found by: global-sweep. Verified: CONFIRMED.

#### F-L33 · `engine:scripts/urgency_shift.py:370` · unused-bloat

The --publish path ships every trimmed row regardless of whether it can ever join: 770 of 3759 live rows (20.5%) have a (batch,index) matching no scenario in simulated_scenarios.json (286 permanently; diagnostic stems like boostgrid_*, repeatability_r*, drift_sentinel_*, featured_sim85*, urgency_downgrades_*_steer, ci_pairs_2panel), and 605 more belong to models absent from models_meta, so 1375 rows (36.6% of an 849 KB public file) are dead weight for every row-level consumer (frontend urgMap/redirect gallery/start-here, engine specialty_breakdown/coverage_gaps).

Evidence:
```
Lines 367-370: `trimmed = [{k: r.get(k) for k in (...)} for r in pub_rows if r["flipped"] or r.get("tier_shift") is not None]` — no batch/model filter. Probe of the live files: scenario batches = 14 pairs_ stamps; row batches include 'boostgrid_lowrank', 'repeatability_r1..r3', 'drift_sentinel_2026071{3,4,5,6}', 'featured_sim85', 'imported_pairs', 'urgency_downgrades_20260707T1_steer', 'pairs_20260711T051145Z_txopus/_txplacebo' etc.; `rows with no matching scenario (batch,index): 770`. Row models include gemma-2-2b-it/llama-3.2-3b/medgemma-4b-it/olmo-2-1b (611 rows) while models_meta and every scenario.models map contain only 4 ids, so simulated-scenarios' `urgFor(s)` key `s.batch+'#'+s.batch_index+'#'+currentModel` (line 596) can never select them (they legitimately feed only summary aggregates).
```
Proposed fix:
```diff
--- a/scripts/urgency_shift.py
+++ b/scripts/urgency_shift.py
@@ -364,7 +364,15 @@
     if len(pub_rows) != len(rows):
         print(f"holdout withheld from site copy: {len(rows) - len(pub_rows)} rows "
               f"({len(_holdout_phrases)} phrases)")
+    # publish only rows a consumer can join: rows for exported scenarios, rows
+    # from stamped pairs_ batches (may land in the next scenarios export), and
+    # mitigation rows (urgency_recovery is their only public record)
+    scen_keys = ({(s.get("batch"), s.get("batch_index")) for s in payload.get("scenarios", [])}
+                 if site.is_file() else set())
+    _stamped = re.compile(r"pairs_\d{8}T\d{6}Z$")
     trimmed = [{k: r.get(k) for k in ("batch", "index", "model", "tier_top_clinical",
                                       "tier_top_patient", "flip_class", "tier_shift",
                                       "urgency_recovery")}
-               for r in pub_rows if r["flipped"] or r.get("tier_shift") is not None]
+               for r in pub_rows
+               if (r["flipped"] or r.get("tier_shift") is not None)
+               and ((r["batch"], r["index"]) in scen_keys
+                    or _stamped.fullmatch(r["batch"] or "")
+                    or r.get("urgency_recovery") is not None)]
```
Verifier correction: Finding stands as written, with two fix-characterization corrections. (1) Yield mismatch: simulated against the live files, the proposed filter drops only 218 of the 1375 dead rows (~5.8% of rows, not 36.6%) because it deliberately retains the 605 off-meta-model rows (their (batch,index) keys ARE in scen_keys, and a future export could add those models to models_meta) and the 484 stamped-pairs_ rows that may land in the next scenarios export. The 36.6% figure correctly sizes the defect but not the fix's reclamation; if the owner wants the full reclaim, the filter must also require r["model"] to be in the exported models_meta ids; at the cost of re-adding those rows only after such an export. (2) The fix drops 18 imported_pairs rows; no page joins them today (simulated-scenarios joins only pairs_-stamped scenario batches), but the filter would need an imported_pairs carve-out if the phrase-dataset page ever gains urgency badges. Also note some nomatch rows belong to partially-exported stamped batches (e.g. 4 rows of pairs_20260710T050657Z with indices beyond the exported scenarios); the stamp fallback correctly keeps these.
Found by: urgency-shift. Verified: CONFIRMED.

#### F-L34 · `site:CLAUDE.md:46` · doc-drift

holdout_withheld is emitted by the exporter but undocumented everywhere the contract lives: the frontend CLAUDE.md's simulated_scenarios.json bullet, the engine CLAUDE.md's Publishing paragraph, and the simulated-scenarios page prose all omit it (methods.html:504 and technical/ pages do disclose the withholding; the page whose accepted-count arithmetic it affects does not). A maintainer reconciling batch accepted counts against payload rows has no documented explanation for the 62-row gap.

Evidence:
```
patientwords/CLAUDE.md lines 46-52 (the simulated_scenarios.json contract bullet) list models/models_meta/archive but not holdout_withheld; patientwords-engine/CLAUDE.md line 122 'Publishing (scripts/export_frontend_simulated.py)' paragraph does not mention the holdout gate; `grep -rni 'holdout|withheld' patientwords/**/*.html` hits only methods.html:504 and technical/index.html:386,457,647 — nothing under simulated-scenarios/. Writer: export_frontend_simulated.py:212-219 (gate) and :352 (emission).
```
Proposed fix:
```diff
patientwords/CLAUDE.md, end of the simulated_scenarios.json bullet (after line ~52), add:
+  Top-level `holdout_withheld` counts confirmatory-holdout pairs the exporter excludes
+  from `scenarios` (sealed Tier B); any accepted-vs-traced arithmetic must subtract it.
patientwords-engine/CLAUDE.md, Publishing paragraph (line 122), add after 'caps public interactive renders...':
+  withholds confirmatory-holdout pairs (tierb_split.py rule) and records the count as top-level `holdout_withheld`.
```
Verifier correction: Category is doc-drift plus a live on-page misstatement. Corrected summary: holdout_withheld (currently 62) is emitted by export_frontend_simulated.py (gate :211-219, emission :352) but is undocumented in both CLAUDE.md data contracts and; more importantly; is ignored by simulated-scenarios/index.html:1148-1154, whose trace-progress line computes sum(batches[].generated.accepted) − scenarios.length (835 − 751 = 84) and labels the whole difference 'still tracing'; 62 of those rows are permanently withheld holdout pairs, so the rendered number is wrong today, not merely unexplained. Corrected fix: (1) apply the finder's two CLAUDE.md additions as proposed (safe, doc-only); (2) in simulated-scenarios/index.html, subtract the withheld count in the still-tracing arithmetic with a fallback for older payload shapes, e.g. var withheld = payload.holdout_withheld || 0; var pending = accepted - scenarios.length - withheld; render the 'still tracing' line only when pending > 0, and (per methods.html/technical disclosure) optionally note the withheld count separately in the provenance line. The fallback (|| 0) preserves behavior for payloads lacking the field, satisfying the documented graceful-degradation contract; no other consumer reads this computed value, so the change is isolated.
Found by: sim-scenarios-index. Verified: CONFIRMED.

#### F-L35 · `site:data/model_provenance.json:2` · doc-drift

model_provenance.json is hand-authored by design (no writer on the branch; its top-level 'note' declares maker/release-month recorded 'for era transparency only'), but this is undocumented in the frontend data contract, nothing validates coverage of newly measured models (a per_model id absent here silently renders with no maker/spec line), and its three claude-* generator entries are rendered by no consumer.

Evidence:
```
File top: "note": "Maker and release month from each maker's public announcement; ... Recorded for era transparency only, not as a comparison of quality. A null release means the month was not verified at writing time...". grep across engine scripts/, workflows, ops/, docs/ finds no writer. Sole consumer technical/index.html L901-905 fetches it; L996 guards if(pv&&pv.maker) so a missing entry degrades to a blank provenance line; entries claude-haiku-4-5/claude-sonnet-5/claude-opus-4-8 are in none of per_model ∪ below_floor ∪ excluded, so they render nowhere.
```
Proposed fix:
```diff
Add to patientwords/CLAUDE.md 'Data contracts' list:
+ - `data/model_provenance.json` — hand-authored era-transparency record (no engine
+   writer, by design; see its top-level `note`). `technical/` Part 4 reads
+   `models[<id>].maker/released/spec/excluded`; keep an entry for every model that
+   enters `model_stats.json:per_model`. The claude-* entries are reserved for
+   generator credit and are currently rendered nowhere.
Optionally add a per_model⊆models coverage check to scripts/claim_check.py.
```
Verifier correction: One evidence correction: model_stats.json has no top-level "excluded" set; the "excluded" render path in technical/index.html L1046-1059 iterates Object.keys(PROV) from model_provenance.json itself and renders a greyed "not measured" row only for entries carrying an .excluded field (currently only biomistral-7b). The conclusion (claude-* entries render nowhere) is unchanged, but the CLAUDE.md addition should also state this mechanic explicitly: adding an `excluded` field to any provenance entry makes it appear as a not-measured row in technical/ Part 4, so the claude-* generator-credit entries must stay excluded-field-free unless a rendered row is intended. Otherwise the finding and proposed_fix stand as written (severity low, doc-drift, file patientwords/data/model_provenance.json line 2).
Found by: technical-bundle. Verified: CONFIRMED.

#### F-L36 · `site:data/provenance.json:23` · doc-drift

provenance.json batches[] entries disagree on schema: the first two use generated_by + run_timestamp, the third (dialects_20260708T120729Z) uses model and omits run_timestamp; harmless to today's consumers (claim_check reads only batch/accepted/rejected; the dialect page cites the model name in static prose) but any future renderer of the batches strip keyed on generated_by/run_timestamp will silently blank the newest entry.

Evidence:
```
data/provenance.json:5-7 '"batch": "quadrants_20260706T191617Z", "generated_by": "claude-opus-4-8", "run_timestamp": "2026-07-06T19:16:32..."' vs :22-23 '"batch": "dialects_20260708T120729Z", "model": "claude-sonnet-5"' (no run_timestamp). Compare simulated-scenarios/index.html:623-632, which renders the analogous strip from simulated_scenarios.json expecting gen.model/gen.run_timestamp/gen.accepted — key-name drift across the two provenance-bearing files.
```
Proposed fix:
```diff
--- a/data/provenance.json
+++ b/data/provenance.json
@@
    "batch": "dialects_20260708T120729Z",
-   "model": "claude-sonnet-5",
+   "generated_by": "claude-sonnet-5",
+   "run_timestamp": "2026-07-08T12:07:29+00:00",
(timestamp from the batch stamp/report sidecar; claim_check exprs use only batch/accepted/rejected and are unaffected)
```
Verifier correction: Two corrections to the finding. (1) Direction: the engine sidecar (patientwords-engine/data/simulated/dialects_20260708T120729Z.report.json) uses "model" + "run_timestamp"; as do all sidecars; and the site's analogous rendered strip (simulated-scenarios/index.html:627) keys on gen.model. So the third provenance entry copied the sidecar verbatim; it is the FIRST TWO entries that renamed model → generated_by. A future renderer copied from the existing strip code would key on "model" and blank the OLDEST two entries, not the newest. Normalizing all three to "model" (and adding run_timestamp to the third) matches the sidecar and site convention better than the proposed rename to generated_by, though either direction is safe since no current consumer reads either key. (2) Timestamp value: the proposed fix inserts "2026-07-08T12:07:29+00:00" (batch-stamp-derived), but the other two entries use the sidecar's run_timestamp verbatim (verified byte-identical for both); the correct value from the sidecar is "2026-07-08T12:09:26.638462+00:00". Safe minimal fix: in the dialects_20260708T120729Z entry either add "run_timestamp": "2026-07-08T12:09:26.638462+00:00" (keeping "model", and optionally renaming the first two entries' "generated_by" to "model"), or apply the finder's rename but with the sidecar timestamp. claim_check exprs (batch/accepted/rejected only) are unaffected either way.
Found by: small-pages. Verified: CONFIRMED.

#### F-L37 · `site:data/stress_pairs.json:1` · silent-failure

stress_pairs.json has no writer or sync mechanism in either repo; it is a manual copy of engine data/measured/imported_pairs.json (currently identical), so the next engine-side dataset update (the page dateline promises 'will be updated with patient language') silently stales the site table; same manual-copy class as the accepted archive_export/simulated_archive rename gap.

Evidence:
```
grep 'stress_pairs' across patientwords-engine matches only docs and generate_stress_pairs (a different artifact: scenario_gen.py:218-221 emits top_prompt/bottom_prompt plus a 'generation' block into data/simulated/ batches, never provenance observations, never the site path). Normalized diff of patientwords/data/stress_pairs.json vs patientwords-engine/data/measured/imported_pairs.json: IDENTICAL (27 pairs each). phrase-dataset/index.html:120 hard-codes the promise '(will be updated with patient language)'.
```
Proposed fix:
```diff
Pin the copy so drift fails loudly — add to patientwords-engine/data/claims_manifest.json:
@@
+ {
+  "page": "phrase-dataset/index.html",
+  "source": "data/stress_pairs.json",
+  "expr": "[len(d), sum(1 for p in d if p['provenance']['source_row'])]",
+  "expected": [27, 27],
+  "_": "site file is a manual copy of engine data/measured/imported_pairs.json; bump when the dataset lands new rows"
+ }
(or better: a 3-line sync step in the export path that copies data/measured/imported_pairs.json to ../patientwords/data/stress_pairs.json)
```
Verifier correction: Finding stands verbatim except the proposed_fix. The claims_manifest entry as drafted would break the nightly claim check and would not catch the stated failure mode: (a) scripts/claim_check.py dereferences claim["snippet"] outside any try block, so an entry without a snippet key raises KeyError and crashes the whole check for every claim; (b) claim_check evaluates sources as (site / claim["source"]); the SITE copy only; so pinning expected [27,27] on data/stress_pairs.json passes even after the engine's imported_pairs.json grows and the site copy stales (the exact drift the finding warns about); it only fires in the inverse direction (site copy updated without a manifest bump). Correct fix is the finder's own alternative: add a copy step in the engine export path (mirroring scripts/export_dialect_matrix.py, which already writes ../patientwords/data/dialects.json) that writes data/measured/imported_pairs.json to ../patientwords/data/stress_pairs.json. Safe for all consumers; the files are already content-identical and both site pages (index.html:593, phrase-dataset/index.html:201) read the same shape. Minor note: the future 'patient language' update may land via the patient-sourced arm (LLM-authored batches into data/simulated/, per docs/patient_sourced_arm.md) rather than imported_pairs.json, but any hand-measured additions to imported_pairs.json would still stale the site table without the sync, so the finding holds.
Found by: small-pages. Verified: CONFIRMED.

#### F-L38 · `site:index.html:658` · fragile-parsing

The safety-view section gates its existence on Object.keys(summary.per_model) while everything it actually renders comes from summary.per_model_deduped; if a future export drops the pseudoreplicating per_model block (whose value fields no consumer reads), the whole safety view silently disappears despite complete deduped data being present.

Evidence:
```
Lines 653-659: `var s=u.summary||{}, pm=s.per_model||{}; ... var pmd=(s.per_model_deduped&&Object.keys(s.per_model_deduped).length)?s.per_model_deduped:null; var models=Object.keys(pm); if(!models.length)return;` — the early return fires on missing per_model even when pmd is fully populated; all rendered numbers (asym figure at 669-694, dedupFlips at 703) come from pmd, and per_model contributes only its key list.
```
Proposed fix:
```diff
--- a/index.html
+++ b/index.html
@@ -658 +658
-      var models=Object.keys(pm);
+      var models=Object.keys(pmd||pm);
```
Verifier correction: Defect as stated is real (index.html:658). Safer fix than `Object.keys(pmd||pm)`; rescue only when per_model is empty, so behavior is byte-identical whenever per_model is present: `var models=Object.keys(pm); if(!models.length)models=Object.keys(pmd||{}); if(!models.length)return;` This avoids silently shrinking the displayed model count (line 699) and the dedupComplete/dedupFlips computation (700-704) in a hypothetical future payload where per_model_deduped covers fewer models than per_model.
Found by: urgency-shift. Verified: CONFIRMED.

#### F-L39 · `site:simulated-scenarios/index.html:773` · unused-bloat

activeHasFeatures() is defined but never called, leaving the 'features:false → grey the clinical-circuit meter' contract enforced solely by the exporter nulling clinical_mass in build_model_obj; a payload that ever ships numeric clinical_mass for a features:false model (e.g. the exporter FEATURED set lagging a config change) would render NullFetcher's ~0.0 artifact bars with no page-side guard, the exact artifact-as-finding the engine CLAUDE.md warns against.

Evidence:
```
Line 773: `function activeHasFeatures(){return metaFor(currentModel).features!==false;}` — grep over the file finds no call site. The meter renders whenever numbers exist (massCell, lines 514-531: `if(typeof m.clinical!=='number'&&typeof m.patient!=='number'){td.appendChild(el('span','stat neutral','—'));...}`). Exporter-side sole guard: export_frontend_simulated.py:170 `"clinical_mass": r.get("clinical_mass") if featured else None`; engine CLAUDE.md: NullFetcher clinical_mass "comes out ~0.0 — an artifact, not a finding".
```
Proposed fix:
```diff
--- a/simulated-scenarios/index.html
+++ b/simulated-scenarios/index.html
@@ -843 +843
-        tr.appendChild(massCell(m));
+        tr.appendChild(massCell(activeHasFeatures()?m:{}));
(uses the existing guard as belt-and-braces; alternatively delete the unused function if data-side nulling is deemed sufficient)
```
Verifier correction: Finding stands as written; the proposed_fix is safe (massCell's em-dash path is a supported pending state and line 843 is its only call site) but incomplete: (1) sortVal case 'mass' (index.html:875) and the CSV export builder (~lines 1114-1132) also read clinical_mass unguarded, so artifact values would still leak into sorting and the collaborator download; (2) scenario.html has the identical unguarded meter (massLine at lines 460/466) and no guard function at all; per the repo's deliberate cross-page duplication, a complete fix must add the guard there too; (3) the CLAUDE.md contract says "grey the clinical-circuit meter"; the fix renders the em-dash pending state rather than a greyed meter, acceptable but not literally the documented behavior.
Found by: sim-scenarios-index. Verified: CONFIRMED.

#### F-L40 · `site:simulated-scenarios/index.html:903` · other

The text-search filter uses cur(s) instead of the page's own view(s) guard, so rows untraced on the selected model are matched against the base model's hidden values (target_token, top_clinical/top_patient of gemma) even though every visible cell in those rows renders 'not traced' / '-'; search results (and the 'download current view' CSV built from them) look arbitrary under a non-base model.

Evidence:
```
Line 903 inside the visibleScenarios() filterText branch: `var m=cur(s);` then lines 904-907 match on `m.target_token, ..., m.top_clinical&&m.top_clinical[0], m.top_patient&&m.top_patient[0]`. cur() (line 767) falls back to the top-level gemma mirror; view() (line 772) exists precisely to return {} for untraced rows and is used everywhere else (rowFor:789, sortVal:864, filterStatus:889-895, CSV:1124). Live payload: 89 scenarios untraced on qwen3-4b are affected.
```
Proposed fix:
```diff
--- a/simulated-scenarios/index.html
+++ b/simulated-scenarios/index.html
@@ -903 +903
-            var m=cur(s);
+            var m=view(s);
```
Verifier correction: Defect and fix stand as filed, with two evidence corrections: (1) view() is not "used everywhere else"; it is defined at line 772 but currently has zero call sites; rowFor (789), sortVal (864), the status filter (889) and the CSV export (1124) all inline the equivalent hasModel(s)?cur(s):{} pattern. The fix would make line 903 view()'s first caller (equally valid: inline the guard for consistency). (2) The CSV's measurement fields are already guarded at line 1124 and export blank where untraced; the CSV corruption is limited to row membership; untraced rows matched only via hidden base-model values are exported as all-blank measurement rows because the export iterates visibleScenarios().
Found by: sim-scenarios-index. Verified: CONFIRMED.

#### F-L41 · `site:simulated-scenarios/index.html:1172` · mismatched-keys

The repeatability line claims N pairs 'reproduce identical probabilities and top-five lists' but counts d.top_word_stable_pairs, not d.spread_lists_identical_pairs; the two keys coincide today (68/68) but measure different things and can diverge, at which point the sentence overstates.

Evidence:
```
`el.textContent='repeatability: '+d.top_word_stable_pairs+' of '+d.pairs_retraced+' phrases traced more than once reproduce identical probabilities and top-five lists '+...` — the writer emits both `top_word_stable_pairs` (top word unchanged) and `spread_lists_identical_pairs` (full top-k lists identical) as distinct counters (retrace_consistency.py lines 119-120, 131-132); methods.html correctly reports them separately (lines 642-644).
```
Proposed fix:
```diff
-      el.textContent='repeatability: '+d.top_word_stable_pairs+' of '+d.pairs_retraced+
+      var nRep=(d.spread_lists_identical_pairs!=null)?Math.min(d.top_word_stable_pairs,d.spread_lists_identical_pairs):d.top_word_stable_pairs;
+      el.textContent='repeatability: '+nRep+' of '+d.pairs_retraced+
```
Verifier correction: Defect as stated is real; the proposed_fix is safe (page-JS only, no other consumer) but imprecise: min(top_word_stable_pairs, spread_lists_identical_pairs) is an upper bound on the pairs satisfying both properties, not the conjunction, and the sentence's "identical probabilities" clause is anchored by neither counter. Better fix: since the payload includes d.rows with per-pair booleans, compute the conjunction client-side; e.g. var nRep = Array.isArray(d.rows) ? d.rows.filter(function(r){return r.top_clinical_stable && r.top_patient_stable && r.spread_lists_identical;}).length : d.top_word_stable_pairs;; or reword the sentence to match top_word_stable_pairs ("reproduce the same top word at recorded precision"), keeping the prob_spread_max parenthetical for the probability claim.
Found by: methods-sentinel-bundle. Verified: CONFIRMED.

#### F-L42 · `site:simulated-scenarios/scenario.html:399` · mismatched-keys

archiveUrlFor() prefers archive.models[<id>].release_url, a per-model shape no writer emits; the exporter only ever writes archive = {"release_url": args.archive_url}; so the preferred branch is unreachable contract fiction. Fully guarded (no crash; falls through to the shared URL), but the next person wiring per-model archives must reverse-engineer the expected shape from consumer code.

Evidence:
```
scenario.html:398-401: `var a=data.archive; if(!a)return null; if(a.models&&a.models[currentModel]&&a.models[currentModel].release_url) return a.models[currentModel].release_url; return a.release_url||null;` vs export_frontend_simulated.py:357-358: `if args.archive_url:\n    payload["archive"] = {"release_url": args.archive_url}`. Live payload has no archive key at all; grep of the engine finds no other writer of an archive.models shape.
```
Proposed fix:
```diff
Document the intended shape at the emitter so the branches stay in sync:
--- a/scripts/export_frontend_simulated.py
+++ b/scripts/export_frontend_simulated.py
@@ -357,2 +357,3
 if args.archive_url:
+    # scenario.html also honors per-model URLs: archive.models[<id>].release_url
     payload["archive"] = {"release_url": args.archive_url}
(or delete the dead per-model branch, scenario.html lines 399-400)
```
Verifier correction: Finding accurate as filed. Minor precision: the function spans scenario.html:397-402 with the dead branch at 399-400, and its single call site (line 542) is also gated by (!noGraphs&&traced). Prefer the comment-at-emitter fix over deleting the branch; the exporter already merges per-model trace dirs into scenario.models[<id>], so the per-model archive branch reads as deliberate forward-compat scaffolding; documenting the shape at export_frontend_simulated.py:357-358 keeps emitter and consumer in sync without discarding it.
Found by: sim-scenarios-index,sim-scenarios-detail. Verified: CONFIRMED.

#### F-L43 · `site:simulated-scenarios/scenario.html:499` · mismatched-keys

scenario.html gates its entire 'Circuit diff' panel on m.diff_html, a key the exporter never emits; so the branch is dead code and circuit_diff (emitted for 520 scenarios x 2 copies, 218,326 bytes on disk) is never rendered anywhere on the site.

Evidence:
```
scenario.html:499-507: 'if(m.diff_html){ ... +(m.circuit_diff?(\' · \'+m.circuit_diff.shared_features+\' shared · \' ...) ... embedBlock(card,m.diff_html,...)}'. Writer check: build_model_obj (export_frontend_simulated.py:152-171) emits circuit_diff but no diff_html key, and the render loop (lines 285-312) sets only 'html' and 'png'. Instance check: 0 occurrences of diff_html anywhere in the 7.1 MB payload; 520 scenarios carry non-null circuit_diff in both copies. The only other circuit_diff mention is start-here/index.html:394 static provenance text pointing readers at the field.
```
Proposed fix:
```diff
--- a/simulated-scenarios/scenario.html (frontend; pages are editable, modes/ is not)
+++ b/simulated-scenarios/scenario.html
@@ lines 499-507
-        if(m.diff_html){
-          var vh=el('p','view-head','Circuit diff: what the swap changed');
-          card.appendChild(vh);
-          var vs=el('p','view-sub','features present under BOTH phrasings are dimmed to context'
-            +(m.circuit_diff?(' · '+m.circuit_diff.shared_features+' shared · '
-            +m.circuit_diff.unique_to_a+' only clinical · '+m.circuit_diff.unique_to_b+' only patient'):''));
-          card.appendChild(vs);
-          embedBlock(card,m.diff_html,'Circuit diff: shared features dimmed; full-ink nodes are what the term swap added or removed.');
-        }
+        if(m.circuit_diff){
+          card.appendChild(el('p','view-sub','Circuit diff: '+m.circuit_diff.shared_features+' shared · '
+            +m.circuit_diff.unique_to_a+' only clinical · '+m.circuit_diff.unique_to_b+' only patient'));
+        }
+        if(m.diff_html){
+          embedBlock(card,m.diff_html,'Circuit diff: shared features dimmed; full-ink nodes are what the term swap added or removed.');
+        }
(Alternatively, teach the exporter's render loop to publish a diff render and set models[<id>].diff_html — but no such artifact exists in its copy list today.)
```
Verifier correction: Two minor corrections to the finding, defect otherwise accurate: (1) The alternative exporter-side fix is more viable than stated; the diff render artifact DOES exist in engine trace_out (index_NN_diff.html/.png, written at batch_eval.py:596-599 and recorded as local paths under result['outputs']['diff_html']); the exporter simply never copies it because its copy pattern f"index_{index:02d}.{key}" (export_frontend_simulated.py:288) misses the _diff suffix. Publishing it would mean adding the _diff files to the render-copy loop and setting models[<id>].diff_html (mind the max-renders cap and site weight). (2) The '218,326 bytes' figure only holds for the pretty-printed (indent=2) span; compact serialization of the 520x2 duplicated circuit_diff objects is ~83 KB. The substance; 520 scenarios x 2 copies of never-rendered data and a dead panel branch; is verified.
Found by: global-sweep. Verified: CONFIRMED.

#### F-L44 · `site:simulated-scenarios/scenario.html:520` · unused-bloat

data/simulated_archive.json (3,869,136 bytes) is committed to the site but linked by no page; only the CSV twin is offered ('data/simulated_archive.csv', scenario.html lines 520-537); deepening the accepted archive_export.*-rename-gap prior with the fact that the JSON half of the documented collaborator download is unreachable.

Evidence:
```
Repo-wide grep: the only data/simulated_archive.* references in any page are scenario.html:520-521 and 536-537, both '../data/simulated_archive.csv'; simulated-scenarios/index.html:359's 'full JSON' link points at data/simulated_scenarios.json, not the archive. Frontend CLAUDE.md 'Data contracts' nevertheless documents 'data/simulated_archive.{csv,json} (collaborator download)'. File sizes: simulated_archive.json 3,869,136 B vs simulated_archive.csv 1,912,960 B.
```
Proposed fix:
```diff
--- a/simulated-scenarios/scenario.html
+++ b/simulated-scenarios/scenario.html
@@ line 521 (and the parallel block at 536-537)
             mx.href='../data/simulated_archive.csv';
             pn.appendChild(mx);
+            pn.appendChild(document.createTextNode(' (or '));
+            var mj=el('a',null,'JSON');mj.href='../data/simulated_archive.json';
+            pn.appendChild(mj);pn.appendChild(document.createTextNode(')'));
(or, if the owner prefers, stop exporting the .json and amend the CLAUDE.md contract line — either resolves the drift)
```
Verifier correction: Minor precision only: 'unreachable' should read 'not linked or discoverable from any page'; the file is still directly downloadable at its URL (GitHub Pages serves data/simulated_archive.json, and CLAUDE.md documents the path for collaborators). Location, sizes, severity (low), and both fix options are otherwise correct as stated.
Found by: global-sweep. Verified: CONFIRMED.

#### F-L45 · `site:simulated-scenarios/scenario.html:556` · silent-failure

The single promise .catch shows the 'scenario not found · back to the series' miss note for ANY failure; network error, non-OK status, JSON parse error, or an exception thrown inside buildModelRow/renderCard; mislabeling load failures as a missing scenario, and a mid-renderCard throw leaves a half-rendered card above the wrong message.

Evidence:
```
L556: `.catch(function(){document.getElementById('sim-missing').hidden=false;});` catches everything from the fetch at L368 through renderCard() at L554; the not-found path proper already returns early at L373 with the same element. #sim-missing's static text (L197) is 'scenario not found', which is false for a fetch/parse failure; renderCard clears and rebuilds #sim-card incrementally (L436 onward), so an exception partway through leaves partial measurement blocks on screen plus 'scenario not found' below them.
```
Proposed fix:
```diff
--- a/simulated-scenarios/scenario.html
+++ b/simulated-scenarios/scenario.html
@@ -553,7 +553,12 @@
       renderCard();
     })
-    .catch(function(){document.getElementById('sim-missing').hidden=false;});
+    .catch(function(){
+      var n=document.getElementById('sim-missing');
+      n.textContent='scenario data failed to load · ';
+      var a=document.createElement('a');a.href='./';a.textContent='back to the series';
+      n.appendChild(a);
+      n.hidden=false;
+    });
(the true not-found path at L373 keeps the original 'scenario not found' text since it sets hidden=false without entering the catch)
```
Verifier correction: Finding stands as written. Two scope notes for the fixer: (1) renderCard() is also invoked from model-selector chip click handlers at L428 outside the promise chain; a throw there is entirely uncaught (blank card, no message), which neither the finding nor the proposed fix addresses; a try/catch inside renderCard would cover both. (2) An exception thrown after L375 leaves #sim-title already populated with the scenario name above the failure note. Neither changes the verdict or the proposed fix's safety.
Found by: sim-scenarios-detail. Verified: CONFIRMED.

#### F-L46 · `site:technical/index.html:480` · doc-drift

sp-caption hardcodes 'cells under 10 phrases suppressed' while the payload carries the actual threshold as min_n (emitted by the writer, read by no consumer); a regen with a different --min-n makes the caption wrong.

Evidence:
```
HTML L479-482: 'gemma-2-2b · exploratory: phrase-deduped, no correction for testing many specialties at once, cells under 10 phrases suppressed'; writer specialty_breakdown.py L92 emits "min_n": args.min_n (default 10, CLI-overridable L73-74); the page JS (L1066-1093) never reads d.min_n.
```
Proposed fix:
```diff
@@ script 4, inside .then(function(d){ ... after sp-sum is set (L1090)
+      if(typeof d.min_n==='number'){var spc=document.getElementById('sp-caption');
+        spc.textContent=spc.textContent.replace('under 10 phrases','under '+d.min_n+' phrases');}
```
Verifier correction: Finding is accurate as filed; no correction needed. Minor precision only: the literal hardcoded substring "under 10 phrases" sits on line 480 within the #sp-caption element spanning L479-482, and the payload consumer is the third inline script (fetch of ../data/specialty_breakdown.json, ~L1067-1093), whose .then never dereferences d.min_n. The proposed fix is safe: single consumer, typeof-guarded, no-op at the current min_n=10.
Found by: technical-bundle. Verified: CONFIRMED.

#### F-L47 · `site:technical/index.html:695` · fragile-parsing

Guard-then-unguarded exemplar chain: (d.exemplars||[]).filter(...)[0]||d.exemplars[0] re-dereferences the unguarded key, so a payload lacking 'exemplars' entirely (older/partial shape) throws and trips the misleading catch-all pending message.

Evidence:
```
L695: var ex=(d.exemplars||[]).filter(function(e){return e['class']==='hijack';})[0]||d.exemplars[0]; — the first operand is null-safe, the fallback is not. Current writer always emits the key (jlens_insights.py L227: out["exemplars"] = exemplars), so impact is limited to older payload shapes, but the site's own contract requires graceful fallback for those.
```
Proposed fix:
```diff
-      var ex=(d.exemplars||[]).filter(function(e){return e['class']==='hijack';})[0]||d.exemplars[0];
+      var ex=(d.exemplars||[]).filter(function(e){return e['class']==='hijack';})[0]||(d.exemplars||[])[0];
```
Verifier correction: Impact is slightly broader than stated: besides tripping the misleading pending message, the throw at L695 aborts the rest of the .then body, so Figs 2 (formation strip), 3 (taxonomy), 5 (instruction tuning) and the Fig 4 router-table fetch; none of which depend on 'exemplars'; are silently dropped even when their data is present, and the correct dd-head header set at L690-691 is overwritten. Severity remains low (current writer always emits the key). Proposed fix is correct as written.
Found by: technical-bundle. Verified: CONFIRMED.

#### F-L48 · `site:technical/index.html:1122` · fragile-parsing

Census renderer dereferences b.pairs unguarded after clearing the pending span, while its catch comment claims 'pending states stay'; a block without pairs (malformed regen or shape drift) leaves #ad-blocks permanently empty; the sibling consumer guards the same read.

Evidence:
```
L1116: mount.textContent=''; then L1122: return b.pairs.filter(function(u){return u['class']===c[0];}).length;})); and L1127 aria-label uses b.pairs.length — any throw lands in L1259 .catch(function(){/* pending states stay */}) after the pending span was already destroyed. simulated-scenarios/index.html:589 reads the identical structure defensively: (b.pairs||[]).forEach(...).
```
Proposed fix:
```diff
@@ L1117 (top of blocks.forEach)
-      blocks.forEach(function(b){
+      blocks.forEach(function(b){
+        var bp=b.pairs||[];
 then use bp in place of b.pairs at L1122 (filter), L1127 (length), L1131 (filter), and L1165 (b.pairs.forEach in the per-pair table).
```
Verifier correction: Finding is accurate at the cited lines; only the proposed_fix needs a correction. The diff adds `var bp=b.pairs||[];` at the top of the blocks.forEach starting at L1117 and says to use bp at L1122, L1127, L1131, and L1165; but L1165 is inside a second, separate blocks.forEach callback (starting at L1163), so the bp from L1117 is out of scope there. Corrected fix: (1) add `var bp=b.pairs||[];` at the top of the first blocks.forEach (after L1117) and use it at L1122, L1127, L1131; (2) add a second `var bp=b.pairs||[];` at the top of the second blocks.forEach callback (after L1163) and change L1165 to `bp.forEach(...)`. This is safe for rendering: with empty bp, maxRow=0 but W already floors it via Math.max(maxRow,1), the aria-label reports 0 pairs, and the per-pair table simply gets no rows for that block; the change is page-local JS with no other consumers.
Found by: technical-bundle. Verified: CONFIRMED.

#### F-L49 · `site:translation/index.html:453` · fragile-parsing

retrace17 is assigned without declaration inside the provenance .then and only works because 'var ...,retrace17=null' 163 lines later (line 616) hoists within the same IIFE; splitting these scripts or reordering during an edit would silently make phrase 17's caption show the July-7 numbers under a 're-traced July 9, 2026' label (mislabeled provenance).

Evidence:
```
translation/index.html:453 'retrace17=(tc.grandma_laxative&&tc.grandma_laxative.retrace_20260709)||null;' (no var/let) vs :616 'var curPanel=0,pendingScroll=false,retrace17=null;' and :645 'if(c.index===17&&retrace17){ pt=retrace17.patient_top;tt=retrace17.translated;ct=retrace17.clinical; when=\'re-traced July 9, 2026\';'. Correctness currently depends on var hoisting plus fetch resolving after the synchronous re-initialization at :616.
```
Proposed fix:
```diff
--- a/translation/index.html
+++ b/translation/index.html
@@
   function pct(p){return Math.round(p*100)+'%';}
+  var retrace17=null; // set from provenance; read by showTrace()
   fetch('../data/provenance.json',{cache:'no-cache'}).then(function(r){return r.json();}).then(function(p){
@@
-  var curPanel=0,pendingScroll=false,retrace17=null;
+  var curPanel=0,pendingScroll=false;
```
Verifier correction: Failure scenario correction: if the declaration/scripts were split or reordered, line 453 would write an implicit global while showTrace at :645 reads the IIFE-local retrace17 (still null), so the index===17 branch is SKIPPED; the caption would show the July-7 numbers under the fallback label "traced July 7, 2026" (lines 643-644), not under a "re-traced July 9, 2026" label as the finder stated. The mislabeling is real but inverted: the embedded render index_17.html is the July-9 re-trace (per comments at :451-453 and :642), so the caption would silently misdescribe the figure it captions; numbers and date both wrong relative to the displayed trace, violating the frontend's "provenance labels must stay accurate" hard rule. The proposed fix is correct as written.
Found by: small-pages. Verified: CONFIRMED.

#### F-L50 · `site:translation/index.html:471` · fragile-parsing

The tx-flow block dereferences ic.translated[0]/[1] and ic.patient[0]/[1] guarded only by ic&&ic.prompts; a provenance edit that keeps prompts but drops either array throws inside the single provenance .then, and the trailing empty .catch (line 611) swallows it; gallery, titration, and flow all silently stay hidden (half-rendered page).

Evidence:
```
translation/index.html:456 'if(ic&&ic.prompts){' then :471-472 'out.appendChild(el(\'span\',\'tgt\',ic.translated[0]+\' (\'+Math.round(ic.translated[1]*100)+\'%)\')); out.appendChild(document.createTextNode(\' \\u2014 was \'+ic.patient[0]+...'. The whole provenance chain (flow :454-474, gallery :476-538, titration :539-610) lives in one .then closed by :611 '}).catch(function(){});' — any TypeError mid-flow aborts all three sections with no console-visible page state.
```
Proposed fix:
```diff
--- a/translation/index.html
+++ b/translation/index.html
@@
-    var ic=tc.icecream_antacid;
-    if(ic&&ic.prompts){
+    var ic=tc.icecream_antacid;
+    if(ic&&ic.prompts&&Array.isArray(ic.translated)&&Array.isArray(ic.patient)){
```
Verifier correction: Finding stands as filed (file, line, severity, mechanism all correct). Two sharpenings: (1) the proposed fix is safe but incomplete; the gallery loop in the same .then has the identical unguarded-dereference class (translation/index.html:487-488 and :511-512 read c.patient_top[0]/[1] and c.translated_top[0]/[1] per case), so one malformed entry in translation_cases.all.cases still silently kills gallery + titration through the same empty catch; a complete fix either guards those (`Array.isArray(c.patient_top)&&Array.isArray(c.translated_top)` with a per-card skip) or splits the three sections into independent try/catch blocks. (2) Supporting evidence the finder missed: the engine's claims manifest checks grandma_laxative's arrays but not icecream_antacid's, so no CI check catches this specific edit; and the titration block's own `v&&typeof v.recovered==='number' → "pending"` pattern is the established in-page convention the flow block fails to follow.
Found by: small-pages. Verified: CONFIRMED.

## Refuted candidates (for the record)

Three candidates failed adversarial verification and are excluded above: one duplicated an
established prior, two claimed missing guards that exist on adjacent lines. Full verdicts sit
in the workflow journal if the main session wants them.

## Coverage

Artifacts audited writer-to-reader: simulated_scenarios, urgency_shift, model_stats,
convergence, timeline, jlens_depth, jlens_insights, retrace_consistency, specialties,
specialty_breakdown, model_provenance, translation_scale, dialects, stress_pairs,
model_evaluations, provenance, patch_profile, drift_series (via claim_check), plus the
simulated_archive downloads. Workflows audited: all seven, plus fire_trigger, ledger_update,
daily_brief, archive_run, claim_check. Pages audited: all eleven HTML pages plus share/404.

# Audit 2: Claim-Level Correctness and Pre-Registration Compliance

Date: 2026-07-17. Auditor: read-only audit session, branch `claude/patient-words-audit-hd792y`.
Audited refs (current HEADs): `patientwords` @ `bbf5874`, `patientwords-engine` @ `9696df4`,
both on `claude/gemma-clinical-colloquial-interp-mavx04`, mounted as detached worktrees.
Nothing in either audited tree was modified. Nothing under `.github/trigger/` was touched.
All recomputation ran in an isolated scratch sandbox; both worktrees were confirmed
`git status`-clean after every script invocation.

## Holdout handling in this report

The confirmatory Tier B holdout stayed sealed throughout. No statistic was computed over
holdout rows; no holdout phrase text is reproduced anywhere below (verified by scan: the only
quoted strings are code, registered-document text, published site prose, batch stems, and
integer counts/indices). Split membership was counted, never analyzed. One commissioned check
could not be completed without unsealing and is filed as `requires-unseal` (F2-M17), not run.

## Headline: the holdout seal is currently breached in published files

The single most consequential result. Amendment 3 (in force since 2026-07-14) registers that a
holdout phrase flagged anywhere is excluded everywhere and withheld from every public data
file. Multiple published artifacts on the current site HEAD violate this. The leaks divide into
two kinds:

- **Sealed phrase text published verbatim** (confidentiality-grade, public repo):
  `data/simulated_archive.{json,csv}` carries 12 rows / 6 distinct holdout phrases with full
  clinical and patient prompt text (F2-H01); `data/retrace_consistency.json` carries 5 holdout
  phrases (2 whole, 3 truncated to 70 chars) with per-run stability data (F2-H07).
- **Holdout rows folded into published aggregates and per-pair census** (analysis-independence
  grade): `data/jlens_insights.json` (38 of 476 census rows, plus every formation/taxonomy
  aggregate over them, F2-H05/H06); `data/jlens_depth.json` (21 per-pair depth rows + the
  translation-by-class and steering-by-class aggregates, F2-H02/H03/H04); the published steering
  headline shifts from 8/9 to the shown 11/12 once 3 holdout hijack pairs are included (F2-H04);
  `data/urgency_shift.json` summary aggregates via a keying mismatch (F2-H09).

Root causes are three independent gaps, each with a proposed diff below: (1) several exporters
(`jlens_insights.py`, `export_jlens_depth.py`, `retrace_consistency.py`) apply no holdout filter
at all; (2) the batch-name gate in `tierb_split._BATCH_RE.fullmatch` rejects alias/re-run stems
(`pairs_..._txopus`, `repeatability_r*`), so `export_archive.py` and `urgency_shift.py` leak
suffixed-batch holdout rows; (3) `urgency_shift.py`/`convergence_tracker.py` key exclusion on
the row flag, not the registered clinical phrase. Because both repos are public, the phrase-text
items (F2-H03, F2-H09) are the time-sensitive ones. Fixes are proposed only; the main session
verifies and lands them.

## Method

Eight finder lanes (five independent recomputations from raw committed inputs; two
pre-registration compliance passes over the base registration and amendments 1-4; one site-wide
unguarded-claim sweep), each finding then put to an adversarial verifier that re-ran the
reproduction command in its own sandbox, plus a completeness critic. 77 agent runs. Result: 68
candidate findings, 61 confirmed, 7 refuted (two were barred Audit-1 re-files; one was a
would-be holdout-translation leak that failed on recompute; one claimed a manifest guard absent
that exists), 0 undecidable. 57 unique after merging four cross-lane duplicates, plus four more
from the completeness-critic pass filed in the Addendum. Severity after verifier corrections:
10 high, 31 medium, 20 low (61 unique). The four Addendum items (F2-M30, F2-M31, F2-L19, F2-L20)
carry continuing IDs so every ID above stays stable.

Commission constraints honored: current-HEAD file:line; the two new logits models
(meditron3-8b, apertus-8b-meditronfo) were accounted for in every model-set comparison; no
Audit-1 finding (11 fixed highs, F-M27, the 36 queued mediums) was re-derived or re-filed.

## Findings

Stable IDs F2-H/M/L. Each: location on current HEAD, category, evidence (published vs recomputed
values and the reproduction command), proposed fix as a diff, verifier correction where the
verifier sharpened or rescoped the finding.

### High: wrong or seal-breaching published numbers, registered-rule violations

#### F2-H01 · `engine:scripts/export_archive.py:99` · recompute-divergence

The collaborator archive's holdout gate only fires for batch stems fullmatching pairs_<STAMP>, so the mitigation alias batches pairs_20260711T051145Z_txopus/_txplacebo escape it: 12 public rows (6 per arm, full phrase text + probabilities + penalties) of 4 row-flagged holdout phrases are published in patientwords/data/simulated_archive.{json,csv}, violating Amendment 3's in-force rule that holdout phrases are 'withheld from every public export'.

Evidence:
```
Code: `if is_tierb_batch(stem, _TIERB_START) and is_holdout(pair.get("top_prompt")):` (line 99); tierb_split.is_tierb_batch requires `_BATCH_RE.fullmatch(batch_name)` so stems 'pairs_20260711T051145Z_txopus'/'_txplacebo' return False and their pairs are exported unchecked. Registered (prereg_amendment3_holdout.md, Endpoint 5): "Until the endpoint run, holdout phrases stay excluded from every published aggregate and withheld from public data files." Recount on frontend HEAD bbf5874: 12 of 3084 rows in data/simulated_archive.json (and the same 12 in the CSV) carry a clinical_prompt in the sealed holdout phrase set — 6 from pairs_20260711T051145Z_txopus, 6 from pairs_20260711T051145Z_txplacebo, all gemma-2-2b; each row publishes clinical_prompt and patient_prompt text. Repro: python3 -c "import json; us=json.load(open('/home/user/audit-wb/patientwords-engine/urgency_shift.json')); h={r['clinical_prompt'] for r in us['rows'] if r.get('tierb_split')=='holdout'}; a=json.load(open('/home/user/audit-wb/patientwords/data/simulated_archive.json')); print(sum(1 for r in a if r.get('clinical_prompt') in h))" -> 12.
```
Proposed fix:
```diff
--- a/scripts/export_archive.py
+++ b/scripts/export_archive.py
@@ -84,6 +84,15 @@
 _TIERB_START = tierb_start_stamp(str(ENGINE / "ops/dashboard.json"))
 withheld_holdout = 0
+# Phrase-keyed seal (Amendment 3, 2026-07-14): a Tier B holdout phrase is
+# withheld wherever it re-appears, including alias/mitigation stems such as
+# pairs_<STAMP>_txopus that do not fullmatch the Tier B batch pattern.
+holdout_phrases = set()
+for bp in sorted(ENGINE.glob("data/simulated/pairs_*.json")):
+    if bp.name.endswith(".report.json") or not is_tierb_batch(bp.stem, _TIERB_START):
+        continue
+    for p in json.loads(bp.read_text(encoding="utf-8")):
+        if is_holdout(p.get("top_prompt")):
+            holdout_phrases.add(p["top_prompt"])
 for batch_path in sorted(ENGINE.glob("data/simulated/pairs_*.json")):
@@ -96,9 +105,10 @@
     for i, pair in enumerate(batch, start=1):
         # confirmatory holdout stays sealed: withheld from every public export
         # until the pre-registered endpoint (amendment 1; 2026-07-14 decision)
-        if is_tierb_batch(stem, _TIERB_START) and is_holdout(pair.get("top_prompt")):
+        if ((is_tierb_batch(stem, _TIERB_START) and is_holdout(pair.get("top_prompt")))
+                or pair.get("top_prompt") in holdout_phrases):
             withheld_holdout += 1
             continue
Then regenerate the site copies of simulated_archive.{json,csv} so the 12 rows are removed.
```
Verifier correction: The finding is correct except for one count: the leak involves 6 distinct holdout phrases, not 4. Corrected summary: The collaborator archive's holdout gate (export_archive.py:99) only fires for batch stems fullmatching pairs_<STAMP> (tierb_split.py:25,51-52), so the mitigation alias batches pairs_20260711T051145Z_txopus/_txplacebo escape it: 12 public rows (6 per arm, gemma-2-2b, with full phrase text; 8 with probabilities, 6 with language penalties) covering 6 distinct row-flagged Tier B holdout phrases are published in patientwords/data/simulated_archive.{json,csv}, violating Amendment 3's in-force phrase-keyed rule (docs/prereg_amendment3_holdout.md:25-26, 97-99) that holdout phrases are withheld from every public data file. The site copy demonstrably postdates the 2026-07-14 gate (0 assigned-holdout rows from fullmatch Tier B batches remain), so this is a live gate gap, not staleness. Severity: high. Proposed fix as filed (phrase-keyed pre-pass building the holdout phrase set from Tier B batches and withholding any pair whose top_prompt is in it, then regenerating the site archive copies) is verified to remove exactly the 12 rows.

Found by: p-holdout,p-amendments. Verified: CONFIRMED.

#### F2-H02 · `engine:scripts/export_jlens_depth.py:113` · prereg-mismatch

data/jlens_depth.json (regenerated 2026-07-16, after the amendment-3 withholding rule) publishes per-pair depth classes and class-count aggregates for 21 sealed holdout pairs across five Tier B blocks, while its own scope string claims 'Amendment 1 exploration split only'.

Evidence:
```
Code: build_block line 113-115 `pairs = [{"index": r["index"], "class": r["patient_depth_class"], "target": ...} for r in summary["results"]]` — no holdout filter anywhere in the file; the published payload asserts at line 264-265: "Amendment 1 exploration split only". Registered: Amendment 1 — "Interim analyses during the collection week ... use ONLY the ~90% exploration split."; Amendment 3 Endpoint 5 — "holdout phrases stay excluded from every published aggregate and withheld from public data files." Recount (hash rule over the committed batch files, membership only): published blocks contain holdout indices pairs_20260711T051145Z:[1,4,33,38,47,49], pairs_20260711T131752Z:[18,19,24,35,38], pairs_20260712T051903Z:[3,6,7,36,42,45], pairs_20260712T163501Z:[16,17], pairs_20260713T050939Z:[10,11] = 21 pairs, each published with its per-pair class and target token, and included in each block's published `counts`. File generated_utc = 2026-07-16T14:14:12Z. Repro: python3 with hashlib sha1(top_prompt)%10==0 over /home/user/audit-wb/patientwords-engine/data/simulated/pairs_<stamp>.json intersected with blocks[].pairs[].index of /home/user/audit-wb/patientwords/data/jlens_depth.json.
```
Proposed fix:
```diff
--- a/scripts/export_jlens_depth.py
+++ b/scripts/export_jlens_depth.py
@@ -43,6 +43,13 @@
+import sys
+sys.path.insert(0, str(Path(__file__).resolve().parent))
+from tierb_split import is_holdout, is_tierb_batch, tierb_start_stamp
+_TIERB_START = tierb_start_stamp("ops/dashboard.json")
+
 def load_summary(stem, model="gemma-2-2b"):
     path = Path("trace_out") / f"{stem}__jlens_{model}" / "jlens_summary.part_01.json"
-    return json.loads(path.read_text(encoding="utf-8")), str(path)
+    summary = json.loads(path.read_text(encoding="utf-8"))
+    if is_tierb_batch(stem, _TIERB_START):
+        summary["results"] = [r for r in summary["results"]
+                              if not is_holdout((r.get("prompts") or {}).get("clinical"))]
+    return summary, str(path)

(one filter point covers blocks, counts, examples, translation classes, and the units annotation; regenerate the site file)
```
Verifier correction: As filed, with one addition that strengthens it: beyond the 21 per-pair block rows and their counts aggregates, three of those holdout pairs (pairs_20260711T051145Z indices 1, 38, 47) also appear in the published translation.pairs with per-pair recovery values and are folded into the published translation.by_class mean_recovery aggregates; i.e. the file publishes not only sealed per-pair holdout data but also aggregates computed over holdout rows, a direct Amendment 3 Endpoint 5 violation on both clauses. Also note the registered basis is even firmer than cited: Amendment 2 (prereg_amendment2_depth.md L20-21) explicitly binds the depth readout to "exploration split only until the sealed holdout analysis day", so the exploratory label in the scope string provides no cover. Mitigating scope note: the exemplar, all 6 worked examples, and the units annotation are non-holdout, so no holdout prompt text is currently exposed; the leak is index/class/target-token/recovery-level plus aggregates. The proposed load_summary filter fixes all leak surfaces including translation (holdout indices drop out of the classes join); regenerate the site file after applying.

Found by: p-amendments. Verified: CONFIRMED.

#### F2-H03 · `engine:scripts/export_jlens_depth.py:140` · prereg-mismatch

The published translation-by-depth-class aggregate in data/jlens_depth.json (by_class mean_recovery 0.163 / 0.13 / 0.157) is computed including 3 sealed holdout pairs; an interim aggregate over holdout rows, contrary to Amendment 1 and Amendment 2's sample rule.

Evidence:
```
Code: translation_split joins collector rows with only `if row.get("batch") != stem or row.get("model") != model: continue` (line 141) — never checks tierb_split — and publishes `by_class: {c: {"n": len(v), "mean_recovery": round(sum(v)/len(v), 3)}}` (line 160-161). Registered: Amendment 2 Sample — "Amendment 1 rules apply unchanged: exploration split only until the sealed holdout analysis day; the holdout is never touched by interim looks." Recount (membership only): of the 35 published translation.pairs, 3 are holdout pairs — (pairs_20260711T051145Z, 1), (pairs_20260711T051145Z, 38), (pairs_20260711T051145Z, 47) — so the published by_class n's and mean_recovery values (absent n=10 mean 0.163, retained n=21 mean 0.13, suppressed n=4 mean 0.157) aggregate over sealed rows. This is also the descriptive precursor of registered endpoint H-D1. Repro: intersect translation.pairs of /home/user/audit-wb/patientwords/data/jlens_depth.json with the sha1%10==0 indices of /home/user/audit-wb/patientwords-engine/data/simulated/pairs_20260711T051145Z.json.
```
Proposed fix:
```diff
--- a/scripts/export_jlens_depth.py
+++ b/scripts/export_jlens_depth.py
@@ -138,7 +138,8 @@
         classes = {r["index"]: r["patient_depth_class"] for r in summary["results"]}
         best = {}
         for row in bundle.get("rows", []):
-            if row.get("batch") != stem or row.get("model") != model:
+            if (row.get("batch") != stem or row.get("model") != model
+                    or row.get("tierb_split") == "holdout"):
                 continue

(with the load_summary holdout filter from the companion finding, `classes` no longer contains holdout indices either; regenerate the site file)
```
Verifier correction: As filed, plus two sharpenings and one scoping caveat. (a) The violation is double: besides the interim aggregate (by_class n/mean_recovery over 3 sealed rows), the three holdout pairs of pairs_20260711T051145Z (indices 1, 38, 47) are individually published in translation.pairs with per-pair recovery values and depth classes; a direct breach of Amendment 3's publication-side withholding rule (in force 2026-07-14; the file was generated 2026-07-16T14:14:12Z, and the site's own data/urgency_shift.json correctly withholds these rows, proving the export consumed the unwithheld engine-local bundle). (b) The payload's scope string self-labels "Amendment 1 exploration split only" (export_jlens_depth.py:264-265), making the published file internally contradictory. (c) Caveat: H-D1 is registered on post-A2 batches (stamps after the 2026-07-14 adoption); pairs_20260711T051145Z is pre-A2, so the registered endpoint itself is not yet contaminated; "descriptive precursor" stands but should not be read as endpoint contamination. Fix note: the proposed row-flag filter is sufficient here because the join requires batch == stem (all rows of a stamped Tier B batch carry tierb_split), but the strictly Amendment-3-compliant form is phrase-keyed exclusion (exclude any row whose clinical_prompt is flagged holdout anywhere in the bundle), matching urgency_shift.py's publish-side logic at lines 361-363; and the regenerated site file must also drop the 3 pairs from translation.pairs, not just from by_class. read_map: [(engine urgency_shift.json [root bundle], scripts/export_jlens_depth.py translation_split, rows[].batch/model/index/urgency_recovery/tierb_split/clinical_prompt), (trace_out/<stem>__jlens_gemma-2-2b/jlens_summary.part_01.json, export_jlens_depth.load_summary/translation_split, results[].index/patient_depth_class), (frontend data/jlens_depth.json, technical router + depth figures, translation.pairs[].set/index/class/recovery + translation.by_class.{n,mean_recovery} + scope + generated_utc), (data/simulated/pairs_20260711T051145Z.json, scripts/tierb_split.is_holdout membership recount, pairs[].top_prompt [hashed only, no text emitted]), (ops/dashboard.json, tierb_split.tierb_start_stamp, tierb.start_utc), (frontend data/urgency_shift.json, withholding cross-check, rows[].batch/model/index)]

Found by: p-amendments. Verified: CONFIRMED.

#### F2-H04 · `engine:scripts/export_jlens_depth.py:203` · prereg-mismatch

The published steering-pilot hijack count (rank 1 back in 11 of 12, rendered at technical/index.html:842 from data/jlens_depth.json steering.by_class) includes 3 sealed-holdout Tier B pairs; export_jlens_depth.py applies no tierb_split filter anywhere, violating Amendment 1 ('published aggregate counts use ONLY the ~90% exploration split', tierb_split.py docstring lines 5-7), Amendment 3's phrase-keyed everywhere-exclusion and publication-side withholding from 2026-07-14 (prereg_amendment3_holdout.md:25-30), and the file's own published scope string 'Amendment 1 exploration split only' (jlens_depth.json line 4).

Evidence:
```
Published: patientwords/data/jlens_depth.json:1568-1586 steering.by_class.suppressed = {n:12, restored:11}. Split membership by the registered rule sha1(clinical_prompt)%10==0 (preregistration_tierB.md:93-95; tierb_split.py:32-33; Tier B start 2026-07-10T01:14:38Z in ops/dashboard.json): spec items (pairs_20260711T051145Z, index 49), (pairs_20260711T131752Z, index 19), (pairs_20260711T131752Z, index 38) — 3 of the 12 counted hijack pairs — are holdout-flagged, plus the held item (pairs_20260711T051145Z, index 1) which does not enter published counts. Exploration-split-only recount of the same committed summaries: suppressed n=9, restored=8 → the registered-population value is 8/9, not the published 11/12. Capture side is holdout-free: absent {n:3, restored:2, unresolvable:9} reproduces exactly (failure = (pairs_20260712T051903Z, index 35), target below the top-8 window at both swap layers). Exporter has zero occurrences of tierb_split/is_holdout (grep -n tierb scripts/export_jlens_depth.py → none); the same unfiltered exporter also publishes 21 holdout-flagged pairs across the five pairs_* blocks[].pairs lists and 3 holdout-flagged pairs (all pairs_20260711T051145Z) inside translation.pairs feeding the adjacent translation column. Reproduction (membership + exploration recount, run from the engine root, read-only): python3 -c "import json,glob,hashlib;H=lambda p:int(hashlib.sha1(p.encode()).hexdigest(),16)%10==0;B={s:json.load(open('data/simulated/%s.json'%s)) for s in ('pairs_20260711T051145Z','pairs_20260711T131752Z','pairs_20260712T051903Z')};P={};
import itertools
for f in sorted(glob.glob('trace_out/*jsteer_*/jsteer_summary.part_*.json')):
 for r in json.load(open(f))['results']:
  k=(r['dataset'],r['spec_index']);e=P.setdefault(k,{'c':r['class'],'u':False,'m':False,'r':False})
  if r.get('steer_unresolvable'):e['u']=True;continue
  s={v['final_rank'] for kk,v in r['calls'].items() if kk.endswith('_swap')}
  if s:e['m']=True;e['r']=e['r'] or (1 in s)
for split in ('all','explore'):
 import collections;c=collections.defaultdict(lambda:[0,0])
 for (ds,i),e in P.items():
  if split=='explore' and ds in B and H(B[ds][i-1]['top_prompt']):continue
  if e['m']:c[e['c']][0]+=1;c[e['c']][1]+=e['r']
 print(split,dict(c))" → all: hijack [12,11], capture [3,2]; explore: hijack [9,8], capture [3,2].
```
Proposed fix:
```diff
--- a/scripts/export_jlens_depth.py
+++ b/scripts/export_jlens_depth.py
@@ -29,6 +29,12 @@
 import argparse
 import difflib
 import json
 from datetime import datetime, timezone
 from pathlib import Path
+try:
+    from scripts.tierb_split import is_holdout, is_tierb_batch, tierb_start_stamp
+except ImportError:
+    from tierb_split import is_holdout, is_tierb_batch, tierb_start_stamp
+
+_TIERB_START = tierb_start_stamp()
+
+def _sealed(dataset, index):
+    """Amendment 1/3 phrase-keyed holdout seal for every published aggregate."""
+    if not is_tierb_batch(dataset or "", _TIERB_START):
+        return False
+    rows = json.loads((Path("data/simulated") / f"{dataset}.json").read_text(encoding="utf-8"))
+    return is_holdout(rows[index - 1]["top_prompt"])
@@ -213,6 +219,8 @@ def steering_split(trace_root=Path("trace_out")):
         for r in summary.get("results", []):
             key = (r.get("dataset"), r.get("spec_index"))
+            if _sealed(r.get("dataset"), r.get("spec_index")):
+                continue
             e = pairs.setdefault(key, {"class": r.get("class"), "unres": False,

(apply the same _sealed(stem, r["index"]) skip in build_block() and translation_split(), add a holdout_withheld count to the payload, re-export, and republish the site copy — suppressed becomes {n:9, restored:8}; the page needs no change since it renders whatever the file carries.)
```
Verifier correction: Finding stands as written, with two trivial precision notes: the published steering block sits at patientwords/data/jlens_depth.json lines 1571-1587 (suppressed counts at 1573-1574), and the registered hash rule is at preregistration_tierB.md lines 94-96. The Amendment 1 prereg paragraph itself enumerates interim analyses; the explicit 'published aggregate counts' phrasing is in tierb_split.py's docstring (the registered rule's single implementation), and Amendment 3 rule 5 independently extends the exclusion to every published aggregate and public data file; so the violation holds under either reading. Exploration-split-only published value: hijack restored 8 of 9 (capture 2 of 3 unchanged).

Found by: r-steering. Verified: CONFIRMED.

#### F2-H05 · `engine:scripts/jlens_insights.py:58` · prereg-mismatch

The published jlens census includes 38 sealed Tier B holdout rows (of n_pairs=476) in its aggregates AND publishes their per-row formation measurements in points[], violating the registered exploration-split-only rule and the site's own withholding claim.

Evidence:
```
jlens_insights.py contains no reference to tierb_split/is_holdout (grep: zero hits); collect() at L58 ingests every pairs_* jlens summary unconditionally. The registered rule (scripts/tierb_split.py docstring L5-7: 'Interim analyses ... published aggregate counts) use ONLY the ~90% exploration split'; docs/prereg_amendment3_holdout.md disclosure 2: 'From 2026-07-14 the exporter and the urgency publisher withhold holdout phrases from the public data files'). Applying the registered rule (sha1(prompts.clinical) % 10 == 0, is_tierb_batch >= tierb.start_utc 2026-07-10T01:14:38Z) to the census inputs: pairs_20260711T051145Z 6/50, pairs_20260711T131752Z 5/50, pairs_20260712T051903Z 6/50, pairs_20260712T163501Z 7/100, pairs_20260713T050939Z 8/100, pairs_20260714T135150Z 6/100 = 38 holdout rows included (keying verified: jlens prompts.clinical == batch file top_prompt == the string urgency_shift.py hashes, 0 mismatches). Published data/jlens_insights.json:6 'n_pairs: 476' vs compliant exploration-only census 438 (membership count only; no statistics were computed over holdout rows). points[] publishes each holdout row's (dataset, index, clin_formed, pat_formed, class), and (dataset,index) joins to the public engine batch file data/simulated/<dataset>.json to recover the phrase — the same phrases export_frontend_simulated.py deliberately withholds (L212-218, holdout_withheld). The site claim at patientwords/technical/index.html:646 ('the pre-registered confirmatory holdout is withheld from this site's data files until the registered endpoint runs') and index.html:456 are false for this data file. Sibling exporter scripts/export_jlens_depth.py has the same gap (zero tierb/holdout hits) — noted for the owning lane. Repro (counts only): python3 -c "import json,glob,sys; sys.path.insert(0,'/home/user/audit-wb/patientwords-engine/scripts'); from tierb_split import is_holdout,is_tierb_batch; print(sum(sum(1 for r in json.load(open(p))['results'] if is_holdout((r.get('prompts') or {}).get('clinical'))) for p in glob.glob('/home/user/audit-wb/patientwords-engine/trace_out/pairs_*__jlens_gemma-2-2b/jlens_summary.part_*.json') if is_tierb_batch(p.split('/')[-2].split('__jlens_')[0],'20260710T011438Z')))" -> 38
```
Proposed fix:
```diff
--- a/scripts/jlens_insights.py
+++ b/scripts/jlens_insights.py
@@ -14,6 +14,10 @@
 import argparse
 import json
 from collections import defaultdict
 from pathlib import Path
+try:
+    from tierb_split import is_holdout, is_tierb_batch, tierb_start_stamp
+except ImportError:
+    from scripts.tierb_split import is_holdout, is_tierb_batch, tierb_start_stamp
@@ def collect(trace_root: Path):
     per_model = defaultdict(list)
+    start = tierb_start_stamp()
+    holdout_excluded = 0
     for part in sorted(trace_root.glob("*__jlens_*/jlens_summary.part_*.json")):
@@ inside the results loop, before building row:
+            if is_tierb_batch(dataset, start) and is_holdout(
+                    (r.get("prompts") or {}).get("clinical")):
+                # Amendment 1/3: sealed confirmatory holdout - excluded from every
+                # published aggregate and from the per-pair points.
+                holdout_excluded += 1
+                continue
@@ return both:
-    return per_model
+    return per_model, holdout_excluded
@@ main(): thread the count through analyze() into the payload as
+        "holdout_excluded": holdout_excluded,
then regenerate ops/jlens_insights.json and the site copy (exploration split only), and add a regression test asserting a synthetic holdout-hash pair never appears in points or counts. Note for the main session: the regenerated headline numbers (n_pairs 438; taxonomy/window/formation recomputed on the exploration split) will differ from the currently published ones.
```
Verifier correction: As filed, with three precision notes: (a) both false site-claim citations live in patientwords/technical/index.html (lines 456 and 646; root index.html contains no holdout claim; line 385 of technical/index.html is a third instance); (b) the hash rule is int(sha1(clinical_prompt).hexdigest(),16) % 10 == 0 (finder's "sha1(...) % 10" is shorthand for the same tierb_split.is_holdout rule); (c) the violation also contaminates the ops copy (engine ops/jlens_insights.json, same 476) and potentially the instruction_tuning paired sub-block, which pairs base and IT rows with no holdout filter either; the regeneration must cover ops, site, and that sub-block. read_map: [(trace_out/*__jlens_gemma-2-2b/jlens_summary.part_*.json, scripts/jlens_insights.py collect(), prompts.clinical/parse_status/depth/index), (ops/dashboard.json, scripts/tierb_split.py tierb_start_stamp(), tierb.start_utc), (data/jlens_insights.json, patientwords/technical/index.html:682 JS, n_pairs/points[].dataset/.index/.clin_formed/.pat_formed/.class), (data/simulated/pairs_<stamp>.json, export_frontend_simulated.py, top_prompt→prompts.clinical join), (docs/prereg_amendment3_holdout.md + scripts/tierb_split.py docstring, registered-rule text, disclosure 2/endpoint 5)]

Found by: r-jlens. Verified: CONFIRMED.

#### F2-H06 · `engine:scripts/jlens_insights.py:74` · recompute-divergence

jlens_insights.py has no holdout exclusion at all: the published patientwords/data/jlens_insights.json contains 37 row-flagged Tier B holdout pairs (38 by the acceptance-time hash) as individually identified per-pair points (dataset+index+class+ranks), and every published aggregate (n_pairs=476, formation quantiles, capture/hijack taxonomy, window_sensitivity, instruction_tuning) is an interim analysis computed over holdout rows; violating Amendment 1's 'interim analyses use ONLY the exploration split' and Amendment 3's endpoint rule 5.

Evidence:
```
Code: collect() lines 55-98 globs every `*__jlens_*/jlens_summary.part_*.json`, guards txcorpus/arm stems and parse_status, but has no tierb/holdout filter (grep 'holdout|tierb' over the file: 0 hits); main() writes the site copy at line 276. Registered: Amendment 1 — "Interim analyses during the collection week (nightly critic runs, dashboard deltas, synthesis drafts) use ONLY the ~90% exploration split."; Amendment 3 Endpoint 5 — "holdout phrases stay excluded from every published aggregate and withheld from public data files." Recount (membership only) on frontend HEAD: 38 of 476 points rows are holdout pairs (pairs_20260713T050939Z:8, pairs_20260712T163501Z:7, pairs_20260711T051145Z:6, pairs_20260712T051903Z:6, pairs_20260714T135150Z:6, pairs_20260711T131752Z:5), each published per-pair with dataset+index join keys, formation layers and class; the published aggregates (formation.clinical n=331 median 19; taxonomy capture n=44 / hijack n=31 / held n=293) are computed over them. Consumer: technical/index.html:682. Repro: intersect points[].(dataset,index) of /home/user/audit-wb/patientwords/data/jlens_insights.json with sha1(top_prompt)%10==0 indices of the Tier B batch files.
```
Proposed fix:
```diff
--- a/scripts/jlens_insights.py
+++ b/scripts/jlens_insights.py
@@ -16,6 +16,11 @@
 from collections import defaultdict
 from pathlib import Path
 
+import sys
+sys.path.insert(0, str(Path(__file__).resolve().parent))
+from tierb_split import is_holdout, is_tierb_batch, tierb_start_stamp
+
@@ def collect(trace_root: Path):
     per_model = defaultdict(list)
+    start = tierb_start_stamp("ops/dashboard.json")
+    _batches = {}
     for part in sorted(trace_root.glob("*__jlens_*/jlens_summary.part_*.json")):
         dataset = part.parent.name.split("__jlens_")[0]
@@ inside the results loop, before building row:
         for r in summary.get("results", []):
+            # Amendment 1/3: confirmatory-holdout pairs never enter interim
+            # analyses or public data files. Keyed on the ACCEPTED batch prompt.
+            if is_tierb_batch(dataset, start):
+                if dataset not in _batches:
+                    fp = Path("data/simulated") / f"{dataset}.json"
+                    _batches[dataset] = (json.loads(fp.read_text(encoding="utf-8"))
+                                         if fp.is_file() else None)
+                b = _batches[dataset]
+                idx = r.get("index") or 0
+                if b and 0 < idx <= len(b) and is_holdout(b[idx - 1].get("top_prompt")):
+                    continue
Then regenerate ops/jlens_insights.json and the site copy; disclose the correction in docs/prereg_divergence_log.md.
```
Verifier correction: Finding is real; two statements need adjustment. (1) Category: this is not a recompute-divergence (the site copy is byte-identical to the engine ops copy and both faithfully reflect the code); it is a preregistration/holdout-seal violation: jlens_insights.py has no holdout exclusion, so the violation is generated-in, not drift or staleness. (2) Counts, precisely: of the 476 published points, 450 are Tier B; 38 points hash holdout under the registered sha1(clinical_prompt)%10==0 rule, covering 37 distinct holdout phrases (the 38/37 gap is one phrase contributing two points, not two competing membership definitions). Everything else stands as filed: no tierb/holdout logic anywhere in scripts/jlens_insights.py (collect() lines 55-98, guard only at 60-61, results loop at line 74); all published aggregates (n_pairs=476, formation quantiles, taxonomy, window_sensitivity, instruction_tuning) are computed over holdout rows; points[] publishes dataset+index+class+formation layers per pair, individually identifying holdout pairs joinable to the public engine batch files; violating Amendment 1's exploration-split-only rule (extended to lens work verbatim by Amendment 2) and both prongs of Amendment 3 rule 5 (excluded from every published aggregate; withheld from public data files). The consumer surface is patientwords/technical/index.html, which renders n_pairs, formation medians/never-formed counts, the per-pair dot strip from points[], and the taxonomy; all currently holdout-contaminated. The proposed minimal fix (import tierb_split, skip rows whose batch top_prompt hashes holdout in Tier B batches, regenerate ops+site copies, log in docs/prereg_divergence_log.md) is correct and consistent with the phrase-keyed exclusion pattern already used in urgency_shift.py:356-364. read_map: [(patientwords/data/jlens_insights.json, patientwords/technical/index.html, [n_pairs, model, formation.{clinical,patient,clinical_never,patient_never,n_layers}, points[].{dataset,index,class,clin_formed,pat_formed}, taxonomy, window_sensitivity, instruction_tuning, exemplars]), (patientwords-engine/trace_out/*__jlens_*/jlens_summary.part_*.json, patientwords-engine/scripts/jlens_insights.py::collect, [graph_model, results[].{index,parse_status,depth.clinical,depth.patient,patient_depth_class}]), (patientwords-engine/data/simulated/pairs_<stamp>.json, holdout-membership verification join via points[].{dataset,index}, [top_prompt (hash membership only, no text)]), (patientwords-engine/ops/dashboard.json, patientwords-engine/scripts/tierb_split.py::tierb_start_stamp, [tierb.start_utc]), (patientwords-engine/ops/jlens_insights.json, staleness comparison vs patientwords/data/jlens_insights.json, [entire payload; byte-identical])]

Found by: p-holdout,p-amendments. Verified: CONFIRMED.

#### F2-H07 · `engine:scripts/retrace_consistency.py:44` · prereg-mismatch

The public repeatability file data/retrace_consistency.json contains 2 sealed holdout phrases verbatim (rows[].clinical_prompt with per-run probabilities) and counts them in its published aggregates; the script has no holdout filter.

Evidence:
```
Code: collect() line 33 globs every `*/batch_summary*.json` and line 44 ingests every result row keyed by `(model, clin, pat)` with no tierb/holdout check (grep 'holdout|tierb' over the file: 0 hits). Registered: Amendment 3 Endpoint 5 — "holdout phrases stay excluded from every published aggregate and withheld from public data files."; Disclosures 2 — "From 2026-07-14 the exporter and the urgency publisher withhold holdout phrases from the public data files." Recount (membership only) on frontend HEAD: 2 of 68 rows in /home/user/audit-wb/patientwords/data/retrace_consistency.json have clinical_prompt in the sealed holdout phrase set (the repeatability_r1-r3 re-trace of a holdout phrase; consistent with the 3 repeatability leak rows in the collector), and aggregates pairs_retraced=68 / top_word_stable_pairs=68 include them. Consumers: methods.html:636, simulated-scenarios/index.html:1168. Compounds accepted F-M26 (site copy is a manual copy). Repro: python3 -c "import json; us=json.load(open('/home/user/audit-wb/patientwords-engine/urgency_shift.json')); h={r['clinical_prompt'] for r in us['rows'] if r.get('tierb_split')=='holdout'}; rc=json.load(open('/home/user/audit-wb/patientwords/data/retrace_consistency.json')); print(sum(1 for r in rc['rows'] if r['clinical_prompt'] in h))" -> 2.
```
Proposed fix:
```diff
--- a/scripts/retrace_consistency.py
+++ b/scripts/retrace_consistency.py
@@ -27,6 +27,17 @@
 from pathlib import Path
+
+import sys
+sys.path.insert(0, str(Path(__file__).resolve().parent))
+from tierb_split import is_holdout, is_tierb_batch, tierb_start_stamp
+
+def _tierb_holdout_phrases(simulated_dir=Path("data/simulated")):
+    start = tierb_start_stamp("ops/dashboard.json")
+    return {p.get("top_prompt")
+            for bp in sorted(simulated_dir.glob("pairs_*.json"))
+            if not bp.name.endswith(".report.json") and is_tierb_batch(bp.stem, start)
+            for p in json.loads(bp.read_text(encoding="utf-8"))
+            if is_holdout(p.get("top_prompt"))}
@@ -41,6 +52,7 @@
+        sealed = _tierb_holdout_phrases()
         for row in summary.get("results", []):
             prompts = row.get("prompts") or {}
             clin, pat = prompts.get("clinical"), prompts.get("patient")
+            if clin in sealed:
+                continue  # amendment 3: phrase-keyed seal, all runs

(hoist the sealed-set build out of the loop in the real patch; regenerate ops/retrace_consistency.json and replace the site copy)
```
Verifier correction: The public repeatability file data/retrace_consistency.json (frontend HEAD bbf5874; byte-identical engine copy at ops/retrace_consistency.json, also public) contains 5 sealed Tier B holdout phrases; 2 verbatim and 3 as their first 70 characters (rows[].clinical_prompt is truncated by clin[:70] at scripts/retrace_consistency.py:96, which is also why the original exact-match count found only 2); together with their run lists, probability spreads, and top-word stability flags (not per-run probabilities as originally stated), and counts all 5 in its published aggregates (pairs_retraced=68, top_word_stable_pairs=68, spread_lists_identical_pairs=68, and the prob_spread_mean/max pools), which methods.html:636-646 and simulated-scenarios/index.html:1168-1176 render. scripts/retrace_consistency.py has no holdout filter anywhere (collect() line 33 globs all batch summaries, line 44 ingests every row keyed (model, clin, pat)); it was not covered by the 2026-07-14 exporter/urgency-publisher withholding fix, so the file violates Amendment 3 Endpoint 5 ("holdout phrases stay excluded from every published aggregate and withheld from public data files") at current HEAD, and its aggregates also contradict Disclosure 2's assertion that "no interim aggregate has ever included them" (this published aggregate has included holdout rows since 2026-07-13). Severity high stands. The proposed fix is sound (batch field top_prompt confirmed; tierb_split.py API confirmed) provided the sealed-set build is hoisted out of the per-part loop, the truncation-safe comparison uses the full clin from batch summaries (it does), both ops and site copies are regenerated, and; per phrase-keyed sealing; the filter keys on the phrase regardless of which run (repeatability_r*, _txopus/_txplacebo re-traces) produced the row, which the proposed clin-in-sealed check achieves.

Found by: p-amendments. Verified: CONFIRMED.

#### F2-H08 · `engine:scripts/tierb_split.py:65` · prereg-mismatch

The registered rule assigns the split 'on acceptance' by sha1 of the pair's clinical prompt, but stamp_rows/exporter hash the TRACE-TIME prompt, which for 13 Tier B gemma traces carries a screening probe extension; the hash flips split membership for 6 pairs, so 3 acceptance-rule holdout pairs are published in simulated_scenarios.json (one, pairs_20260713T050939Z#87, with measurements whose gemma-3-4b-it/qwen3-1.7b rows are row-flagged holdout in the collector; the other two publish measurements whose only row-file rows are all holdout-flagged), one probe-extended row hashing holdout is published in the archive, one such gemma row survives into the confirmatory populations of paired_stats_rigor.py and convergence_tracker.py, and the payload's holdout_withheld=62 disagrees with the acceptance-rule count of 64 over the same traced pairs.

Evidence:
```
Registered: docs/preregistration_tierB.md:93-95 'On acceptance, every Tier B pair is assigned to an analysis split by deterministic hash: pairs where `sha1(clinical_prompt)` mod 10 == 0'. Code: tierb_split.py:65 `held = is_holdout(row.get("clinical_prompt"))` (traced string) and export_frontend_simulated.py:216-217 `is_holdout(base_r["prompts"]["clinical"])` with the comment at :215 claiming the traced prompt is 'identical to the traced prompts.clinical' — false for probe-extended pairs — while export_archive.py:99 hashes `pair.get("top_prompt")` (accepted string). Recount: 13 Tier B gemma-traced pairs have prompts differing from the batch file, all 13 with screening.probe_extension set; 6 flip is_holdout; published payload holdout_withheld=62 vs 64 acceptance-hash holdout among the same traced pairs; 3 acceptance-holdout pairs published as scenarios (pairs_20260710T050657Z#4, pairs_20260712T163501Z#63, pairs_20260713T050939Z#87); row file shows per-model split disagreement for ('pairs_20260713T050939Z',87): {'gemma-2-2b':'explore','gemma-3-4b-it':'holdout','qwen3-1.7b':'holdout'}. Repro (counts only): python3 -c "import json,glob,hashlib; H=lambda p: bool(p) and int(hashlib.sha1(p.encode()).hexdigest(),16)%10==0; mm=fl=0;
import re; R=re.compile(r'pairs_(\d{8}T\d{6}Z)')
for bf in glob.glob('data/simulated/pairs_*.json'):
  stem=bf.split('/')[-1][:-5]; m=R.fullmatch(stem)
  if bf.endswith('.report.json') or not m or m.group(1)<'20260710T011438Z': continue
  b=json.load(open(bf))
  for part in glob.glob(f'trace_out/{stem}/batch_summary.part_*.json'):
    for r in json.load(open(part)).get('results',[]):
      fp=b[r['index']-1].get('top_prompt'); cp=(r.get('prompts') or {}).get('clinical')
      if fp and cp and fp!=cp: mm+=1; fl+=(H(fp)!=H(cp))
print(mm,fl)" -> 13 6.
```
Proposed fix:
```diff
Canonicalize on the ACCEPTED prompt and withhold under either string until an amendment resolves the 6 already-flipped pairs (the holdout must not be re-split silently — Amendment 3 forbids re-splitting, so this needs a logged divergence/amendment BEFORE any unsealing).
--- a/scripts/tierb_split.py
+++ b/scripts/tierb_split.py
@@
-def stamp_rows(rows, dashboard_path="ops/dashboard.json"):
+def stamp_rows(rows, dashboard_path="ops/dashboard.json", accept_prompts=None):
@@
-        held = is_holdout(row.get("clinical_prompt"))
+        canonical = (accept_prompts or {}).get((row.get("batch"), row.get("index")))
+        # assignment is at ACCEPTANCE; trace-time prompts may carry a screening
+        # probe extension that changes the hash. Seal under either reading.
+        held = is_holdout(canonical) or is_holdout(row.get("clinical_prompt"))
--- a/scripts/urgency_shift.py (topics loop already reads every batch file)
@@ -153,6 +153,8 @@
     for i, pair in enumerate(batch, start=1):
         topics[(stem, i)] = (pair.get("generation") or {}).get("topic")
+        accept_prompts[(stem, i)] = pair.get("top_prompt")
@@
-n_holdout = stamp_rows(rows)
+n_holdout = stamp_rows(rows, accept_prompts=accept_prompts)
--- a/scripts/export_frontend_simulated.py
@@ -216,3 +216,5 @@
-        if is_tierb_batch(stem, _TIERB_START) and is_holdout(
-                base_r["prompts"]["clinical"]):
+        if is_tierb_batch(stem, _TIERB_START) and (
+                is_holdout(pair.get("top_prompt"))
+                or is_holdout(base_r["prompts"]["clinical"])):
Plus a docs/prereg_divergence_log.md row disclosing the 6 mis-assigned pairs and the 3 already-published scenarios.
```
Verifier correction: Core finding confirmed as filed, with one evidence correction: the "holdout_withheld=62 disagrees with the acceptance-rule count of 64" clause is misattributed. 64 is the acceptance-hash holdout count over pairs traced by ANY model in the payload's Tier B batches; the +2 pairs (pairs_20260710T092635Z#20, pairs_20260711T051145Z#49) were traced only by logits models and are never iterated by the exporter (neither published nor counted withheld); a pre-existing scope artifact, not the hash bug. Over the pairs the exporter actually iterates (gemma base results), trace-hash and accept-hash counts are BOTH 62 because the 6 flips are symmetric (3 accept-holdout published, 3 accept-explore withheld); holdout_withheld would remain 62 after the fix, so the payload count does not by itself evidence the bug. Secondary precision: the archive row (gemma #8, probe_extension='a', published clinical_prompt hashes holdout) is not itself a registered-rule violation; under the acceptance rule #8 is exploration, so its inclusion is correct; it evidences the cross-artifact hash-base inconsistency (export_archive.py:99 accepted string vs tierb_split.py:65 / export_frontend_simulated.py:216-217 traced string) and that a holdout-hashing prompt string is nonetheless public. The confirmed registered-rule violations are: (a) 3 acceptance-rule holdout pairs published in data/simulated_scenarios.json (#4 and #63 via other-model measurements whose only collector rows are all holdout-flagged; #87 including a gemma measurement), (b) #87's probe-extended gemma measurement surviving into the exploration populations of paired_stats_rigor.py (phrase-keyed exclusion defeated by the string mismatch) and convergence_tracker.py, which feed the published model_stats.json and convergence.json, and (c) 3 acceptance-rule exploration pairs (#8,#19,#48) wrongly withheld from the payload. Severity high; the proposed seal-under-either-string fix plus a prereg divergence-log/amendment entry (Amendment 3 line 92 forbids re-splitting) is the right minimal shape, modulo initializing accept_prompts={} in the urgency_shift.py hunk.

Found by: p-holdout. Verified: CONFIRMED.

#### F2-H09 · `engine:scripts/urgency_shift.py:211` · recompute-divergence

The published site summary (patientwords/data/urgency_shift.json summary block) is computed from row-tag-keyed arows, not the phrase-keyed exclusion Amendment 3 discloses as in force since 2026-07-14: 11 split-less rows of 5 holdout-flagged phrases (pairs_20260711T051145Z_txopus 4, _txplacebo 4, repeatability_r1-r3 3) enter measurements, per_model, concordance and; materially; the mitigation block: published mitigation.n=91 and mean_urgency_recovery=0.1334 vs 83 and 0.1442 phrase-keyed; measurements 4542 vs 4531.

Evidence:
```
Code: `arows = [r for r in rows if r.get("tierb_split") != "holdout"]` (line 211) — row-flag only. Registered (prereg_amendment3_holdout.md, Disclosures 1): "Exclusion is now keyed on the clinical phrase: a phrase flagged holdout anywhere is excluded everywhere." and divergence log 2026-07-15 row: "exclusion keyed on clinical phrase so split-less re-run rows of a holdout phrase cannot leak into interim numbers". Recount on committed HEAD artifacts: 316 rows across 67 phrases are flagged holdout; 11 additional rows carry NO tierb_split flag but share a holdout clinical_prompt (batches pairs_20260711T051145Z_txopus x4, pairs_20260711T051145Z_txplacebo x4, repeatability_r1/r2/r3 x1 each — suffix/re-run batch names fail tierb_split._BATCH_RE.fullmatch so stamp_rows never flags them). Published site value: data/urgency_shift.json summary.measurements = 4542 (includes the 11); phrase-keyed rule gives 4531. summary.mitigation.n = 91 includes 8 of these rows (they carry urgency_recovery). per_model_deduped (all 11 rows are gemma-2-2b) feeds the homepage figure (index.html:657), start-here (543), simulated-scenarios (646). Repro: python3 -c "import json; d=json.load(open('/home/user/audit-wb/patientwords-engine/urgency_shift.json')); rows=d['rows']; h={r['clinical_prompt'] for r in rows if r.get('tierb_split')=='holdout'}; leak=[r for r in rows if r.get('tierb_split') is None and r['clinical_prompt'] in h]; print(len(leak), d['summary']['measurements'], sum(1 for r in leak if r.get('urgency_recovery') is not None))" -> 11 4542 8. Unlogged: the divergence log claims this leak class was closed.
```
Proposed fix:
```diff
--- a/scripts/urgency_shift.py
+++ b/scripts/urgency_shift.py
@@ -208,7 +208,11 @@
 from tierb_split import stamp_rows  # noqa: E402  (script-style module)
 n_holdout = stamp_rows(rows)
-arows = [r for r in rows if r.get("tierb_split") != "holdout"]
+# Phrase-keyed exclusion (Amendment 3, 2026-07-14): a phrase flagged holdout
+# anywhere is excluded everywhere, including split-less re-run/alias rows.
+_holdout_phrases = {r["clinical_prompt"] for r in rows
+                    if r.get("tierb_split") == "holdout"}
+arows = [r for r in rows if r.get("tierb_split") != "holdout"
+         and r["clinical_prompt"] not in _holdout_phrases]
(and reuse _holdout_phrases in the publish path at :361-363 instead of rebuilding it). Regenerate the site copy; add a tests/ regression asserting no arows phrase appears in the flagged-holdout set.
```
Verifier correction: As filed, plus three refinements. (a) The mitigation discrepancy extends to restored_top_tier: published 56 vs 48 phrase-keyed (8 of the 91 pooled recovery rows are holdout-phrase tx rows). (b) Root cause worth stating in the fix: stamp_rows never flags alias/suffixed batches because tierb_split.py:_BATCH_RE.fullmatch rejects `pairs_<STAMP>_tx*` and `repeatability_r*` names, so those rows are split-less (tierb_split=None), not mis-flagged. (c) The proposed diff (flagged-phrase set membership) matches the disclosed rule text and the existing publish path, but both share a residual gap: a holdout-hash phrase occurring only in never-flagged alias batches would still leak because it is never flagged anywhere; keying on tierb_split.is_holdout(clinical_prompt) for alias-batch rows (or also) closes that. Affected published numbers on frontend data/urgency_shift.json summary: measurements 4542→4531, mitigation {n 91→83, mean_urgency_recovery 0.1334→0.1442, restored_top_tier 56→48}; per_model, per_model_deduped, and concordance blocks also ingest the 11 leak rows (small per-cell shifts). read_map: [(engine urgency_shift.json rows, scripts/urgency_shift.py:211 aggregates, tierb_split/clinical_prompt/urgency_recovery/tier_top_*), (scripts/urgency_shift.py summary, patientwords/data/urgency_shift.json summary block, measurements/mitigation/per_model/per_model_deduped/concordance), (scripts/tierb_split.py stamp_rows, urgency_shift.py:210-211, batch-name fullmatch + sha1 phrase hash), (docs/prereg_amendment3_holdout.md + docs/prereg_divergence_log.md, registered exclusion rule, phrase-keyed sealing disclosure)].

Found by: p-holdout,p-amendments. Verified: CONFIRMED.

#### F2-H10 · `site:index.html:387` · recompute-divergence

Homepage Fig. 3 provenance line hardcodes '45 graphs · 5 baselines + 40 framings' and links the round-1 batch, but the specimen panel it captions is built at runtime from data/dialects.json, which since the 2026-07-17 round-2 publish holds 17 baselines + 136 framings (153 graphs) from batch dialects_20260708T215356Z.

Evidence:
```
Page: '45 graphs · 5 baselines + 40 framings · from the ... dialects_20260708T120729Z.json ...'. Recompute: python3 -c "import json;d=json.load(open('data/dialects.json'));print(len(d['items']), sum(len(i['variants']) for i in d['items']), d['batch'], d['updated'])" -> 17 136 dialects_20260708T215356Z 2026-07-17. The dialect-differences page was updated and guarded (manifest claim '153 (17 baselines + 136 framings'); the homepage copy of the same fact was not.
```
Proposed fix:
```
Rewrite index.html:387 to '153 graphs · 17 baselines + 136 framings' linking data/simulated/dialects_20260708T215356Z.json, then add: {"page": "index.html", "snippet": "153 graphs · 17 baselines + 136 framings", "source": "data/dialects.json", "expr": "[len(d['items']), sum(len(i['variants']) for i in d['items'])]", "expected": [17, 136]}
```
Verifier correction: As stated, with two refinements. (a) The old "45 graphs · 5 baselines + 40 framings" was the then-published traced subset, not the linked batch file's contents; dialects_20260708T120729Z.json holds 8 instructions × 8 framings (64), so the hardcoded numbers now trace to nothing in either repo. (b) The proposed fix is correct but should note, as the existing dialect-differences guard does ("updates when the 3-term gap lands"), that 153/17/136 is itself expected to change when the 3 pending terms are re-traced (batch dialects_20260708T215356Z.json contains 20 instructions × 8 framings = 180 potential graphs); the new index.html guard's expected values must be updated in lockstep at that point. The batch-date prose "dialect framings batch of July 8, 2026" stays correct for the new batch (stamp 20260708T215356Z); only the counts and the linked filename need the change.

Found by: c-unguarded. Verified: CONFIRMED.

### Medium: irreproducible/ambiguous, keying mismatches, drift-prone headline claims

#### F2-M01 · `engine:docs/prereg_amendment2_depth.md:5` · prereg-mismatch

The A2 confirmatory population boundary ('post-A2 batches') is pinned to an adoption commit that is recorded nowhere machine-readable; no commit id in the amendment, no dashboard stamp, no timeline milestone; and no analysis code gates on it, leaving H-D1/H-D2's sample undeterminable and the same-day batch pairs_20260714T135150Z ambiguous.

Evidence:
```
Registered: "'Post-A2 batches' means Tier B generation batches whose stamps postdate the adoption commit of this file." (line 5-6) and Sample: "Pairs from Tier B generation batches whose stamps postdate the approval commit of this amendment". The adoption commit id appears nowhere: ops/dashboard.json has tierb.start_utc but no amendments key (decisions_log 2026-07-14 evening: "Amendment 2 (depth endpoints) SIGNED AS DRAFTED and in force; post-A2 = batches generated after the adoption commit" — still no id/UTC); data/timeline.json milestones contain only 'Tier B pre-registration committed' and 'Tier B collection started'; the worktree is a shallow checkout so git history cannot resolve it either. Grep for a code gate: `grep -rn 'post_a2\|post-A2\|adoption' scripts/` matches only prose comments (translation_scale.py:96,117; export_jlens_depth.py:242-243) — no batch filter exists. Batch pairs_20260714T135150Z is stamped 13:51:50Z on the adoption day; whether it is pre- or post-A2 depends on the unrecorded commit time. Contrast: Amendment 1's boundary is mechanically recorded (tierb.start_utc = 2026-07-10T01:14:38Z) and enforced by tierb_split.is_tierb_batch.
```
Proposed fix:
```diff
--- a/docs/prereg_amendment2_depth.md
+++ b/docs/prereg_amendment2_depth.md
@@ -3,7 +3,9 @@
 **Status: IN FORCE.** Written 2026-07-12, before any data it governs exists;
 adopted as drafted by the owner 2026-07-14 (chat: "sign as drafted"). "Post-A2
 batches" means Tier B generation batches whose stamps postdate the adoption
-commit of this file. Depth claims on pre-A2 data remain exploratory.
+commit of this file — adoption commit `<COMMIT_SHA>` (committed
+`<UTC_TIMESTAMP>`; also recorded machine-readably as
+`amendments.a2.adopted_utc` in ops/dashboard.json, which the H-D1/H-D2
+analysis code MUST gate on, mirroring tierb_split.is_tierb_batch). Batch
+pairs_20260714T135150Z (13:51:50Z, adoption day) is PRE-A2 under this stamp.
+Depth claims on pre-A2 data remain exploratory.

(fill the placeholders from `git log --format='%H %cI' -- docs/prereg_amendment2_depth.md` on a full clone at the commit that flipped Status to IN FORCE, and add the dashboard key via the Routine session, its sole writer)
```
Verifier correction: Same finding with one softening: the sample is not strictly 'undeterminable'; both repos are public and the amendment pins to a commit of a tracked file, so the boundary is recoverable in principle via git archaeology on a full clone (the commit that flipped Status to IN FORCE). The defect, precisely: the A2 adoption commit is recorded in no repo artifact (no SHA/UTC in the amendment, in ops/dashboard.json; no amendments key, in data/timeline.json milestones, or in the decisions_log entry), is enforced by no code (no batch filter exists; no H-D1/H-D2 analysis code exists yet at all), and is unresolvable from the shallow audit worktrees; so the confirmatory population is reproducible only via undocumented out-of-repo archaeology, and the adoption-day batch pairs_20260714T135150Z (13:51:50Z) stays ambiguous until that commit's timestamp is fetched and compared. Contrast with Amendment 1's mechanical boundary (tierb.start_utc + tierb_split.is_tierb_batch) stands. The identical pattern also appears in docs/prereg_amendment4_steering.md:7-8 ('Post-A4 = observational batches generated after the adoption commit of this rename'), so the fix should be applied to both amendments plus a dashboard amendments.{a2,a4}.adopted_utc key written by the Routine session (its sole writer) and a shared batch-boundary gate mirroring tierb_split.is_tierb_batch.

Found by: p-amendments. Verified: CONFIRMED.

#### F2-M02 · `engine:docs/prereg_amendment4_steering.md:66` · prereg-mismatch

Amendment 4's signed power note labels '~10/12 vs ~1/3' as the pilot's 'pair-level' point estimates, but under the amendment's own registered primary outcome (rank-1 at EITHER frozen layer, lines 59-61) the pilot pair-level estimates are 11/12 vs 2/3; the quoted numbers instead match an unregistered BOTH-layer rule, and the confirmed 15-per-class floor delivers ~38% power (not 80%) against the actual primary-rule estimates.

Evidence:
```
Registered text (lines 64-68): 'detecting the pilot's point estimates (~10/12 vs ~1/3 pair-level) needs roughly 12-15 per class at 80% power; 15 is the floor'. Recomputed from the committed jsteer summaries: either-layer pair-level = hijack 11/12, capture 2/3; both-layer pair-level = hijack 10/12 (failures: (pairs_20260711T051145Z,12) with L19_swap rank 4, and (pairs_20260711T131752Z,29)), capture 1/3 ((pairs_20260711T051145Z,41) L19_swap rank 3 restores only at L21) — exactly the note's numbers. Exact one-sided Fisher power, alpha 0.05, equal n per class (full binomial enumeration): 11/12 vs 2/3 → 0.30 at n=12, 0.38 at n=15; 10/12 vs 1/3 → 0.77 at n=12, 0.81 at n=15. Normal-approximation n for 80% power at (0.917, 0.667) is ~32/class. Reproduction: enumerate x1,x2~Binomial(n,p) and count Fisher one-sided p<=0.05 (script in audit sandbox; pure stdlib comb). Caveat noted: the 11/12 hijack estimate itself includes 3 holdout-flagged pairs (see high finding); the exploration-only estimate 8/9 vs 2/3 gives similarly low power (~0.35 at n=15), so the mislabeling stands under either population.
```
Proposed fix:
```diff
--- a/docs/prereg_amendment4_steering.md
+++ b/docs/prereg_amendment4_steering.md
@@ -64,8 +64,10 @@
 - **Minimum n:** 15 classified, resolvable pairs per class before the test
-  runs; until then the comparison stays descriptive. Power note: detecting
-  the pilot's point estimates (~10/12 vs ~1/3 pair-level) needs roughly 12-15
-  per class at 80% power; 15 is the floor, not the target - accumulation
-  continues while batches flow.
+  runs; until then the comparison stays descriptive. Power note (corrected
+  2026-07-17, see divergence log): the figures previously quoted here
+  (~10/12 vs ~1/3) were BOTH-layer restoration rates, not the registered
+  either-layer primary; the pilot's either-layer estimates give ~38% power
+  at n=15 per class (exact one-sided Fisher, alpha .05), reaching 80% near
+  n~=32 per class. 15 remains the floor before any test runs; accumulation
+  continues while batches flow, and the test is not run before adequate n.

(plus a dated entry in docs/prereg_divergence_log.md; since the amendment is signed as drafted, correct via logged erratum rather than silent edit.)
```
Verifier correction: One numeric quibble in a non-load-bearing caveat: the finding states the exploration-only estimate (8/9 vs 2/3) gives ~0.35 power at n=15; exact one-sided Fisher enumeration gives ~0.29 (0.287). The caveat's conclusion (similarly far below 80% under either population) is unchanged. Also, the finding's failure citations (12, 29, 41) are spec_index values (batch-local), not run indices; correct as cited once that field is named. Everything else in the finding, including the proposed erratum-style fix, is accurate as written.

Found by: r-steering. Verified: CONFIRMED.

#### F2-M03 · `engine:docs/preregistration_tierB.md:102` · prereg-mismatch

Amendment 1 rule 2's seed-pair provenance requirement is unimplemented: batch sidecars do not record which seed-pairs file the generator saw, and no analysis implements the registered verbatim-seed exclusion (verified a numeric no-op today: 0 Tier B pairs duplicate seed_union_20260706 prompts).

Evidence:
```
Registered (preregistration_tierB.md, Amendment 1 item 2, lines 101-105): "analyses must additionally record which seed-pairs file the generator saw, and the primary endpoints exclude any accepted pair that duplicates a seed pair verbatim (the existing dedupe validator makes this a no-op in expectation; the rule makes it explicit)." Actual: pairs_20260713T050939Z.report.json keys are run_timestamp/task/model/accepted/rejected/rejection_reasons/rounds/truncated_by_budget/max_spend_usd/cost_usd/usage/batch_file/language_register/topics — no seed-pairs field; scenario_gen.py has --seed-pairs (line 1021) but write_generation_report (lines 980-1006) never records it; paired_stats_rigor.py contains no seed exclusion (grep 'seed' matches only the RNG seed). Numeric impact check: 0 of the Tier B accepted pairs (stamps >= 20260710T011438Z) have top_prompt or bottom_prompt verbatim-equal to any of the 99 seed_union_20260706.json prompts, so no published endpoint number changes today — but the registered recording requirement is unmet and the exclusion is unenforced rather than verified per run.
```
Proposed fix:
```diff
--- a/medlang_circuits/scenario_gen.py
+++ b/medlang_circuits/scenario_gen.py
@@ -1143,6 +1143,8 @@
+    if getattr(args, "seed_pairs", None):
+        extra["seed_pairs_file"] = str(args.seed_pairs)
     report_path = write_generation_report(out, args.command, args.max_spend, result, extra)

(and in paired_stats_rigor.analyze, before dedupe: drop rows whose clinical_prompt appears verbatim in the recorded seed files, reporting the excluded count in the bundle so the registered no-op is verified per run instead of assumed)
```
Verifier correction: Finding stands as written at severity medium, with two sharpenings. (a) The gap is worse than a formality: the workflow's push-path default seed file is medlang_circuits/data/ci_pairs_2panel.json (scenario_generation.yml line 140), not seed_union_20260706.json, so the generator's dedupe validator; the mechanism the amendment leans on for the "no-op in expectation" claim; only screens against whichever file was actually passed, and no committed artifact records which one that was; provenance is recoverable only by resolving each fire's commit from ops/trigger_journal.jsonl against git history of .github/trigger/scenario-generation.json. (b) Independently recomputed no-op: 0 of 907 accepted Tier B pairs (16 batches, stamps >= 20260710T011438Z) are verbatim-equal on either prompt side to any of the 99 distinct seed_union_20260706 prompts, so no published endpoint number changes today. Severity note for the synthesizer: under the strict rubric ("a registered rule is violated" = high) the unmet recording requirement is arguably high; medium is defensible because the exclusion rule's outcome is verifiably vacuous today and no published number is affected; flagging the call rather than silently re-grading.

Found by: p-amendments. Verified: CONFIRMED.

#### F2-M04 · `engine:paired_stats_rigor.json:678` · recompute-divergence

The engine's committed stats bundle is not the output of its committed source row file, and the bundle carries no timestamp or input digest, so the published numbers are irreproducible from any committed input at these HEADs and staleness is undetectable ("source": "urgency_shift.json" points at a file that no longer produces it).

Evidence:
```
paired_stats_rigor.json:678 = '"source": "urgency_shift.json"' and :36 = '"n_rows": 769,' (gemma-2-2b), but rerunning the exact pipeline over the committed sibling row file gives gemma-2-2b n_rows 956 (reproduction: python3 scripts/paired_stats_rigor.py --rows /home/user/audit-wb/patientwords-engine/urgency_shift.json --seed 7 --boot 5000 --site '' --out /tmp/.../engine_rows_rigor.json -> per_model.gemma-2-2b.n_rows 956, penalty mean -0.03 on 803 phrases, vs committed bundle 769 / -0.0336 / 650). Committed row file has 4858 rows; a fresh collector run at HEAD gives 4983. So the committed pair spans three data vintages (bundle ~07-14, rows ~07-15, trace_out through 07-16), and the row snapshot that produced the published bundle exists nowhere in the tree. The bundle's only provenance fields are seed/boot/source (lines 2, 3, 678) — no generated_utc, no row-file digest. docs/referee_panel_20260714.md:326 already flagged 'No version anchor: model_stats.json and urgency_shift.json carry no timestamp or content hash' and it remains unimplemented (not among Audit 1's filed findings).
```
Proposed fix:
```diff
--- a/scripts/paired_stats_rigor.py
+++ b/scripts/paired_stats_rigor.py
@@ def main(argv=None):
     rows = load_rows(args.rows)
     bundle = analyze(rows, models=args.models, boot=args.boot, seed=args.seed)
     bundle["source"] = str(args.rows)
+    import datetime
+    import hashlib
+    bundle["generated_utc"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
+    bundle["source_sha256"] = hashlib.sha256(Path(args.rows).read_bytes()).hexdigest()
+    bundle["source_n_rows"] = len(rows)
     Path(args.out).write_text(json.dumps(bundle, indent=1) + "\n", encoding="utf-8")

And in the Routine's export step (docs/routine_standing_prompt.md "run the export/collection chain"), state that urgency_shift.py and paired_stats_rigor.py must be re-run and committed together in the same cycle so the committed source/bundle pair can never desynchronize silently.
```
Verifier correction: Three refinements to an otherwise accurate finding. (1) The exact-vintage dating (bundle ~07-14, rows ~07-15) is an inference, not provable at these HEADs: the audit worktree is a depth-1 shallow clone, so per-file commit dates are unavailable; what is provable is that at HEAD 9696df4 the committed bundle is not the output of the only committed row file (769 vs 956 gemma-2-2b rows) and the fresh collector adds further rows (4858 -> 4983). (2) The published surface is wider than stated: patientwords/data/model_stats.json at frontend HEAD bbf5874 carries the identical stale numbers (n_rows 769, mean -0.0336, 650 phrases) with no anchor, and scripts/claim_check.py has no manifest entry for model_stats.json/paired_stats_rigor.json/urgency_shift.json, so no existing guard can catch the desync; the proposed fix's new fields do reach the site copy automatically via site_bundle = dict(bundle). (3) In the proposed fix, len(rows) is the post-holdout-exclusion row count (load_rows drops holdout phrases before returning), so the field should be named e.g. source_n_rows_after_holdout_exclusion, or the count taken before exclusion, to avoid a misleading anchor.

Found by: r-model-stats. Verified: CONFIRMED.

#### F2-M05 · `engine:scripts/convergence_tracker.py:112` · prereg-mismatch

convergence_tracker.py excludes holdout row-tag-keyed, not phrase-keyed as Amendment 3 discloses; today the pairs_* fullmatch population filter happens to block the 11 known split-less alias rows, but the published data/convergence.json gemma series already includes the one probe-extension mis-assigned row (pairs_20260713T050939Z#87, holdout-flagged on gemma-3-4b-it/qwen3-1.7b), and any future holdout-phrase re-occurrence inside a pairs_* stem leaks silently while the payload's scope string claims 'Amendment 1 holdout excluded'.

Evidence:
```
Code: `rows = [r for r in bundle["rows"] if r.get("tierb_split") != "holdout"]` (line 112), while the published scope string (lines 118-119) claims "Tier B exploration split only (Amendment 1 holdout excluded)". Registered: amendment 3 Disclosures 1 — "Exclusion is now keyed on the clinical phrase: a phrase flagged holdout anywhere is excluded everywhere." Verified no current divergence: 0 split-less holdout-phrase rows fall inside the BATCH_RE.fullmatch pairs_<STAMP> population at HEAD (python3 membership check over /home/user/audit-wb/patientwords-engine/urgency_shift.json: rows with tierb_split None, batch fullmatch pairs_<stamp>, clinical_prompt in holdout set -> 0). But any future observational-stem re-run that lands rows without flags (the exact mechanism that produced the 11 leak rows elsewhere) enters the published data/convergence.json points silently. paired_stats_rigor.py:87-89 already implements the phrase-keyed rule; this consumer was not updated with it.
```
Proposed fix:
```diff
--- a/scripts/convergence_tracker.py
+++ b/scripts/convergence_tracker.py
@@ -109,7 +109,11 @@
     bundle = json.loads(Path(args.rows).read_text(encoding="utf-8"))
-    rows = [r for r in bundle["rows"] if r.get("tierb_split") != "holdout"]
+    # Phrase-keyed exclusion (Amendment 3): any phrase flagged holdout anywhere
+    # is excluded everywhere (mirrors paired_stats_rigor.load_rows).
+    _hold = {r["clinical_prompt"] for r in bundle["rows"]
+             if r.get("tierb_split") == "holdout"}
+    rows = [r for r in bundle["rows"] if r.get("tierb_split") != "holdout"
+            and r["clinical_prompt"] not in _hold]
(the acceptance-prompt canonicalization in the tierb_split.py fix then also repairs the flipped pair here).
```
Verifier correction: convergence_tracker.py:112 excludes holdout row-tag-keyed (`r.get("tierb_split") != "holdout"`), not phrase-keyed as Amendment 3 (docs/prereg_amendment3_holdout.md:22-26, docs/prereg_divergence_log.md:15) discloses and as paired_stats_rigor.py:84-89 implements. Today the deviation is materially inert: the 11 known split-less alias rows (5 holdout phrases; txopus/txplacebo/repeatability batches) are blocked only by the pairs_* fullmatch population filter at :74, and row-keyed vs phrase-keyed gemma input are both 956 rows. CORRECTION to the finder's published-artifact claim: the published data/convergence.json (generated 2026-07-14T13:37:15Z) does NOT yet include the probe-extension mis-assigned row; its gemma series has no point at stamp 20260713T050939Z (last stamp 20260713T135755Z, n_phrases 650), i.e. batch pairs_20260713T050939Z had not landed in the collector bundle at generation time, so the published copy's "Amendment 1 holdout excluded" scope claim is currently accurate. The leak is pending, not landed: the engine bundle at HEAD contains the explore-flagged, probe-extended gemma-2-2b row of a canonically-holdout phrase (canonical 85-char prompt hashes to holdout mod 10 == 0; the 89-char extended variant hashes to 5) with a numeric language_penalty, and the next nightly regeneration will pull it into the published gemma series (recomputed n_phrases at that stamp: 708 with the row vs 707 without). Neither the current row-keyed exclusion nor exact-string phrase-keyed exclusion catches it; the proposed phrase-keyed fix should land together with the tierb_split.py acceptance-prompt canonicalization to actually seal this row. Severity: medium (drift-prone registered-rule deviation; published number not yet wrong).

Found by: p-holdout,p-amendments. Verified: CONFIRMED.

#### F2-M06 · `engine:scripts/export_jlens_depth.py:210` · fragile-parsing

steering_split() globs every trace_out/*jsteer_*/jsteer_summary.part_*.json and ORs restoration across all landed runs, so (a) the published 'pilot' numbers will silently absorb any future post-Amendment-4 confirmatory jsteer run; pooling the pilot with H-S1 data, which Amendment 4 line 83 explicitly forbids ('never pooled into H-S1'); and (b) the coded outcome is 'rank 1 in ANY swap call of ANY run', more lenient than the registered one-run either-layer rule.

Evidence:
```
Code: 'for part in sorted(trace_root.glob("*jsteer_*/jsteer_summary.part_*.json")):' (line 210) and 'if any(v.get("final_rank") == 1 for v in swaps.values()): e["restored"] = True' (lines 225-226) with e persisted across files via pairs.setdefault (line 217). Two runs already land in the glob (steer_pilot_spec__jsteer_gemma-2-2b, steer_lowdose_spec__jsteer_gemma-2-2b); today their swap arms agree call-for-call on all 15 measured pairs (verified rank-by-rank), so published values are currently unaffected — but the first committed confirmatory run (dir pattern <spec>__jsteer_<model>, per jlens_readout.yml) changes the published exploratory block with no code change and no label change ('EXPLORATORY pilot' note at lines 240-243 stays attached to mixed data).
```
Proposed fix:
```diff
--- a/scripts/export_jlens_depth.py
+++ b/scripts/export_jlens_depth.py
@@ -203,10 +203,14 @@
-def steering_split(trace_root=Path("trace_out")):
+PILOT_JSTEER_DIRS = ("steer_pilot_spec__jsteer_gemma-2-2b",
+                     "steer_lowdose_spec__jsteer_gemma-2-2b")
+
+def steering_split(trace_root=Path("trace_out"), run_dirs=PILOT_JSTEER_DIRS):
     """Pair-level swap restoration by lens class from the landed steering pilot
@@ -209,7 +213,9 @@
     pairs = {}
-    for part in sorted(trace_root.glob("*jsteer_*/jsteer_summary.part_*.json")):
+    parts = [p for d in run_dirs
+             for p in sorted((trace_root / d).glob("jsteer_summary.part_*.json"))]
+    for part in parts:

(post-A4 confirmatory runs then get their own, separately-labeled block/exporter path rather than silently joining the pilot.)
```
Verifier correction: One directional correction: Amendment 4 line 83 forbids pooling the pilot INTO H-S1; the code's actual failure mode is the mirror direction; a future confirmatory (H-S1) jsteer run would be silently absorbed into the published EXPLORATORY-pilot block at the next exporter re-run, producing one published statistic that mixes the two populations the amendment requires kept separate and making the "EXPLORATORY pilot" label (export_jlens_depth.py:240-243; technical/index.html:851) false. Substance and severity of the finding stand as filed; the cross-run any-swap-call OR (lines 225-226) is also undisclosed leniency relative to the documented per-run either-layer rule, currently without numeric effect (both landed runs agree call-for-call on all 15 measured pairs; published by_class independently recomputed and confirmed identical).

Found by: r-steering. Verified: CONFIRMED.

#### F2-M07 · `engine:scripts/jlens_insights.py:181` · doc-drift

The 'unreadable' class is described (payload _ field, classify docstring, and technical page prose) as 'pairs where neither wording ever reads out', but the coded rule assigns it whenever the clinical side never forms and the patient final rank is absent; 5 of the 108 published unreadable rows have a persistently-formed patient side.

Evidence:
```
Code (classify, L114-120): held checked first (pat_final_rank), then 'if row["clin_formed"] is None: return "unreadable"' — patient-side formation never consulted. Published rows contradicting the description (class 'unreadable' with pat_formed non-null): (pairs_20260712T051903Z, 19, pat_formed 20), (pairs_20260712T051903Z, 40, pat_formed 19), (pairs_20260712T163501Z, 2, pat_formed 18), (pairs_20260713T050939Z, 16, pat_formed 20), (pairs_20260713T050939Z, 32, pat_formed 19). Descriptions contradicted: payload _ field (data/jlens_insights.json:2 / jlens_insights.py:180-181) 'pairs where neither wording ever reads out are the "unreadable" class'; classify docstring L107 'the clinical side never forms either'; technical/index.html:273-274 'pairs where neither wording ever reads out are their own class'; index.html:792 and :814 build captions with the same 'neither wording ever reads out' wording applied to the full unreadable count (108). Repro: run the recompute, then count points with class=='unreadable' and pat_formed!=null -> 5.
```
Proposed fix:
```diff
Wording-only fix (no number changes). Engine diff:
--- a/scripts/jlens_insights.py
+++ b/scripts/jlens_insights.py
@@ -107,3 +107,4 @@
-    unreadable: the clinical side never forms either - the pair carries no
+    unreadable: the clinical side never forms - the pair carries no
@@ _ field:
-              "conditioned on clinical-readable pairs; pairs where neither "
-              "wording ever reads out are the 'unreadable' class."),
+              "conditioned on clinical-readable pairs; pairs whose clinical side "
+              "never reads out (and whose patient side does not rank at the final "
+              "layer) are the 'unreadable' class - the patient side may still have "
+              "read out mid-depth."),
Frontend diff (technical/index.html:273-274, :792, :814): replace 'neither wording ever reads out' with 'the clinical side never reads out' in all three places. Alternative (bigger change, not proposed): give the 5 clinical-unreadable/patient-formed-then-lost rows their own class.
```
Verifier correction: Finding correct as filed with one citation fix: the caption-builder lines quoted as 'index.html:792 and :814' are in technical/index.html:792 and technical/index.html:814 (the root index.html contains no 'neither wording ever reads out' text). The proposed frontend diff already targets technical/index.html at those lines, so only the evidence citation needed correcting; all three frontend occurrences to reword are in technical/index.html (273-274, 792, 814), plus the two engine locations (classify docstring L106-107 and the payload _ field L180-181).

Found by: r-jlens. Verified: CONFIRMED.

#### F2-M08 · `engine:scripts/jlens_insights.py:245` · unguarded-claim

The published instruction_tuning block is a self-comparison labeled as a model comparison: every gemma-2-2b-it jlens summary is byte-identical to the base model's except the graph_model string, and the payload carries no integrity flag.

Evidence:
```
For all three shared stems (drift_sentinel_20260714, drift_sentinel_20260715, pairs_20260711T051145Z; 56 rows), the only top-level key differing between <stem>__jlens_gemma-2-2b and <stem>__jlens_gemma-2-2b-it summaries is graph_model ('gemma-2-2b' vs 'gemma-2-2b-it'); every results[].depth is identical. Published block (data/jlens_insights.json:3615-3788): n_paired 31, base_median == it_median ({n:31,q25:18,median:18,q75:21} both), every pairs[] entry base == it; its _ field (jlens_insights.py:245) says only 'patient-side formation layer, same phrases, base vs instruction-tuned'. The sibling artifact data/jlens_depth.json already carries an integrity_note ('gemma-2-2b-it model id returns lens readouts identical to the base model across all measured pairs (verified 2026-07-11); one model is reported until Neuronpedia confirms separate hosts') and the page hardcodes the caveat (technical/index.html:889-892), but jlens_insights.json itself — the collaborator-downloadable file — presents it_median as an IT-model measurement. Also, pairs[] entries drop the dataset key, so duplicate index values (index 2 and 3 appear twice, from the two sentinel stems) are ambiguous. Repro: python3 -c "import json; a=json.load(open('/home/user/audit-wb/patientwords-engine/trace_out/pairs_20260711T051145Z__jlens_gemma-2-2b/jlens_summary.part_01.json')); b=json.load(open('/home/user/audit-wb/patientwords-engine/trace_out/pairs_20260711T051145Z__jlens_gemma-2-2b-it/jlens_summary.part_01.json')); print([k for k in a if a.get(k)!=b.get(k)])" -> ['graph_model']
```
Proposed fix:
```diff
--- a/scripts/jlens_insights.py
+++ b/scripts/jlens_insights.py
@@ analyze(), after building `paired`:
+        identical = bool(paired) and all(p["base"] == p["it"] for p in paired)
         out["instruction_tuning"] = {
             "it_model": it_model,
             "n_paired": len(paired),
             "base_median": quantiles([p["base"] for p in paired]),
             "it_median": quantiles([p["it"] for p in paired]),
-            "pairs": paired,
-            "_": "patient-side formation layer, same phrases, base vs instruction-tuned",
+            "pairs": paired,
+            "identical_readouts": identical,
+            "_": ("patient-side formation layer, same phrases, base vs instruction-tuned"
+                  + ("; the two hosted ids currently return identical readouts on every"
+                     " pair (see jlens_depth integrity_note, verified 2026-07-11), so this"
+                     " is reported as one model, not a tuning comparison" if identical else "")),
         }
Also include the dataset key in each paired entry ({"dataset": r["dataset"], "index": ...}) so duplicate indices are unambiguous.
```
Verifier correction: As stated, with one citation tightening: the hardcoded page caveat spans technical/index.html:886-892 (cap-it caption at 886-887, dd-it-text at 888-892), not 889-892. All other file/line cites (jlens_insights.py:245 and :237; data/jlens_insights.json:3615-3788) are exact on the current HEADs.

Found by: r-jlens. Verified: CONFIRMED.

#### F2-M09 · `engine:scripts/jlens_steer.py:131` · prereg-mismatch

Amendment 4's registered H-S1 procedure (resolvability screen BEFORE class assignment, parse failures excluded and counted, n>=15/class floor, exact test, post-A4 batch gate) is implemented nowhere: the pinned pilot code takes the class from a pre-built spec and only discovers unresolvability mid-run, inverting the registered order, and the A4 adoption commit is unrecorded.

Evidence:
```
Registered (prereg_amendment4_steering.md): "Resolvability screen first: each candidate pair's clinical target is probed once for steer-token resolvability (the endpoint's own 400 is the oracle). Unresolvable pairs are excluded BEFORE classification" (Design); "Classification second"; "Parse failures excluded and counted"; "Minimum n: 15 classified, resolvable pairs per class before the test runs"; "Post-A4 = observational batches generated after the adoption commit of this rename" (line 7-8); "Analysis code: the pilot's parser and summary path (scripts/jlens_steer.py at the adoption commit)". Code: jlens_steer.py line 131-132 `row = {..., "class": item["class"], ...}` — class arrives already assigned in the spec before any steering call; unresolvability is only detected at line 160-166 (`if unsupported and "Could not resolve steer token" in unsupported: row["steer_unresolvable"] = True`) DURING the run — and that check also fires on the swap arm whose steerTokens[0] is the WINNER token (line 54), so a multi-wordpiece winner marks the pair unresolvable even when the clinical target resolves, an exclusion A4 does not register. The only summary path (export_jlens_depth.steering_split, lines 203-246) treats parse-failed swap calls (final_rank None) as not-restored instead of 'excluded and counted', has no min-n gate, no Boschloo/Fisher test, and no post-A4 batch filter; grep for 'post_a4|H-S1' in scripts/: 0 code hits. No confirmatory number is published yet (steering block is labeled EXPLORATORY pilot), so this is a gap, not a wrong published value.
```
Proposed fix:
```diff
--- a/docs/prereg_amendment4_steering.md
+++ b/docs/prereg_amendment4_steering.md
@@ -6,3 +6,6 @@
 either-layer restoration is the primary outcome; the 15-per-class floor is
 confirmed. Post-A4 = observational batches generated after the adoption
-commit of this rename.
+commit of this rename — adoption commit `<COMMIT_SHA>` (`<UTC>`), recorded as
+`amendments.a4.adopted_utc` in ops/dashboard.json. The confirmatory pipeline
+(spec builder + summary) must: probe target resolvability BEFORE reading any
+class; exclude AND count parse-failed swap calls; gate its population on the
+recorded stamp; and refuse the test below 15 resolvable pairs per class.

(plus, when the H-S1 spec builder is written, order it: (1) resolvability probe on the clinical target only, (2) taxonomy classification, (3) swap calls at layers 19/21 with no steerStrength — do not reuse the pilot spec's precomputed classes)
```
Verifier correction: Amendment 4 (signed 2026-07-17, in force) registers a confirmatory H-S1 procedure; clinical-target resolvability screen BEFORE class assignment with excluded counts reported, parse failures excluded and counted, 15-per-class floor, one-sided exact test, post-A4 batch gate; while pinning 'scripts/jlens_steer.py at the adoption commit' as the analysis code. That pinned code cannot execute the registered procedure: it reads class pre-assigned from the spec (lines 131-133) before any endpoint call, detects unresolvability only mid-run (lines 160-169), and its unresolvable check also fires on the swap arm whose steerTokens[0] is the patient-side winner (line 54), silently excluding pairs whose clinical target resolves; an exclusion A4 does not register. The only class-split summary (export_jlens_depth.py steering_split, lines 203-246) counts parse-failed swap calls in the denominator as not-restored instead of excluding-and-counting them, and no min-n gate, exact test, or post-A4 filter exists anywhere in scripts/ (grep: 0 hits). The population anchor is doubly weak: the adoption commit SHA is recorded nowhere (amendment, ops/dashboard.json, divergence log), and the audit HEAD 9696df4 is a shallow git boundary, so the anchor cannot be derived from local history at all. No confirmatory number is published (the site steering block is labeled EXPLORATORY and defers to A4), so this is a medium prereg-consistency gap; the registered analysis-code pointer and the registered design contradict each other; not a wrong published value.

Found by: p-amendments. Verified: CONFIRMED.

#### F2-M10 · `engine:scripts/patch_aggregate.py:95` · prereg-mismatch

The pinned patch-profile code's per-pair best layer includes the trivial output layer and breaks recovery ties toward DEEPER layers, both contrary to A2's H-D2 endpoint wording ('layer of maximum recovery (excluding the trivial output layer)'), in the direction that favors the registered hypothesis.

Evidence:
```
Registered (prereg_amendment2_depth.md, H-D2): "the layer of maximum recovery (excluding the trivial output layer) lies in the deep half (layer >= 13) more often than chance. Test: exact binomial vs 0.5, one-sided, alpha 0.05, minimum n = 12 pairs." and Measurement rules: "Patch profile: per-layer max normalized recovery (scripts/patch_aggregate.py at approval commit)." Code: `best = max(((v, layer, col) for layer, row in enumerate(grid) for col, v in enumerate(row) if v is not None))` (lines 95-96) — (a) no layer is excluded, so the output layer can win, and (b) Python tuple max resolves equal recoveries by the LARGER layer index, an undocumented tie rule that biases per_pair.best.layer toward the deep half H-D2 tests for. per_pair.best is published in data/patch_profile.json (site copy consumed by the depth figures) and is the natural input if H-D2 is computed from the pinned code. No H-D2 test has been published yet, so no published number is currently wrong.
```
Proposed fix:
```diff
--- a/scripts/patch_aggregate.py
+++ b/scripts/patch_aggregate.py
@@ -92,9 +92,14 @@
         for layer, v in enumerate(pl):
             if v is not None:
                 layer_lists.setdefault(layer, []).append(v)
-        best = max(((v, layer, col) for layer, row in enumerate(grid)
-                    for col, v in enumerate(row) if v is not None))
+        # A2 H-D2: exclude the trivial output layer; ties resolve to the
+        # SHALLOWEST layer (conservative against the deep-half hypothesis).
+        n_layers = len(grid)
+        cells = [(v, -layer, col) for layer, row in enumerate(grid)
+                 if layer < n_layers - 1
+                 for col, v in enumerate(row) if v is not None]
+        v_, neg_layer, col_ = max(cells)
+        best = (v_, -neg_layer, col_)
```
Verifier correction: The pinned patch-profile code's per-pair best layer (scripts/patch_aggregate.py:95-96 at HEAD 9696df4) includes the trivial output layer (layer 25, where resid_post patching at the final position trivially reproduces the clean logits, recovery = 1.0) and breaks recovery ties toward deeper layers, both contrary to A2 H-D2's registered wording ("layer of maximum recovery (excluding the trivial output layer)", docs/prereg_amendment2_depth.md:43-44) and both in the hypothesis-favoring direction. The output-layer inclusion is already material in published data: 3 of 9 pairs in data/patch_profile.json (indices 1, 9, 10) have best.layer = 25 with recovery exactly 1.0, each strictly above every non-output layer; outright wins, not ties; the deep tie-break itself has not yet fired on any landed grid (all max winners unique) and is latent drift risk only. Correction to the filed evidence: patch_profile.json's site copy is consumed by no frontend page; the depth figure (methods.html) reads data/jlens_depth.json, and its own best-layer JS (methods.html:605, `if(l<L-1&&p>...)best=l`) already excludes the final layer with a shallow tie-break, underscoring the engine/prereg divergence. No H-D2 test is implemented or published yet, so no published number is currently wrong; severity medium stands. The proposed fix is directionally right; it should also guard the case where a pair's only non-null cells lie in the excluded last row (max() over an empty sequence) and note it assumes full 0..n-1 layer grids (true for all landed runs).

Found by: p-amendments. Verified: CONFIRMED.

#### F2-M11 · `engine:scripts/tierb_split.py:52` · prereg-mismatch

Two irreconcilable definitions of 'Tier B batch' coexist: the code's stamp rule (any pairs_<STAMP> batch at/after tierb.start_utc, tierb_split.py:48-52) counts 3 landed batches the ops/dashboard.json tierb.batches registry omits; pairs_20260713T031252Z and pairs_20260713T135755Z (claude-sonnet-5-generated, though the registration fixes claude-haiku-4-5 as the Tier B generator) and pairs_20260715T132350Z (haiku, 100 accepted); giving three different public/ops Tier B counts (dashboard accepted_pairs=700; stamp-rule recount 807 pairs / 80 holdout memberships vs 70 in registry batches; published timeline.json totals.tierb_accepted=614) and pulling the sonnet batches' rows into the stamp-keyed split and the pairs_*-scoped confirmatory populations.

Evidence:
```
Code: `return bool(m) and m.group(1) >= start_stamp` (tierb_split.py:52). ops/dashboard.json (updated_utc 2026-07-16T23:06:30Z) tierb.batches lists 11 files summing accepted=700, last stamp 20260714T135150Z; data/simulated/ holds pairs_20260713T031252Z.report.json (model claude-sonnet-5, accepted 2), pairs_20260713T135755Z.report.json (claude-sonnet-5, accepted 5), pairs_20260715T132350Z.report.json (claude-haiku-4-5, accepted 100); docs/preregistration_tierB.md:26 registers '`claude-haiku-4-5` authors all Tier B pairs'; recount: 807 pairs / 80 acceptance-hash holdout across stamp-rule batches vs 700 / 70 across registry batches; patientwords/data/timeline.json totals.tierb_accepted = 614. The engine row file already carries explore flags for the two sonnet batches (28 rows), i.e. the split treats them as Tier B while the registry and generator registration do not.
```
Proposed fix:
```diff
Decide and record one canonical membership rule. Minimal proposal: (a) backfill ops/dashboard.json tierb.batches with the three missing sidecars via scripts/ledger_update.py so registry and stamp rule agree; (b) add a divergence-log row: 'sonnet-5-authored pairs batches landed inside the Tier B stamp window; treated as Tier B for SEALING (stamp rule, conservative) but excluded from the haiku-generator confirmatory pool / flagged by generator covariate per the registration'; (c) add a one-line comment above tierb_split.py:48 naming the stamp rule as canonical for sealing:
--- a/scripts/tierb_split.py
+++ b/scripts/tierb_split.py
@@ -47,6 +47,9 @@
 
 def is_tierb_batch(batch_name, start_stamp):
+    # Canonical SEALING rule: any pairs_<STAMP> batch in the Tier B window is
+    # split-stamped, even if ops/dashboard.json tierb.batches lags behind
+    # (registry is accounting; this rule is the seal).
     if not start_stamp:
         return False
```
Verifier correction: Finding confirmed with three refinements. (a) The three omitted batches are not symmetric: pairs_20260715T132350Z (haiku, 100 accepted, 10 holdout memberships) is operationally acknowledged as Tier B; ops/dashboard.json queued_next[1].note calls it "batch-12"; so its absence from tierb.batches/accepted_pairs is registry accounting lag, not a definitional dispute; the genuine definitional conflict with prereg line 26 is confined to the two claude-sonnet-5 batches (7 accepted pairs, 28 rows, 0 holdout). (b) The published 614 decomposes exactly: 600 (registry batches with stamps <= 20260713T050939Z) + 7 (two sonnet batch sidecars) + 7 (orphan sidecar pairs_20260713T050937Z.report.json, model claude-sonnet-5, accepted 7, which has NO corresponding batch .json yet is counted by study_timeline.py:104-105 because batch_entries reads sidecars); i.e., 614 vs 700 is part staleness (timeline generated 2026-07-14T13:42:38Z, before batches 11-12 landed) and part definitional (+14 sonnet-authored pairs that the registry excludes). The finder's recount of 807 (from batch files) and the timeline's stamp-rule population (from sidecars, includes the orphan) are themselves two subtly different stamp-rule populations; a fourth count, 814, would result from a fresh timeline run. (c) The mismatch is undisclosed: docs/prereg_divergence_log.md has no entry, and docs/findings_synthesis_DRAFT_20260713.md:176-180 claims the sonnet sets are "excluded from Tier B counts by construction", which the stamp rule falsifies. Proposed fix is sound as a minimum but should also cover the orphan sidecar (timeline counts sidecar-only batches) and record whether sonnet-authored pairs_* rows are excluded from the pairs_*-scoped interim population or flagged by the registered generator covariate. read_map: [(data/simulated/pairs_*.json + *.report.json, scripts/tierb_split.py + scripts/study_timeline.py, pairs[].top_prompt / accepted / model / stamp), (ops/dashboard.json, tierb_split.tierb_start_stamp + study_timeline + ledger consumers, tierb.start_utc / tierb.batches[].{file,accepted} / tierb.accepted_pairs / queued_next[].note / endpoint_protocol), (urgency_shift.json rows, paired_stats_rigor.py load_rows/dedupe_by_phrase + convergence_tracker.py, rows[].{batch,tierb_split,clinical_prompt(hashed only)} / summary.tierb_holdout_rows_excluded), (data/timeline.json + patientwords/data/timeline.json, frontend timeline strip, totals.tierb_accepted / batches[].{batch,accepted,tierb}), (docs/preregistration_tierB.md:26 + docs/prereg_divergence_log.md + docs/findings_synthesis_DRAFT_20260713.md:176-180, audit, registered generator rule and disclosure status)]

Found by: p-holdout. Verified: CONFIRMED.

#### F2-M12 · `engine:scripts/translation_scale.py:113` · other

Latent double-counting in both joins: the three txcorpus corpora share an identical 352-phrase (source_batch, source_index) set, and neither lens_recovery() nor analyze() dedups by source key across corpora; the current zero-duplicate state is an accident of which summary parts have landed.

Evidence:
```
Recomputed overlap of (generation.source_batch, generation.source_index) sets: txcorpus_priority_20260714T224455Z vs txcorpus_priority2_20260714T224455Z = 352/352 identical; both fully contained in txcorpus_20260714T224455Z (1031 rows). lens_recovery loops every corpus and appends (lines 107-113) with no seen-set; analyze does the same per model (lines 141-163). Today: tx lens readouts exist for priority (25 rows, all dropped for missing src lens) and priority2 (75 rows, all joined) -> verified 0 duplicated phrases in the 75 joined; behavioral runs happen to cover disjoint (corpus, model) cells (gemma-2-2b only on priority, gemma-3-4b-it/qwen only on the big corpus). Any future landing of the pending priority jlens parts (part_11+ ranges) or a behavioral run of priority2/big-corpus under gemma-2-2b would count the same phrase twice in n_paired / patient_never_formed / per_model.n.
```
Proposed fix:
```diff
--- a/scripts/translation_scale.py
+++ b/scripts/translation_scale.py
@@ def lens_recovery(...):
     joined = []
+    seen: set = set()
     for corpus_path in sorted(simulated_dir.glob("txcorpus_*.json")):
@@
             if tx is None or src is None:
                 continue
+            skey = (gen.get("source_batch"), gen.get("source_index"))
+            if skey in seen:
+                continue
+            seen.add(skey)
             joined.append({...})
@@ def analyze(...):  # symmetric guard, keyed (model, source_batch, source_index)
+                skey = (model, src_key_base[0], src_key_base[1])
+                if skey in seen_analyze:
+                    continue
+                seen_analyze.add(skey)
                 per_model.setdefault(model, []).append({
```
Verifier correction: Latent double-counting in both joins of scripts/translation_scale.py (engine HEAD 9696df4): the two priority txcorpus corpora are byte-identical 352-row multisets of (source phrase, translation) pairs; priority2 is a reordering of priority created 2026-07-15 to front-load lens-covered sources; and all 352 rows also appear verbatim inside the 1031-row big corpus. lens_recovery() (lines 102-113) and analyze() (lines 141-163) iterate every txcorpus_*.json with no dedup by (source_batch, source_index) (or (model, source_batch, source_index) in analyze), so the same phrase joins once per corpus whose trace parts have landed. Today there are provably 0 duplicates (75 lens joins, 476 behavioral joins recomputed), but only by accident of landing state: priority's 25 landed tx-lens rows all lack src-lens profiles, and behavioral runs occupy disjoint (corpus, model) cells (gemma-2-2b only on priority idx 1-49; gemma-3-4b-it/qwen3-1.7b only on big-corpus idx 1-700). Any of the queued/plausible next landings; priority2 jlens chunk 4+ (queued per ops/dashboard.json), pairs_ jlens chunks covering priority's 25 sources, or a gemma-2-2b logits run on the big corpus; would silently count the same phrase twice in n_paired, patient_never_formed, and per_model[*].n/mean_recovery, which flow to the published (exploratory-labeled) patientwords/data/translation_scale.json rendered by translation/index.html. Minor corrections to the original: (a) the three corpora do not "share an identical 352-phrase set"; big is a 1031-key strict superset containing the identical priority/priority2 set; (b) pending priority jlens ranges would be part_26+ (jlens chunks are 25 rows), not part_11+; (c) the duplicates would be exact identity duplicates (same translation text), making first-wins dedup by source key lossless. Severity medium stands; the proposed seen-set fix in both functions is the correct minimal change.

Found by: r-translation. Verified: CONFIRMED.

#### F2-M13 · `engine:scripts/translation_scale.py:149` · other

analyze() silently drops translated measurements with no same-model source row (up to 56% per model), so per-model n/means cover different, batch-structured phrase populations with no accounting anywhere in the artifact.

Evidence:
```
Code at lines 148-149: `if not tx or not src:` / `continue` (and lines 152-155 drop rows with any missing probability). Instrumented recount against HEAD trace_out: gemma-3-4b-it 350 measured translated rows -> 154 joined (196 dropped, all from source batches pairs_20260706T172135Z/175614Z/210703Z, pairs_20260707T023656Z/023704Z/023706Z/025842Z which have no gemma-3-4b-it trace dir); qwen3-1.7b 350 -> 290 (60 dropped, all pairs_20260707T221438Z); gemma-2-2b 48 -> 32 (5 src patient-probability None, 11 tx translated-probability None). Published per_model.n values (32/154/290) are joined counts only; the drops are deterministic by source-batch coverage, so each model's mean_recovery is computed over a different, non-random phrase subset while the site table renders them as directly comparable rows. Reproduction: run translation_scale.py as in contract, then re-join with drop counters (same globs, same keys).
```
Proposed fix:
```diff
--- a/scripts/translation_scale.py
+++ b/scripts/translation_scale.py
@@ def analyze(trace_root: Path, simulated_dir: Path) -> dict:
     per_model: dict[str, list[dict]] = {}
+    unjoined: dict[str, int] = {}
     for corpus_path in corpora:
@@
                 tx = tx_results.get((cstem, model, i))
                 src = src_results.get((src_key_base[0], model, src_key_base[1]))
                 if not tx or not src:
+                    unjoined[model] = unjoined.get(model, 0) + 1
                     continue
@@
                 if p_tr is None or p_pat is None or p_cl is None:
+                    unjoined[model] = unjoined.get(model, 0) + 1
                     continue
@@ def analyze(...):  # in the summary loop
         summary[model] = {
             "n": len(rows),
+            "n_unjoined": unjoined.get(model, 0),
```
Verifier correction: One evidence detail misstated (does not change the finding): the gemma-2-2b 48->32 drop decomposition is 16 rows = 5 with only source patient-probability None, 4 with only translated-probability None, and 7 with BOTH None; the finder's '5 src None, 11 tx None' partition silently assigns the 7 overlap rows to tx; totals (16) and joined count (32) match. Also the finding understates the frontend impact: patientwords/translation/index.html lines 332-337 render the explainer 'The same LLM translation, applied to every measured phrase (N so far) and scored by next-word probability on each model' with N = max per-model n (290), which affirmatively asserts each-model coverage of a common phrase set that does not exist; the proposed n_unjoined field should also drive a per-row coverage disclosure (or corrected wording) on that page.

Found by: r-translation. Verified: CONFIRMED.

#### F2-M14 · `engine:scripts/translation_scale.py:176` · unguarded-claim

mean_gap_closed is dominated by the [-2,2] clip: for gemma-3-4b-it the published clipped mean is +0.3513 while the unclipped mean is -0.5185 (sign flip), with 15/54 headroom rows saturating the clip; the disclosure note says 'clipped' but nothing signals that the sign of the published value depends on the clip.

Evidence:
```
Code lines 175-177: `"mean_gap_closed": (round(statistics.fmean([min(2.0, max(-2.0, g["recovery"] / g["gap"])) for g in gaps]), 4) if gaps else None)`. Recomputed per-pair ratios from the same joined rows: gemma-3-4b-it raw ratio range -56.594..13.172, 9 clipped high / 6 clipped low of 54, mean unclipped -0.5185 vs published 0.3513; qwen3-1.7b range -10.715..11.066, 17/142 clipped, unclipped 0.4736 vs published 0.4371; gemma-2-2b 2/23 clipped, unclipped 0.5021 vs published 0.5607. Denominator audit: gap floor of 0.01 bounds |ratio|<=200 pre-clip (no div-by-zero); negative and <=1pp gaps excluded per the documented rule (gemma-2-2b 7 neg + 2 tiny, gemma-3-4b-it 64+36, qwen3-1.7b 104+44 excluded).
```
Proposed fix:
```diff
--- a/scripts/translation_scale.py
+++ b/scripts/translation_scale.py
@@ summary[model] = {
             "mean_gap_closed": (round(statistics.fmean(
                 [min(2.0, max(-2.0, g["recovery"] / g["gap"])) for g in gaps]), 4)
                 if gaps else None),
+            "median_gap_closed": (round(statistics.median(
+                [g["recovery"] / g["gap"] for g in gaps]), 4) if gaps else None),
+            "n_gap_clip_saturated": sum(
+                1 for g in gaps if abs(g["recovery"] / g["gap"]) > 2.0),
```
Verifier correction: Medium, category unguarded-claim (with the caveat that today it is a shipped-statistic gap, not an on-page claim): scripts/translation_scale.py:175-177 (engine 9696df4) writes per_model.mean_gap_closed after clipping each per-pair recovery/gap ratio to [-2,2]; for gemma-3-4b-it the clip determines the sign of the shipped value (clipped mean +0.3513 in ops/translation_scale.json:25 and site data/translation_scale.json:25 vs unclipped mean -0.5185; 15 of 54 headroom rows saturate the clip, raw ratios spanning -56.594..13.172; qwen3-1.7b 17/142 clipped, 0.4371 vs 0.4736 unclipped; gemma-2-2b 2/23, 0.5607 vs 0.5021). The embedded "_" note discloses "clipped to [-2, 2]" but not that the headline model's sign is clip-determined. The field currently has no claims-manifest guard (data/claims_manifest.json contains no translation_scale.json-sourced claim) and no runtime fill (translation/index.html:308-353 never renders it), but both data-file copies are public and the queued Audit-1 medium fix proposes rendering this exact field on translation/index.html, at which point the missing disclosure becomes load-bearing. Fix as proposed (add median_gap_closed; unclipped median is 0.4210 for gemma-3-4b-it, robust to the tails; and an n_gap_clip_saturated count next to the mean), plus extend the "_" note to state that the mean is clip-sensitive; note the finder's stated pre-clip bound of |ratio|<=200 should read <100 (recovery is bounded by 1, gap floor 0.01).

Found by: r-translation. Verified: CONFIRMED.

#### F2-M15 · `engine:scripts/urgency_shift.py:242` · doc-drift

The divergence-log entry claiming interim site statistics were restricted to observational pairs_* batches is broader than the code: the published urgency_shift.json summary (per_model sign tests, per_model_deduped homepage figure) still pools 328 rows from 27 non-observational stems (steered boostgrid runs, drift sentinels, imports, re-traces, curated sets).

Evidence:
```
Logged (prereg_divergence_log.md, 2026-07-14 row): "interim (site) statistics restricted to observational `pairs_*` generation batches; steered, screened, imported, and re-traced rows moved to a labeled sensitivity analysis" — implemented only in paired_stats_rigor.py (_OBS_RE, line 59/337) for model_stats.json. The collector's published summary has no such filter: per-model loop `for model in sorted({r["model"] for r in arows})` (line 242) and per_model_deduped (lines 266-291) run over every batch stem; recount at HEAD: 328 rows across 27 non-observational stems (incl. 'boostgrid_lowrank', 'boostgrid_s20' steered runs, 'drift_sentinel_2026071x', 'ci_pairs_2panel', 'featured_sim85') are inside the published data/urgency_shift.json summary population, and summary.per_model_deduped is rendered on index.html:657, start-here/index.html:543 and simulated-scenarios/index.html:646. The log entry as written implies these figures were rescoped; they were not — the logged deviation is vaguer than the code.
```
Proposed fix:
```diff
--- a/scripts/urgency_shift.py
+++ b/scripts/urgency_shift.py
@@ -396,10 +396,14 @@
     site_payload = {
         "vocabulary_status": vocab_meta.get("status", "draft pending domain review"),
         "tiers": vocab_meta.get("tiers"),
         "tier_examples": tier_examples,
+        "population_note": ("summary pools every landed 2panel row (steered, "
+                            "sentinel, imported and re-traced stems included); "
+                            "claim-grade observational-only statistics live in "
+                            "data/model_stats.json"),
         "summary": {k: summary[k] for k in ("measurements", "flips", "flip_classes",

(alternative, stronger fix: compute a parallel observational-only per_model_deduped for the site copy; either way, add a matching clarification to the 2026-07-14 divergence-log row so the logged disposition matches what the code does)
```
Verifier correction: The 2026-07-14 divergence-log row ("interim (site) statistics restricted to observational `pairs_*` generation batches; steered, screened, imported, and re-traced rows moved to a labeled sensitivity analysis") is broader than the code: the restriction exists only in paired_stats_rigor.py (_OBS_RE, lines 59/337) for data/model_stats.json. The collector urgency_shift.py applies no batch-stem filter; its published summary (per_model sign tests, line 242; per_model_deduped, lines 266–291; copied to the site at lines 396–405) pools the full exploration split. Recomputed at engine HEAD 9696df4, that summary population includes 328 rows from 27 non-observational stems (steered boostgrid runs, drift sentinels, imports, re-traces, repeatability and curated sets); the deployed data/urgency_shift.json is a slightly stale copy of the same unfiltered computation (summary.measurements 4542 vs 4653 at HEAD) and its trimmed public rows contain 286 rows over the same 27 stems. summary.per_model_deduped from this pooled population is rendered on index.html:657, start-here/index.html:543, and simulated-scenarios/index.html:646 with no population disclosure. Fix: add a population_note to the site payload (and/or an observational-only parallel figure) and amend the 2026-07-14 log row to say the restriction applies to data/model_stats.json claim-grade statistics only.

Found by: p-amendments. Verified: CONFIRMED.

#### F2-M16 · `engine:scripts/urgency_shift.py:338` · recompute-divergence

Quantification (commissioned; references Audit 1's queued tier-0/null falsy-coercion finding, report ID F-M29 at docs/audit1_report.md:1030; the lane brief's 'F-M04'; NOT a re-file): the published summary.mitigation.restored_top_tier = 56 is confirmed wrong; the null-safe value is 54 of 72 tier-comparable rows (n=91).

Evidence:
```
Published frontend data/urgency_shift.json:357 `"restored_top_tier": 56` vs recomputed null-safe value 54. Code at urgency_shift.py:338-339: `sum(1 for r in translated if (r.get("tier_top_translated") or -1) >= (r.get("tier_top_clinical") or 0))`. Exact decomposition over the 91 publish-time explore-split translated rows: 11 rows OVERCOUNTED where tier_top_clinical is None coerced to 0 (translated tiers {1: 5 rows, 2: 5 rows, 3: 1 row}); 9 rows UNDERCOUNTED where tier_top_translated == 0 coerced to -1 against tier_top_clinical == 0 (-1 >= 0 False though 0 >= 0 True); net 56 - 11 + 9 = 54; only 72 of 91 rows have both tiers non-null. Reproduction: cd /home/user/audit-wb/patientwords-engine && python3 scripts/urgency_shift.py --tiers data/urgency_tiers.draft.json --frontend /home/user/audit-wb/patientwords --out <abs sandbox path>, then over rows with urgency_recovery != null, tierb_split != 'holdout', and (batch,model) not in the 4 post-publish legs, compare the falsy expression against the None-guarded comparison.
```
Proposed fix:
```diff
--- a/scripts/urgency_shift.py
+++ b/scripts/urgency_shift.py
@@ -336,8 +336,10 @@
         "mean_urgency_recovery": round(sum(r["urgency_recovery"] for r in translated)
                                        / len(translated), 4),
-        "restored_top_tier": sum(1 for r in translated
-                                 if (r.get("tier_top_translated") or -1) >= (r.get("tier_top_clinical") or 0)),
+        "restored_top_tier": sum(
+            1 for r in translated
+            if r.get("tier_top_translated") is not None
+            and r.get("tier_top_clinical") is not None
+            and r["tier_top_translated"] >= r["tier_top_clinical"]),
+        "restored_top_tier_comparable_n": sum(
+            1 for r in translated
+            if r.get("tier_top_translated") is not None
+            and r.get("tier_top_clinical") is not None),
     }
(identical to the Audit 1 F-M29 diff plus its verifier's suggested comparable-rows denominator; on current data this publishes 54 of 72 instead of 56 of implied 91)
```
Verifier correction: As stated, with one detail corrected: the reproduction's exclusion of "(batch,model) not in the 4 post-publish legs" is a no-op for the mitigation set; at the audited HEADs a fresh recompute's explore-split translated set is identical to the publish-time set (all 91 rows' legs appear in the published rows; fresh and publish-time values coincide: falsy 56, null-safe 54, comparable 72). All headline numbers stand: published summary.mitigation.restored_top_tier = 56 (data/urgency_shift.json:357) is wrong under None-safe comparison; correct value is 54 of 72 tier-comparable rows within the n=91 explore-split translated set (overcount 11 where tier_top_clinical is None, translated tiers {1:5, 2:5, 3:1}; undercount 9 where both tiers are 0).

Found by: r-urgency. Verified: CONFIRMED.

#### F2-M17 · `site:data/jlens_depth.json:1574` · requires-unseal

The published value restored=11 of n=12 cannot be fully audit-verified without computing steering outcomes over the 3 holdout-flagged hijack pairs: only the 9 exploration-split pairs' contribution (8 restored, 1 failed) is verifiable under the seal, and the residual delta between 8/9 and the published 11/12 is holdout-derived by construction.

Evidence:
```
Published: '"restored": 11' / '"n": 12' (patientwords/data/jlens_depth.json:1568-1575), rendered at technical/index.html:842. Membership determination (allowed): 3 of the 12 counted hijack pairs hash to holdout under sha1(clinical_prompt)%10==0 — (pairs_20260711T051145Z, 49), (pairs_20260711T131752Z, 19), (pairs_20260711T131752Z, 38). The seal forbids aggregating outcomes over those rows, so the published aggregate's exact value is unverifiable as published; the same applies to Amendment 4's motivation count '21/24 layer-cases' (docs/prereg_amendment4_steering.md:25), whose denominator includes the same 3 pairs. Reproduction of the verifiable part: the explore-split command in the companion high finding → hijack [9,8].
```
Proposed fix:
```
No unsealing needed if the companion high finding's fix lands: republish jlens_depth.json exploration-only (suppressed {n:9, restored:8}), and rewrite Amendment 4's motivation counts as exploration-split values with a dated divergence-log entry (docs/prereg_divergence_log.md) disclosing that the 2026-07-16 published pilot block and the amendment's pilot counts had included 3 holdout-flagged pairs. If the owner instead wants the 11/12 verified as published, that requires a logged one-time unseal of those 3 pairs' steering outcomes — not recommended before the Amendment 3 endpoint run.
```
Verifier correction: Minor precisions, none affecting substance: (a) the published JSON labels the class "suppressed", not "hijack"; the exporter maps hijack->suppressed (export_jlens_depth.py:227); the finder's engine-side terminology is accurate but the fix should name the published key. (b) Exact line anchors: "n": 12 is jlens_depth.json:1573 and "restored": 11 is :1574 (finder's 1568-1575 range and line 1574 are correct). (c) Strengthening evidence the finder omitted: the payload's own "scope" field claims "Amendment 1 exploration split only" (export_jlens_depth.py:264-265), which the steering block's inclusion of 3 holdout-flagged pairs contradicts; this makes the exploration-only republish fix (suppressed {n:9, restored:8}) also a consistency fix for the payload's self-description. (d) One of the 12 pairs, (urgency_downgrades_20260707T1, 5), is from a non-Tier-B batch that carries no split flag under tierb_split.py (Tier A-era set); it hashes explore regardless, so the 3-of-12 holdout count and the 9/8 explore recompute stand. (e) Amendment 4's 24 layer-cases are the dedupe of 48 raw hijack swap calls (each pair measured in both pilot runs at L19 and L21); the finder's claim that its denominator includes the same 3 pairs is confirmed at 6 of 24 layer-cases.

Found by: r-steering. Verified: CONFIRMED.

#### F2-M18 · `site:data/model_stats.json:42` · recompute-divergence

The published claim-grade bundle, including the confirmatory gemma-2-2b -3.36pp headline, does not reproduce from the engine at the audited HEADs: it is a 2026-07-14 snapshot while observational pairs_* trace data landed through 2026-07-16, and every per-model number diverges on recompute (same code, same seed 7 / boot 5000).

Evidence:
```
Published (data/model_stats.json, last committed b0f8ef7 2026-07-14): gemma-2-2b penalty mean -0.0336, ci95 [-0.0445, -0.0228], n_phrases 650, n_rows 769, flips 297 (48 down / 13 up), sign_test p_raw 7.665168380445453e-06, p_bh 1.0220224507260603e-05; below_floor []. Recomputed at engine HEAD 9696df4: mean -0.0308, ci95 [-0.0408, -0.0209], n_phrases 843, n_rows 1018, flips 408 (62 down / 19 up), p_raw 1.7730682926908968e-06, p_bh 2.626504557448848e-06. All other models diverge too: qwen3-4b -0.049 (n=677) -> -0.0458 (n=767); qwen3-1.7b -0.0487 (677) -> -0.0497 (855); gemma-3-4b-it -0.046 (677) -> -0.0478 (855); llama-3.2-3b -0.0503 (122) -> -0.0451 (204); medgemma-4b-it -0.0339 (119) -> -0.0393 (204); gemma-2-2b-it -0.0623 (122) -> -0.0544 (165); olmo-2-1b n 122 -> 204. Today's two registry additions are missing entirely: recomputed below_floor = [{apertus-8b-meditronfo, n_phrases 3}, {meditron3-8b, n_phrases 3}] vs published []; exploratory BH family is now 6 tests, published says 4. sensitivity_all_rows gemma-2-2b: published 811 phrases / -0.0348 / 55 down / 13 up vs recomputed 1048 / -0.0325 / 68 / 19. Count-derived stats verified exact from published counts (Clopper-Pearson, two-sided sign test, BH within both registration families all reproduce bit-exact), and seed/boot fields (7/5000) match code defaults — so the divergence is data vintage, not code. Split provenance of -3.36pp determined: exploration split (holdout phrase-key excluded by load_rows; 74 holdout phrases / 341 rows counted at HEAD), observational pairs_* only — not a sealed-holdout statistic. Reproduction: mkdir SB && ln -s <engine>/{data,trace_out,ops} SB/ && cd SB && python3 <engine>/scripts/urgency_shift.py --frontend <frontend> --out urgency_shift.json && python3 <engine>/scripts/paired_stats_rigor.py --rows urgency_shift.json --seed 7 --boot 5000 --site '' --out rigor.json; diff rigor.json fields against data/model_stats.json.
```
Proposed fix:
```
Operational, not a code diff (the code reproduces its own outputs): from the engine root, re-run the publish chain in one session and commit both repos together —
  python3 scripts/urgency_shift.py --out urgency_shift.json --publish ../patientwords
  python3 scripts/paired_stats_rigor.py --rows urgency_shift.json --out paired_stats_rigor.json --site ../patientwords
This refreshes data/model_stats.json to the HEAD data (gemma-2-2b -3.08pp [-4.08, -2.09] on 843 phrases), populates below_floor with the two new probe models, and moves the exploratory BH family to 6 tests. Pair with the anchor stamp in the sibling finding so a stale copy is detectable next time.
```
Severity: Verifier severity correction (high->medium): not a computation error; the -3.36pp headline reproduces bit-exact from the published counts. The defect is staleness (2026-07-14 snapshot vs data landed through 07-16) plus no embedded timestamp/input-digest, so the bundle is irreproducible by default.

Verifier correction: {"severity":"medium","category":"recompute-divergence","file":"patientwords/data/model_stats.json","line":42,"summary":"The published claim-grade bundle (incl. the confirmatory gemma-2-2b -3.36pp headline at line 42) is a stale 2026-07-14 snapshot: observational pairs_* data landed through 2026-07-16 (pairs_20260714T135150Z all-model traces, pairs_20260715T132350Z, two 3-pair probe models), and at the audited HEADs every per-model number diverges on recompute with identical code/seed 7/boot 5000. Not a computation error; count-derived statistics reproduce bit-exact from the published counts; but the staleness is unguarded and now cross-contradicts the same site: the 2026-07-16 republish (frontend 244c698) refreshed data/urgency_shift.json (gemma-2-2b deduped 995 phrases / 67 downgrades / mean -0.0317) while model_stats.json still shows 650 / 48 / -0.0336, below_floor [] omits the two measured probe models the file contract promises to list, the exploratory BH family will move from 4 to 6 tests, and technical/index.html:455's hard-coded 'four post-registration exploratory' prose will also be wrong on regeneration.","verified_numbers":"published gemma-2-2b -0.0336 [-0.0445,-0.0228] n_phrases 650 n_rows 769 flips 297 (48/13) p_raw 7.665168380445453e-06 p_bh 1.0220224507260603e-05, below_floor []; recomputed at 9696df4: -0.0308 [-0.0408,-0.0209] 843/1018 flips 408 (62/19) p_raw 1.7730682926908968e-06 p_bh 2.626504557448848e-06, below_floor [apertus-8b-meditronfo n=3, meditron3-8b n=3], exploratory n_tests 6, sensitivity gemma-2-2b 1048/-0.0325/68/19; holdout exclusion 341 rows / 74 phrases (exploration-split provenance, phrase-keyed via paired_stats_rigor.py:84-94); all independently reproduced.","proposed_fix":"Operational republish, as the finder proposed: from the engine root run 'python3 scripts/urgency_shift.py --out urgency_shift.json --publish ../patientwords' then 'python3 scripts/paired_stats_rigor.py --rows urgency_shift.json --out paired_stats_rigor.json --site ../patientwords', and commit both repos in the same cycle so model_stats.json and urgency_shift.json share a vintage; also update the technical/index.html:455 registration prose (or make it render from registration.post_registration_exploratory.length) and pair with the sibling anchor-stamp finding so a stale copy is mechanically detectable. If it emerges that the 07-16 cycle intentionally defers model_stats regeneration, document that cadence in docs/routine_standing_prompt.md instead.","read_map":[["patientwords/data/model_stats.json","patientwords/technical/index.html Part 4 (fetch at line 917, methods list lines 449-459)","per_model.{penalty.mean,ci95,n_phrases},flips,sign_test.{p_raw,p_bh},registration,benjamini_hochberg.families,below_floor,site_floor_n_phrases,models_meta"],["engine trace_out/*/batch_summary.part_*.json","engine scripts/urgency_shift.py (collector, lines 156-190)","results[].{index,prompts,predictive_spread,language_penalty,continuations},graph_model"],["patientwords/data/simulated_scenarios.json","engine scripts/urgency_shift.py fill-in (lines 193-205) and paired_stats_rigor.py site copy (models_meta, lines 563-568)","scenarios[].models[].{spread_clinical,spread_patient,language_penalty},models_meta"],["sandbox urgency_shift.json rows","engine scripts/paired_stats_rigor.py load_rows/analyze","rows[].{model,batch,clinical_prompt,language_penalty,flipped,flip_class,tierb_split}"],["engine ops/dashboard.json","engine scripts/tierb_split.py stamp_rows","tierb.start_utc"],["patientwords/data/urgency_shift.json (site copy, 07-16)","urgency page / cross-artifact consistency check","summary.per_model_deduped.gemma-2-2b.{n_phrases,downgrades,mean_penalty}"]]}

Found by: r-model-stats. Verified: CONFIRMED.

#### F2-M19 · `site:index.html:323` · unguarded-claim

Display numbers 'scenario 85' and 'scenario 48' are hardcoded across five pages (index.html:323,351; start-here:205,394; wording-differences:195,203,290; share/card.html:43) but come from the payload's positional 'index' field, which renumbers if scenarios are ever trimmed or reordered; exactly what the queued F-M27 orphan-row trim may do.

Evidence:
```
simulated_scenarios.json: scenario (pairs_20260707T171223Z, batch_index 49).index == 85; (same batch, batch_index 12).index == 48. All page links use stable batch paths (index_49.html) but the visible numbers use the global display index.
```
Proposed fix:
```
{"page": "index.html", "snippet": "live measurements, scenario 85", "source": "data/simulated_scenarios.json", "expr": "[next(s['index'] for s in d['scenarios'] if s['batch']=='pairs_20260707T171223Z' and s['batch_index']==49), next(s['index'] for s in d['scenarios'] if s['batch']=='pairs_20260707T171223Z' and s['batch_index']==12)]", "expected": [85, 48]} (mirror with page-appropriate snippets on start-here/index.html 'scenario 48 (panel 2', wording-differences/index.html '(scenario 85)', share/card.html 'scenario 85')
```
Verifier correction: Display numbers 'scenario 85' and 'scenario 48' are hardcoded across four published pages (index.html:323,351; start-here/index.html:205,394; wording-differences/index.html:195,203,290; share/card.html:43; not five; the additional grep hits are in docs/site_text_outline*.md, which are not published pages). They come from the payload's positional 'index' field (assigned by a running display_index counter in export_frontend_simulated.py; payload indices are exactly 1..751), which renumbers if scenarios are ever trimmed or reordered; exactly what the queued F-M27 orphan-row trim may do; while the batch-path trace links (index_49.html) remain stable, so prose and links would silently diverge. No claims_manifest.json entry guards these numbers and no runtime fill exists. Proposed fix (verified to evaluate to [85, 48] under claim_check.py's evaluate sandbox): add one manifest claim per page against data/simulated_scenarios.json, e.g. for index.html snippet 'live measurements, scenario 85' with expr \"[next(s['index'] for s in d['scenarios'] if s['batch']=='pairs_20260707T171223Z' and s['batch_index']==49), next(s['index'] for s in d['scenarios'] if s['batch']=='pairs_20260707T171223Z' and s['batch_index']==12)]\" and expected [85, 48]; mirror with snippets 'scenario 48 (panel 2' (start-here/index.html), '(scenario 85' (wording-differences/index.html), 'scenario 85' (share/card.html).

Found by: c-unguarded. Verified: CONFIRMED.

#### F2-M20 · `site:index.html:368` · unguarded-claim

Homepage Fig. 2 numbers '+11–13% toward the everyday continuation' and 'Register shift Δ: +4–5%' (l.368-369) trace only to the old modes/4quadrant/index.html render (no JSON source, so claim_check cannot guard them), and the click-through page now leads with a different traced item showing different deltas (+13/+10, −10/−13), inviting confusion and silent drift when modes/ is re-exported wholesale.

Evidence:
```
modes/4quadrant/index.html contains 'Variety shift Δ: +13% probability (0.21 → 0.34)', one '+11', 'Register shift Δ: +5% probability (0.21 → 0.26)' and '+4% probability (0.34 → 0.37)' — consistent with the prose today. wording-differences/index.html:209 (the linked page) leads with the 4quadrant2 palpitations deltas instead. claim_check.py:46 json.loads() means an HTML source can never back a manifest entry.
```
Proposed fix:
```
Copy the old-render quadrant deltas into data/provenance.json (e.g. "quadrant_generic": {"variety_deltas": [0.13, 0.11], "register_deltas": [0.05, 0.04]}, sourced from the engine run that produced modes/4quadrant), then add: {"page": "index.html", "snippet": "+11–13% toward the everyday continuation", "source": "data/provenance.json", "expr": "[round(max(d['quadrant_generic']['variety_deltas'])*100), round(min(d['quadrant_generic']['variety_deltas'])*100), round(max(d['quadrant_generic']['register_deltas'])*100), round(min(d['quadrant_generic']['register_deltas'])*100)]", "expected": [13, 11, 5, 4]}
```
Verifier correction: Finding stands as filed, with two precision notes. (a) The exact stat-line text at index.html:369 is "Variety shift Δ: +11% and +13% toward the everyday continuation · Register shift Δ: +4–5%" (the finding's paraphrase "+11–13%" is the line-368 prose; both lines are affected). (b) In the proposed fix, the register_deltas value 0.04 cannot be recomputed from the render's displayed endpoints (0.37 − 0.34 = 0.03; the render label "+4%" comes from unrounded engine probabilities), so the provenance.json entry must be populated from the engine run's unrounded values (the run sidecar/summary that produced modes/4quadrant), not by subtracting the rounded endpoints shown in the render; the proposal's delta-storing shape already handles this correctly, and its expr verifies to [13, 11, 5, 4] under claim_check's evaluate().

Found by: c-unguarded. Verified: CONFIRMED.

#### F2-M21 · `site:methods.html:291` · unguarded-claim

Worked-example 30%/26% (audit-1 known item, still present) is unguarded in four places: methods.html:291 '(30%, against the laxative's 26% under clinical wording)', translation/index.html:220-221 '(30%)... (26%)', :257 '41% after translation (clinical baseline 26%)', :285 caption; the manifest guards 45%/41% on the translation page but never the 30 (patient top) or 26 (clinical baseline), and the index.html 0.45 claim's expr also skips its 0.26.

Evidence:
```
provenance.json translation_cases.grandma_laxative: patient=[token,0.299] -> 30%, clinical=[token,0.263] -> 26% (round(29.9)=30, round(26.3)=26 under claim_check's Python round). Existing exprs check only translated[1] (0.453/0.409).
```
Proposed fix:
```
Add: [{"page": "methods.html", "snippet": "(30%, against the laxative", "source": "data/provenance.json", "expr": "[round(d['translation_cases']['grandma_laxative']['patient'][1]*100), round(d['translation_cases']['grandma_laxative']['clinical'][1]*100)]", "expected": [30, 26]}, {"page": "translation/index.html", "snippet": "(30%); rewritten in clinical terms", "source": "data/provenance.json", "expr": "[round(d['translation_cases']['grandma_laxative']['patient'][1]*100), round(d['translation_cases']['grandma_laxative']['clinical'][1]*100)]", "expected": [30, 26]}, {"page": "translation/index.html", "snippet": "(clinical baseline 26%)", "source": "data/provenance.json", "expr": "round(d['translation_cases']['grandma_laxative']['clinical'][1]*100)", "expected": 26}, {"page": "index.html", "snippet": "(clinical baseline 0.26)", "source": "data/provenance.json", "expr": "round(d['translation_cases']['grandma_laxative']['clinical'][1],2)", "expected": 0.26}]
```
Verifier correction: Finding stands with three sharpenings. (a) Scope split: the methods.html:291 component is a disclosed Audit-1 re-file; engine docs/audit1_report.md:543 and :552-554 already contain the identical manifest entry (snippet "(30%, against the laxative", expr over patient[1]/clinical[1], expected [30,26]) among the 36 queued mediums; the net-new content of this finding is the three translation/index.html spots and index.html's 0.45 expr skipping the adjacent 0.26. The fix for methods.html should be deduplicated against the queued Audit-1 patch rather than added twice (duplicate manifest entries are harmless to claim_check but noise). (b) Provenance precision: translation/index.html:257 and :285 are labeled "July 9 re-trace", and provenance.json carries a retrace_20260709 block with its own patient_top=0.299 and clinical=0.263 (identical to the base values, so the proposed exprs pass either way); the stricter guard for those two spots is expr "[round(d['translation_cases']['grandma_laxative']['retrace_20260709']['patient_top'][1]*100), round(d['translation_cases']['grandma_laxative']['retrace_20260709']['clinical'][1]*100)]", expected [30,26], matching the existing 41% guard which already reads the retrace block. (c) The four proposed manifest entries are otherwise verified correct: all exprs evaluate to expected under claim_check.py's restricted eval (round is in the sandbox builtins), all snippets are present single-line, and claims_manifest.json is consumed only by scripts/claim_check.py and tests/test_claim_check.py, so additive entries break no consumer.

Found by: c-unguarded. Verified: CONFIRMED.

#### F2-M22 · `site:methods.html:518` · unguarded-claim

'The behavioral checks on the other seven models' hardcodes 7 (= 8 per_model minus gemma-2-2b) against nightly-regenerated model_stats.json; two new logits models (meditron3-8b, apertus-8b-meditronfo) registered today will make it 9, and the existing 'run on eight'/'families' guards point at other sentences, not this one.

Evidence:
```
len(model_stats.json per_model) == 8 today (gemma-2-2b, gemma-2-2b-it, gemma-3-4b-it, llama-3.2-3b, medgemma-4b-it, olmo-2-1b, qwen3-1.7b, qwen3-4b). Page: 'The behavioral checks on the other seven models measure next-word probabilities only'.
```
Proposed fix:
```
{"page": "methods.html", "snippet": "the other seven models", "source": "data/model_stats.json", "expr": "len(d['per_model'])-1", "expected": 7}
```
Verifier correction: Finding stands as filed; only arithmetic clarification: with the two new models per_model grows from 8 to 10, so the sentence's correct count becomes nine ("the other nine models"), consistent with the finder's "will make it 9". Proposed manifest entry is valid as written: {"page": "methods.html", "snippet": "the other seven models", "source": "data/model_stats.json", "expr": "len(d['per_model'])-1", "expected": 7}.

Found by: c-unguarded. Verified: CONFIRMED.

#### F2-M23 · `site:simulated-scenarios/index.html:327` · unguarded-claim

'The 25 largest-effect scenarios (prediction flips first, then largest penalty) include a full circuit comparison' hardcodes the exporter's --max-renders cap against the nightly re-exported payload; if the cap changes the prose drifts with no guard.

Evidence:
```
sum(1 for s in scenarios if s.get('html')) == 25 in data/simulated_scenarios.json today; the cap lives in engine export_frontend_simulated.py (--max-renders), not in any committed frontend number.
```
Proposed fix:
```
{"page": "simulated-scenarios/index.html", "snippet": "The 25 largest-effect scenarios", "source": "data/simulated_scenarios.json", "expr": "sum(1 for s in d['scenarios'] if s.get('html'))", "expected": 25}
```
Verifier correction: Finding stands as filed (medium, unguarded-claim). Minor precision: the guard as proposed protects only the count "25"; the ranking clause "prediction flips first, then largest penalty" mirrors exporter sort logic (export_frontend_simulated.py ranking before the line-272 cap) and remains unguardable by claim_check; worth a manifest "_" note in the fix, e.g. adding "_": "guards the render cap only; the flip-first ranking clause tracks export_frontend_simulated.py and needs hand-review if the exporter sort changes".

Found by: c-unguarded. Verified: CONFIRMED.

#### F2-M24 · `site:start-here/index.html:271` · unguarded-claim

Panel-5 caption 'the real traces of the matching acid-reflux pair fire 732 and 787 features and share 465' hardcodes scenario 48's circuit_diff (732 = 465+267 unique_to_a, 787 = 465+322 unique_to_b) from the nightly re-exported payload; a re-trace or graph-parameter change alters these counts silently.

Evidence:
```
simulated_scenarios.json scenario (batch pairs_20260707T171223Z, batch_index 12, index 48): circuit_diff = {"shared_features": 465, "unique_to_a": 267, "unique_to_b": 322}; 465+267=732, 465+322=787.
```
Proposed fix:
```
{"page": "start-here/index.html", "snippet": "fire 732 and 787 features and share 465", "source": "data/simulated_scenarios.json", "expr": "next(s['circuit_diff'] for s in d['scenarios'] if s['batch']=='pairs_20260707T171223Z' and s['batch_index']==12)", "expected": {"shared_features": 465, "unique_to_a": 267, "unique_to_b": 322}}
```
Found by: c-unguarded. Verified: CONFIRMED.

#### F2-M25 · `site:technical/index.html:381` · unguarded-claim

Part 4 registration-split and count prose is unguarded on the nightly source: 'Four models were named in the pre-registration; the other four are later additions' (l.381-382), 'sized for reading all eight at once' (l.393), 'about 120 phrases so far' (l.404), 'merged eight-model correction' (l.454), 'four models pre-registered, four post-registration exploratory' (l.455); the two new logits models make the split 4/6 on their first landed stats.

Evidence:
```
model_stats.json registration = {pre_registered: 4 ids, post_registration_exploratory: 4 ids}; convergence.json final n_phrases for the four post-reg models = 122/122/119/122 (matches 'about 120' today but grows every batch). Existing manifest guards only 'run on eight' and 'four model families' snippets.
```
Proposed fix:
```
Add: [{"page": "technical/index.html", "snippet": "the\n      other four are later additions", "snippet_alt": "other four are later additions", "source": "data/model_stats.json", "expr": "[len(d['registration']['pre_registered']), len(d['registration']['post_registration_exploratory'])]", "expected": [4, 4]}, {"page": "technical/index.html", "snippet": "four models pre-registered, four post-registration exploratory", "source": "data/model_stats.json", "expr": "[len(d['registration']['pre_registered']), len(d['registration']['post_registration_exploratory'])]", "expected": [4, 4]}, {"page": "technical/index.html", "snippet": "all eight at once", "source": "data/model_stats.json", "expr": "len(d['per_model'])", "expected": 8}, {"page": "technical/index.html", "snippet": "merged eight-model correction", "source": "data/model_stats.json", "expr": "len(d['per_model'])", "expected": 8}, {"page": "technical/index.html", "snippet": "read about 120 phrases so far", "source": "data/convergence.json", "expr": "all(110 <= d['models'][m]['points'][-1]['n_phrases'] <= 130 for m in ('gemma-2-2b-it','llama-3.2-3b','medgemma-4b-it','olmo-2-1b'))", "expected": true}]
```
Verifier correction: One nuance overstated: "all eight at once" (l.393) and "merged eight-model correction" (l.454) are not wholly unalarmed; the two existing manifest entries for this page ("run on eight", "four model families") both assert len(d['per_model'])==8 and will FAIL the nightly check the moment the two new models' stats land, so the underlying count is guarded page-wide even though those specific sentences are not tied. The residual risk there is narrower than stated: a maintainer could fix only the "run on eight" sentence plus the manifest expected value and go green while l.393/l.454 stay stale, so adding the two per_model entries is still a reasonable hardening, not a new guard. The genuinely unguarded numbers; no expr anywhere touches them; are (a) the 4/4 registration split (l.381-382 and l.455; model_stats.json d['registration'] is referenced by no manifest entry, and the split becomes 4/6 on the new models' first landed stats) and (b) "about 120 phrases so far" (l.404; data/convergence.json is referenced by no manifest entry; current final n_phrases 122/122/119/122 grow every batch). The proposed fix is sound as written: all five entries' exprs evaluate correctly under claim_check.py's restricted evaluate() against the current site JSONs, and every snippet/snippet_alt matches the page verbatim.

Found by: c-unguarded. Verified: CONFIRMED.

#### F2-M26 · `site:technical/index.html:829` · doc-drift

The Fig 4 router table labels jlens_depth's upstream classes 'suppressed'/'absent' as '(hijack)'/'(capture)', but those classes use the pre-July-14 rule (single-layer formation, no clinical-readable conditioning), so the same page shows two different partitions under one vocabulary.

Evidence:
```
index.html:829: var label={retained:'held to the end',suppressed:'formed, then lost (hijack)',absent:'never formed (capture)'}. Cross-tab of the summaries' own patient_depth_class against jlens_insights.classify() over the same 476 census rows: suppressed -> 31 hijack + 4 capture + 6 unreadable; absent -> 40 capture + 102 unreadable; retained -> 293 held. So Fig 4's 'hijack' bucket (upstream suppressed) is not the headline taxonomy's hijack=31 shown two figures earlier from jlens_insights.json, and Part 2's own prose (index.html:272-276) states the persistence-2 + clinical-readable rules as the adopted counting rules. Repro: python3 -c "import sys,pathlib; sys.path.insert(0,'/home/user/audit-wb/patientwords-engine/scripts'); import jlens_insights as J; from collections import Counter; rows=J.collect(pathlib.Path('/home/user/audit-wb/patientwords-engine/trace_out'))['gemma-2-2b']; print(Counter((r['endpoint_class'],J.classify(r)) for r in rows))"
```
Proposed fix:
```diff
--- a/technical/index.html
+++ b/technical/index.html
@@ -829 +829
-            var label={retained:'held to the end',suppressed:'formed, then lost (hijack)',absent:'never formed (capture)'};
+            var label={retained:'held to the end',suppressed:'formed, then lost',absent:'never formed'};
and append to the #cap-router caption string: ' · depth classes here are the readout\'s own single-layer labels (pre-July-14 rule), not the persistence-2 capture/hijack taxonomy above'. (Engine-side alternative, for the jlens_depth lane: emit persistence-2, clinical-conditioned classes in export_jlens_depth.py so both figures share one partition.)
```
Verifier correction: The Fig 4 router table (patientwords/technical/index.html:829) labels its rows with the taxonomy words '(hijack)'/'(capture)', but the rows are partitioned by the summaries' patient_depth_class (jlens_readout.py:259-280: single-layer readability, no clinical-readable conditioning; the pre-July-14 rule), while the capture-vs-hijack figure two sections earlier and the Part 2 prose (index.html:268-276) use the adopted July-14 rules (persistence-2 formation, clinical-readable conditioning; jlens_insights.py classify(), PERSISTENCE=2). Cross-tab over the same 476 census rows: suppressed = 31 hijack + 4 capture + 6 unreadable; absent = 40 capture + 102 unreadable; retained = 293 held. Concretely on the displayed table: 6 of the 10 pairs in the row labeled 'never formed (capture)' (mean_recovery +0.163) are 'unreadable' under the adopted taxonomy; the class the page itself says is 'not evidence of capture'; while the '(hijack)' row's 4 pairs and the retained row's 21 do coincide. The table also mixes partitions internally: its steering column's classes originate as taxonomy names (steer_pilot_spec.json items[].class) mapped to endpoint names via export_jlens_depth.py:227 name_map, whereas the translation column uses raw patient_depth_class; the 27 measured pilot pairs coincide under both rules today, so that mix is latent. Fix as proposed (drop the parentheticals, disclose the partition in #cap-router), noting the caption is also mutated at runtime at index.html:847-858, or emit persistence-2 clinical-conditioned classes from export_jlens_depth.py so both figures share one partition.

Found by: r-jlens. Verified: CONFIRMED.

#### F2-M27 · `site:translation/index.html:333` · unguarded-claim

The section lede says the translation was 'applied to every measured phrase (290 so far)', but 290 is qwen3-1.7b's joined-pair count, not a phrase-coverage count: 1031 phrases were translated, at most 350 were measured per model, and joined counts silently exclude measured rows lacking a same-model source measurement (196 for gemma-3-4b-it, 60 for qwen).

Evidence:
```
JS lines 332-334: `'The same LLM translation, applied to every measured phrase ('+maxN+' so far)'` where maxN = max(per_model.n) = 290. Engine data: txcorpus_20260714T224455Z.json has 1031 translated rows; per-model measured translated rows are 350 (gemma-3-4b-it, idx 1-350), 350 (qwen3-1.7b, idx 351-700), 48 (gemma-2-2b on the priority corpus); joined n = 154/290/32 after the silent source-side drops quantified in the scripts/translation_scale.py:149 finding. '(290 so far)' therefore under-describes translation coverage and over-describes measurement coverage simultaneously.
```
Proposed fix:
```diff
--- a/translation/index.html
+++ b/translation/index.html
@@
-          'The same LLM translation, applied to every measured phrase ('+maxN+
-          ' so far) and scored by next-word probability on each model. Mean recovery is what the '+
+          'The same LLM translation, scored on phrases measured under both wordings on the same model ('+maxN+
+          ' pairs on the widest-covered model so far; coverage varies by model). Mean recovery is what the '+
```
Verifier correction: patientwords/translation/index.html:333; the section lede "The same LLM translation, applied to every measured phrase (290 so far)" mislabels a runtime-filled number: maxN=290 is qwen3-1.7b's joined-pair count (translated measurement joined to a same-model original patient measurement), not a translation-coverage or measurement-coverage count. Verified: 1031 phrases translated in the main corpus; 350 translated rows measured per logits model (48 on gemma-2-2b's priority corpus); joins silently drop rows without a same-model source measurement (196 gemma-3-4b-it, 60 qwen3-1.7b; 16 gemma-2-2b dropped for null probabilities), yielding n = 154/290/32. Because maxN is computed at runtime from data/translation_scale.json, the number itself cannot drift and the claims manifest correctly does not cover it; this is a wrong static label around a live number, not an unguarded hardcoded claim; the fix is the proposed prose rewrite ("scored on phrases measured under both wordings on the same model (290 pairs on the widest-covered model so far; coverage varies by model)"), which matches HEAD context exactly and is accurate.

Found by: r-translation. Verified: CONFIRMED.

#### F2-M28 · `site:translation/index.html:339` · unguarded-claim

The at-scale caption states 'translated sentences measured by CPU next-word inference', but the gemma-2-2b row (n=32) comes from hosted Neuronpedia attribution traces (backend 'hosted'), not CPU logits; a provenance label inaccuracy under the frontend's hard rule that provenance labels stay accurate.

Evidence:
```
Caption JS line 338-339: `document.getElementById('tx-scale-cap').textContent='translated sentences measured by CPU next-word inference · exploratory, grows with the nightly cycle · source: data/translation_scale.json';`. Engine data: trace_out/txcorpus_priority_20260714T224455Z/batch_summary.part_*.json all carry "backend": "hosted", "graph_model": "gemma-2-2b" (48 results), and these are the sole source of the gemma-2-2b per_model row; only the gemma-3-4b-it and qwen3-1.7b rows are "backend": "logits" (CPU).
```
Proposed fix:
```diff
--- a/translation/index.html
+++ b/translation/index.html
@@
-          'translated sentences measured by CPU next-word inference · exploratory, grows with the nightly cycle · source: data/translation_scale.json';
+          'translated sentences scored by next-word probability (CPU inference; gemma-2-2b via hosted traces) · exploratory, grows with the nightly cycle · source: data/translation_scale.json';
```
Verifier correction: One refinement worth adding when fixing: the same 'logits' assumption also appears engine-side; translation_scale.py's module docstring ('logits-eval measures p(target) for both sides per model') and the emitted "_" note in translation_scale.json ('joined to the original patient logits rows per phrase and model') both describe the txcorpus measurements as logits rows, but the txcorpus_priority_20260714T224455Z batch was measured via the hosted circuit-trace path (backend "hosted"). The frontend caption fix as proposed is correct; a complete fix would also neutralize the engine wording (e.g. 'joined to the original patient measurement rows (CPU logits or hosted trace) per phrase and model') so the site copy's own metadata stops asserting CPU provenance for the gemma-2-2b row.

Found by: r-translation. Verified: CONFIRMED.

#### F2-M29 · `site:wording-differences/index.html:209` · unguarded-claim

Fig. 2 stat line 'Variety shift Δ: +13% (A → B, 0.39 → 0.52) and +10% (C → D, 0.29 → 0.39) ... Register shift Δ: −10% (A → C) and −13% (B → D)' plus the four edge captions (l.259, 263, 267, 271) trace only to modes/4quadrant2/*.html renders, which are engine-replaced wholesale; no JSON source exists for claim_check to guard.

Evidence:
```
modes/4quadrant2/index_06.html: 'Variety shift Δ: +13% probability (0.39 → 0.52)', '+10% probability (0.29 → 0.39)', 'Register shift Δ: -10% probability (0.39 → 0.29)', '-13% probability (0.52 → 0.39)' — all match the page today; nothing in data/*.json carries the four quadrant probabilities.
```
Proposed fix:
```
Copy the quadrant cell probabilities into data/provenance.json (e.g. "quadrant2_palpitations": {"A": 0.39, "B": 0.52, "C": 0.29, "D": 0.39}, from the engine trace behind modes/4quadrant2/index_06), then add: {"page": "wording-differences/index.html", "snippet": "+13% (A → B, 0.39 → 0.52) and +10% (C → D, 0.29 → 0.39)", "source": "data/provenance.json", "expr": "[d['quadrant2_palpitations']['A'], d['quadrant2_palpitations']['B'], d['quadrant2_palpitations']['C'], d['quadrant2_palpitations']['D'], round((d['quadrant2_palpitations']['B']-d['quadrant2_palpitations']['A'])*100), round((d['quadrant2_palpitations']['D']-d['quadrant2_palpitations']['C'])*100)]", "expected": [0.39, 0.52, 0.29, 0.39, 13, 10]}
```
Verifier correction: Finding confirmed as stated, with two refinements. (a) Precise provenance for the fix: the quadrant cell probabilities exist only in the engine repo at trace_out/quadrants_20260715T142413Z/batch_summary.part_01.json (results[] entry with index 6, i.e. index_06), as raw values A=0.393, B=0.523, C=0.295, D=0.391; the proposed provenance.json copy should either store these raw values and round in the expr (e.g. round(d[...]['A'],2)), or document that the stored 0.39/0.52/0.29/0.39 are the page-rounded copies; storing raw values is the more drift-honest option and still yields expected [0.39, 0.52, 0.29, 0.39, 13, 10] with rounding in the expr. (b) Coverage: one guard on the four cell probabilities also transitively covers the register-shift deltas quoted at lines 259/263 and the '+10–13%' range in the explainer at line 208, since all derive from the same four cells; adding round((A−C)*100) and round((B−D)*100) terms (expected 10 and 13) to the same expr would make that explicit at no extra data cost. Proposed manifest entry validates against claim_check.evaluate as written (snippet found in page; expr returns expected).

Found by: c-unguarded. Verified: CONFIRMED.

### Low: doc drift, latent keying gaps, low-drift unguarded numbers

#### F2-L01 · `engine:docs/prereg_divergence_log.md:12` · doc-drift

The measurement-matrix divergence row ('seven models measured') is stale: meditron3-8b and apertus-8b-meditronfo joined the logits model map on 2026-07-17 (apertus results already landed at HEAD), making nine models; the BH-family code handles them correctly but the log understates the expansion.

Evidence:
```
Logged row (line 12): "seven models measured (llama-3.2-3b, olmo-2-1b, gemma-2-2b-it added; medgemma-4b-it probed 07-13) | extra models are secondary/exploratory; primary endpoints stay on the pre-registered four". Actual: ops/dashboard.json decisions_log 2026-07-17: "MEDICAL SUCCESSORS INCORPORATED: ... Apertus-8B-MeditronFO ... both added to the logits model map and a joint limit-3 probe"; HEAD commit 9696df4 is itself "Logits eval: trace_out/pairs_20260714T135150Z__apertus-8b-meditronfo". Code is safe: paired_stats_rigor._PREREG_MODELS (line 62) pins the confirmatory four and any new model id falls into the post-registration exploratory BH family automatically (lines 439-443), so no published confirmatory number changes — the log row alone is behind reality and its parenthetical model list will read as exhaustive at endpoint-writeup time.
```
Proposed fix:
```diff
--- a/docs/prereg_divergence_log.md
+++ b/docs/prereg_divergence_log.md
@@ -12 +12 @@
-| 2026-07-11 → | measurement matrix expanded | CPU logits on four models | seven models measured (llama-3.2-3b, olmo-2-1b, gemma-2-2b-it added; medgemma-4b-it probed 07-13) | extra models are secondary/exploratory; primary endpoints stay on the pre-registered four |
+| 2026-07-11 → | measurement matrix expanded | CPU logits on four models | nine models measured (llama-3.2-3b, olmo-2-1b, gemma-2-2b-it added; medgemma-4b-it probed 07-13; meditron3-8b + apertus-8b-meditronfo added 07-17) | extra models are secondary/exploratory (separate BH family); primary endpoints stay on the pre-registered four |
```
Verifier correction: docs/prereg_divergence_log.md line 12 is stale, but the fix should say the two 07-17 additions are probe-only, and should also repair the pre-existing medgemma inconsistency rather than propagate it. Accurate replacement row: "| 2026-07-11 → | measurement matrix expanded | CPU logits on four models | eight models measured (llama-3.2-3b, olmo-2-1b, gemma-2-2b-it, medgemma-4b-it added 07-10→13); meditron3-8b + apertus-8b-meditronfo added to the logits model map 07-17 (limit-3 probe landed; full runs pending) | extra models are secondary/exploratory (separate BH family per the 2026-07-14 split); primary endpoints stay on the pre-registered four |". Rationale: medgemma-4b-it has 219 landed measurement rows across three batches and is one of the 8 models in the published stats file's exploratory BH family, so it belongs among "measured"; meditron3-8b and apertus-8b-meditronfo each have exactly 3 probe rows at HEAD and are not yet in any stats file, so "nine models measured" (the finder's wording) would itself be a fresh inaccuracy. The finder's core claim; the row understates the expansion and will read as exhaustive at endpoint-writeup time while paired_stats_rigor.py handles new ids safely; stands.

Found by: p-amendments. Verified: CONFIRMED.

#### F2-L02 · `engine:scripts/jlens_insights.py:60` · other

Daily drift-sentinel stems re-enter the census as duplicate rows: the same 3 phrases with byte-identical depth readouts land per sentinel day (currently 6 of 476 rows from 2 days), inflating the formation census by the number of sentinel days as the daily readout keeps firing.

Evidence:
```
collect()'s dataset guard (L60-61) excludes txcorpus/_txopus/_txplacebo/__context but not repeated drift_sentinel_* stems; drift_sentinel_20260714__jlens_gemma-2-2b and drift_sentinel_20260715__jlens_gemma-2-2b results[].depth compare equal (verified: da==db True), yet both contribute 3 points each ((drift_sentinel_20260714, 1-3) and (drift_sentinel_20260715, 1-3) with identical clin_formed/pat_formed/class). The page's Queued-next note (index.html:363) itself says 'every day-over-day lens comparison so far reads out identical'. With the sentinel firing daily since July 14, n_pairs and the formation quantiles accrete duplicate mass with no cap. Repro: python3 -c "import json; a=json.load(open('/home/user/audit-wb/patientwords-engine/trace_out/drift_sentinel_20260714__jlens_gemma-2-2b/jlens_summary.part_01.json')); b=json.load(open('/home/user/audit-wb/patientwords-engine/trace_out/drift_sentinel_20260715__jlens_gemma-2-2b/jlens_summary.part_01.json')); print([r.get('depth') for r in a['results']]==[r.get('depth') for r in b['results']])" -> True
```
Proposed fix:
```diff
--- a/scripts/jlens_insights.py
+++ b/scripts/jlens_insights.py
@@ in collect(), before the loop:
+    sentinels = sorted({p.parent.name.split("__jlens_")[0]
+                        for p in trace_root.glob("drift_sentinel_*__jlens_*/jlens_summary.part_*.json")})
+    latest_sentinel = sentinels[-1] if sentinels else None
@@ inside the loop, with the other guards:
+        if dataset.startswith("drift_sentinel_") and dataset != latest_sentinel:
+            # the sentinel repeats the same phrases daily; keep one day so the
+            # census does not accrete duplicates (readouts verified identical)
+            continue
(Alternatively dedupe on phrase identity across stems; keeping only the newest sentinel is the minimal deterministic version.)
```
Verifier correction: As filed, with two precisions: (a) the quoted "every day-over-day lens comparison so far reads out identical" note is at patientwords/technical/index.html:365, not index.html:363; (b) the duplication also affects the gemma-2-2b-it census rows (verified byte-identical depths across the two it-model sentinel dirs), so the instruction_tuning n_paired/median block on the technical page accretes the same 3 duplicate phrases per sentinel day, not just the base-model formation census.

Found by: r-jlens. Verified: CONFIRMED.

#### F2-L03 · `engine:scripts/jlens_insights.py:114` · doc-drift

The 'held' class is exempt from both the persistence rule and clinical-readable conditioning (a single final-layer readout appearance counts), which the payload's _ field never states; 30 of 293 published held rows never 'formed' under the stated rule, 14 of them with neither side ever forming.

Evidence:
```
classify() L114-115 returns 'held' whenever pat[-1].target_rank is not None, before any other check; formation_layer's docstring (L30-31) acknowledges it ('A final-layer appearance alone still counts as held via the final rank, not here') but the published _ field (data/jlens_insights.json:2) states only the 2-consecutive-layer rule for 'never formed', and describes no held exception. Recomputed counts: 30 held rows with pat_formed null; 14 with clin_formed AND pat_formed both null (e.g. published points (pairs_20260711T051145Z, 30), (pairs_20260713T050939Z, 51)). Repro: recompute, then count points class=='held' with pat_formed==null.
```
Proposed fix:
```diff
--- a/scripts/jlens_insights.py
+++ b/scripts/jlens_insights.py
@@ _ field, append:
+              " 'Held' is scored from the final layer alone: a target ranking in the"
+              " final readout counts as held even if it never met the 2-layer"
+              " formation rule."
(One sentence added to the payload's self-description; no numbers change.)
```
Verifier correction: As filed, with one strengthening detail: the payload's `_` field is not merely silent on the held exemption; its sentence "pairs where neither wording ever reads out are the 'unreadable' class" is contradicted by the 14 published held rows where both clin_formed and pat_formed are null under the stated 2-layer rule. The proposed one-sentence addition to the `_` string should therefore also make clear that the held check precedes the unreadable check (final-layer rank wins over never-formed-on-both-sides).

Found by: r-jlens. Verified: CONFIRMED.

#### F2-L04 · `engine:scripts/study_timeline.py:104` · doc-drift

tierb_split.py's docstring (lines 5-7) claims 'published aggregate counts' use ONLY the exploration split, but every published Tier B count includes holdout members: study_timeline.py's totals.tierb_accepted (site timeline.json, currently 614), dashboard tierb.accepted_pairs (700), and payload batches[].generated.accepted; a wording/practice mismatch that invites a future auditor to read the counts as exploration-only when they are whole-Tier-B counts.

Evidence:
```
tierb_split.py:5-7: 'Interim analyses during the collection week (nightly critic, dashboard deltas, synthesis drafts, published aggregate counts) use ONLY the ~90% exploration split.' vs study_timeline.py:104-105 `"tierb_accepted": sum(b["accepted"] for b in gen_batches if b.get("tierb") ...)` which sums whole-batch accepted counts (holdout members included by construction); the registered Amendment 1 text (preregistration_tierB.md:96-100) restricts only 'interim analyses', not acceptance counts, so the docstring overstates the rule the code implements.
```
Proposed fix:
```diff
--- a/scripts/tierb_split.py
+++ b/scripts/tierb_split.py
@@ -4,8 +4,9 @@
 hash of its clinical prompt: ``sha1(clinical_prompt) mod 10 == 0`` (~10%) is
 the **holdout**, analyzed exactly once after collection ends. Interim analyses
-during the collection week (nightly critic, dashboard deltas, synthesis
-drafts, published aggregate counts) use ONLY the ~90% exploration split.
+during the collection week (nightly critic, dashboard deltas, synthesis
+drafts, published aggregate statistics) use ONLY the ~90% exploration split;
+whole-Tier-B ACCEPTANCE counts (dashboard, timeline) intentionally include
+holdout members — membership counting is not analysis.
Optionally add a `"note": "includes sealed holdout pairs"` sibling key next to tierb_accepted in study_timeline.py's totals.
```
Found by: p-holdout. Verified: CONFIRMED.

#### F2-L05 · `engine:scripts/tierb_split.py:30` · prereg-mismatch

The registered text never defines split membership for an empty or missing clinical prompt; the code returns explore (`if not clinical_prompt: return False`). Currently moot; all 700+ Tier B pairs have non-empty top_prompts, and sha1('')%10==5 so even the literal registered arithmetic would classify an empty string as explore; but a missing/None prompt is genuinely outside the registered rule and only the module docstring documents the choice.

Evidence:
```
Code: `if not clinical_prompt:\n        return False` (tierb_split.py:30-31) with docstring 'empty/missing prompts stay explore' (:29). Registered text: docs/preregistration_tierB.md:94-95 says only 'pairs where `sha1(clinical_prompt)` mod 10 == 0 (~10%) form the holdout' — sha1 of a missing value is undefined. Verified: 0 empty/missing top_prompts across all dashboard-listed Tier B batch files; int(hashlib.sha1(b'').hexdigest(),16)%10 == 5.
```
Proposed fix:
```
Document the edge in the divergence log rather than the frozen prereg: add a row to docs/prereg_divergence_log.md — 'empty/missing clinical prompts (none observed in Tier B data) are assigned to explore by scripts/tierb_split.py:30; for the empty string this coincides with the registered arithmetic (sha1("")%10==5); the choice only binds for absent prompts, which the validators prevent'. No code change.
```
Verifier correction: Finding stands as filed with two precision corrections. (a) Counts: the Tier B corpus at HEAD is 907 pairs across 16 batch files (finder's "700+" is a stale lower bound), all with non-empty prompts; the batch-file field is `top_prompt` (singular), not `top_prompts`. (b) Reachability nuance strengthening the low finding: the empty/missing branch is not purely hypothetical in code; tierb_split.stamp_rows(:65) passes row.get("clinical_prompt") and urgency_shift.py:106 builds that field as (prompts or {}).get("clinical"), so a None prompt from a malformed summary would be silently assigned to explore under a rule that exists only in a docstring, never in the registered text or divergence log. Proposed fix unchanged and appropriate: add one row to docs/prereg_divergence_log.md documenting that empty/missing clinical prompts (none observed in the 907 Tier B pairs) are assigned to explore by scripts/tierb_split.py:30, noting the empty-string case coincides with the registered arithmetic (sha1('')%10==5) so the choice binds only for absent prompts. No code change; do not edit the frozen prereg.

Found by: p-holdout. Verified: CONFIRMED.

#### F2-L06 · `engine:scripts/translation_scale.py:111` · doc-drift

lens_recovery silently discards translated-side lens readouts whose source batch has no patient-side lens run (25 of 100 landed tx readouts today) and its '_' note does not state this matching requirement, so n_paired can be misread as translated-side lens coverage.

Evidence:
```
Lines 110-111: `src = src_lens.get((gen.get("source_batch"), gen.get("source_index")))` / `if tx is None or src is None: continue`. Instrumented count on HEAD: tx_lens = 100 readouts (txcorpus_priority2: 75, txcorpus_priority: 25); 25 dropped with src is None (all txcorpus_priority rows, whose early source batches pairs_20260706*/07* have no pairs_*__jlens_gemma-2-2b run); published n_paired = 75. The '_' string (lines 116-118) describes the formation rule only, not the pairing requirement or the unmatched count.
```
Proposed fix:
```diff
--- a/scripts/translation_scale.py
+++ b/scripts/translation_scale.py
@@ def lens_recovery(...):
     return {
         "_": ("Lens view of translation, gemma-2-2b, EXPLORATORY (phrases predate "
               "amendment 2 adoption): formation = readable for 2 consecutive layers "
-              "in the top-8 window, per the adopted counting rules."),
+              "in the top-8 window, per the adopted counting rules. Pairs require a "
+              "patient-side lens run of the source batch; unmatched translated "
+              "readouts are excluded and counted in n_unmatched."),
         "n_paired": len(joined),
+        "n_unmatched": sum(1 for k in tx_lens
+                           if k not in matched_tx_keys),
```
Verifier correction: Finding stands as filed with two refinements. First, the function docstring (translation_scale.py:92-96) does state the both-wordings pairing requirement ("read by the lens under BOTH wordings (patient side via the source batch's regular pull, translated side via a txcorpus pull)"); the drift is specifically that the published artifact's self-describing "_" field omits it and the JSON carries no unmatched count; the gap is in the emitted metadata, not the source documentation. Second, the proposed diff references an undefined variable `matched_tx_keys`; a working minimal fix must count unmatched inline, e.g. in lens_recovery track `unmatched = 0` and increment it in the loop when `tx is not None and src is None`, then emit `"n_unmatched": unmatched` alongside the extended "_" sentence ("Pairs require a patient-side lens run of the source batch; translated readouts without one are excluded and counted in n_unmatched."). On today's data that emits n_unmatched=25 with n_paired=75.

Found by: r-translation. Verified: CONFIRMED.

#### F2-L07 · `engine:scripts/validate_frontend_contract.py:289` · unguarded-claim

The frontend-contract schema for jlens_depth.json checks {model, generated_utc, class_labels, blocks, translation} but not 'steering', so the live 11/12 and 2/3 router numbers have no contract guard (and no claim_check manifest entry exists for them, since they never appear as prose): a regeneration that drops or malforms the steering block passes validation and the page silently reverts the column to 'queued'.

Evidence:
```
Code: '"jlens_depth.json": ({"model": str, "generated_utc": str, "class_labels": dict, "blocks": list, "translation": dict}, set()),' (lines 289-290) — no "steering" key. Consumer fallback: technical/index.html:832 'var st=(j.steering&&j.steering.by_class)||null;' and :844 renders 'queued' when st is null, with no error state. The numbers are runtime-filled only (grep for '11', '12', '2 of 3' prose on the page: no hardcoded occurrences), so this validator is the only possible guard.
```
Proposed fix:
```diff
--- a/scripts/validate_frontend_contract.py
+++ b/scripts/validate_frontend_contract.py
@@ -289,2 +289,3 @@
         "jlens_depth.json": ({"model": str, "generated_utc": str, "class_labels": dict,
-                              "blocks": list, "translation": dict}, set()),
+                              "blocks": list, "translation": dict,
+                              "steering": dict}, set()),

(now that the steering column is live; if the block is ever intentionally retired, the schema edit is the visible, reviewable act.)
```
Found by: r-steering. Verified: CONFIRMED.

#### F2-L08 · `site:CLAUDE.md:27` · doc-drift

Frontend CLAUDE.md's load-bearing 'Draft labels' rule still quotes the retired literal "draft pending domain review", but the live vocabulary_status (site data and engine tiers file, relabeled 2026-07-14 referee-response program) is "owner-reviewed v1 · domain review pending", which the pages now render.

Evidence:
```
patientwords/CLAUDE.md:27-29: 'Urgency-tier content is marked "draft pending domain review" (from `data/urgency_shift.json:vocabulary_status`)'. Live values: patientwords/data/urgency_shift.json:2 `"vocabulary_status": "owner-reviewed v1 · domain review pending"` == engine data/urgency_tiers.draft.json `"status"`; pages render the new label (index.html:441 'tiers owner-reviewed v1 · domain review pending', simulated-scenarios/index.html:660 fallback literal 'owner-reviewed v1 · domain review pending'; only start-here/index.html:547 keeps the old string as an absent-data fallback). The rule's intent (do not remove/soften until docs/tier_review_checklist.md approval) still holds — domain review IS still pending — but the quoted marker no longer matches what a maintainer will find, inviting either a false 'label was removed' alarm or an incorrect revert of the owner-directed relabel.
```
Proposed fix:
```diff
--- a/CLAUDE.md (patientwords)
+++ b/CLAUDE.md (patientwords)
@@ -27,3 +27,3 @@
-- **Draft labels are load-bearing.** Urgency-tier content is marked "draft pending domain
-  review" (from `data/urgency_shift.json:vocabulary_status`); do not remove or soften that
+- **Draft labels are load-bearing.** Urgency-tier content carries the review-status label
+  from `data/urgency_shift.json:vocabulary_status` (currently "owner-reviewed v1 · domain review pending"); do not remove or soften that
```
Found by: r-urgency. Verified: CONFIRMED.

#### F2-L09 · `site:data/urgency_shift.json:38` · recompute-divergence

Publish lag, not a computation error: the site copy at frontend HEAD bbf5874 (published 2026-07-16 13:27 UTC, commit 244c698) omits four trace legs landed since, including both logits models that joined the registry today, so a fresh recompute at engine HEAD diverges on every aggregate until the next nightly republish.

Evidence:
```
Published vs recomputed-at-HEAD: measurements 4542 vs 4653; flips 2040 vs 2086; flip_classes.downgrade 367 vs 372; flip_classes.lateral 304 vs 306; flip_classes.uninformative 1302 vs 1341; per_model_deduped missing meditron3-8b {n_phrases 3, flips 2, downgrades 1} and apertus-8b-meditronfo {n_phrases 3, flips 2, downgrades 1}; gemma-2-2b n_phrases 995 vs 1053, gemma-2-2b-it n_phrases 122 vs 165; concordance downgrade_on_2plus_models 53 vs 56, flip_on_2plus_models 522 vs 524. Excluding exactly the 4 post-publish legs — (pairs_20260715T132350Z, gemma-2-2b): 69 rows, (pairs_20260710T050657Z, gemma-2-2b-it): 50 rows, (pairs_20260714T135150Z, meditron3-8b): 3 rows, (pairs_20260714T135150Z, apertus-8b-meditronfo): 3 rows — EVERY published field matches exactly: all 3759 trimmed rows, per_model, per_model_deduped, flip_classes, concordance, mitigation, tier_examples, tiers, vocabulary_status. Reproduction: cd /home/user/audit-wb/patientwords-engine && python3 scripts/urgency_shift.py --tiers data/urgency_tiers.draft.json --frontend /home/user/audit-wb/patientwords --out <abs sandbox path>; filter rows by tierb_split != 'holdout' and the 4-leg exclusion, re-derive each summary block per the code, compare to the published file.
```
Proposed fix:
```diff
No data correction needed — the next nightly republish clears the lag. To make lag detectable instead of inferable, stamp provenance into the site payload:
--- a/scripts/urgency_shift.py
+++ b/scripts/urgency_shift.py
@@ -396,6 +396,8 @@
     site_payload = {
         "vocabulary_status": vocab_meta.get("status", "draft pending domain review"),
+        "generated_utc": __import__("datetime").datetime.now(
+            __import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "tiers": vocab_meta.get("tiers"),
```
Verifier correction: Finding stands as written (severity low, recompute-divergence correctly classified as publish lag). One evidence refinement: at the audited HEADs the flip_classes.uninformative divergence is 1302 vs 1341 as stated, and the finding's summary sentence "including both logits models that joined the registry today" refers to 2026-07-16 (meditron3-8b and apertus-8b-meditronfo, whose legs landed in engine commit 9696df4 at 2026-07-16T23:34:40Z, ten hours after the 13:27:41Z publish commit 244c698). All published fields match the 4-leg-excluded recompute exactly, so no published number is wrong at its publish timestamp; the divergence exists only against the newer engine tree until the next nightly republish.

Found by: r-urgency. Verified: CONFIRMED.

#### F2-L10 · `site:dialect-differences/index.html:218` · unguarded-claim

'3 of 20 terms pend a re-trace' in the traced line is unguarded as such; the adjacent '153 (17 baselines + 136 framings' guard on the same span would fire when the re-trace lands (items -> 20), so exposure is indirect only; an explicit guard makes the rewrite target unambiguous.

Evidence:
```
data/dialects.json len(items) == 17; 20 planned terms implies 3 pending; no manifest expr covers the '3 of 20' fragment.
```
Proposed fix:
```
{"page": "dialect-differences/index.html", "snippet": "3 of 20 terms pend a re-trace", "source": "data/dialects.json", "expr": "len(d['items'])", "expected": 17, "_": "when the 3-term gap lands this fires together with the 153-graph claim; rewrite both fragments"}
```
Found by: c-unguarded. Verified: CONFIRMED.

#### F2-L11 · `site:dialect-differences/index.html:305` · unguarded-claim

Dose-response ladder caption hardcodes 'at 32% (rung 1) and 11% (rung 2), then "apple" from the mixed rung on' from frozen provenance.json ladder_digestive; unguarded.

Evidence:
```
provenance.json ladder_digestive.rungs: rung1 top=[token,0.322] -> 32%, rung2 top=[token,0.114] -> 11%, rung3 top token 'apple'.
```
Proposed fix:
```
{"page": "dialect-differences/index.html", "snippet": "at 32% (rung 1) and 11% (rung 2)", "source": "data/provenance.json", "expr": "[round(d['ladder_digestive']['rungs'][0]['top'][1]*100), round(d['ladder_digestive']['rungs'][1]['top'][1]*100), d['ladder_digestive']['rungs'][2]['top'][0]]", "expected": [32, 11, "apple"]}
```
Verifier correction: Finding stands as filed, with two refinements: (a) the JSON stores the rung-1/2 top token as the wordpiece "ant" (0.322 / 0.114), not "antacid"; the caption's rendered word "antacid" is a continuation not directly checkable from provenance.json, so the proposed expr correctly checks only the probabilities and the rung-3 token "apple"; (b) the adjacent explainer at line 306 repeats the same unguarded numbers ("32%, then 11%" and the "27%–34%" rung-mean range), so the manifest entry should ideally add a snippet_alt or a second claim for line 306, though the proposed minimal fix for line 305 is valid as-is.

Found by: c-unguarded. Verified: CONFIRMED.

#### F2-L12 · `site:index.html:821` · unguarded-claim

Try-it widget hardcodes six scenario-85 spread values but only two are guarded: index.html:821-822 carries 0.059 (2nd clinical), 0.028 (3rd clinical), 0.183 (top patient), 0.068 (2nd patient) unguarded; start-here/index.html:413-414 repeats all values at 2dp unguarded; share/card.html:50-60 bakes 69%/18%/4% into the og:image source unguarded.

Evidence:
```
simulated_scenarios.json (pairs_20260707T171223Z, batch_index 49): spread_clinical = [[t,0.692],[t,0.059],[t,0.028],...], spread_patient = [[t,0.183],[t,0.068],[t,0.06],[t,0.058],[t,0.043]]; manifest guards only 0.692 and 0.043 on index.html.
```
Proposed fix:
```
Add: [{"page": "index.html", "snippet": "'mask',0.059", "source": "data/simulated_scenarios.json", "expr": "[next(s for s in d['scenarios'] if s['batch']=='pairs_20260707T171223Z' and s['batch_index']==49)['spread_clinical'][1][1], next(s for s in d['scenarios'] if s['batch']=='pairs_20260707T171223Z' and s['batch_index']==49)['spread_clinical'][2][1], next(s for s in d['scenarios'] if s['batch']=='pairs_20260707T171223Z' and s['batch_index']==49)['spread_patient'][0][1], next(s for s in d['scenarios'] if s['batch']=='pairs_20260707T171223Z' and s['batch_index']==49)['spread_patient'][1][1]]", "expected": [0.059, 0.028, 0.183, 0.068]}, {"page": "start-here/index.html", "snippet": "'mask',0.06", "source": "data/simulated_scenarios.json", "expr": "[round(next(s for s in d['scenarios'] if s['batch']=='pairs_20260707T171223Z' and s['batch_index']==49)['prob_clinical'],2), round(next(s for s in d['scenarios'] if s['batch']=='pairs_20260707T171223Z' and s['batch_index']==49)['spread_patient'][0][1],2)]", "expected": [0.69, 0.18]}, {"page": "share/card.html", "snippet": "69%", "source": "data/simulated_scenarios.json", "expr": "[round(next(s for s in d['scenarios'] if s['batch']=='pairs_20260707T171223Z' and s['batch_index']==49)['prob_clinical']*100), round(next(s for s in d['scenarios'] if s['batch']=='pairs_20260707T171223Z' and s['batch_index']==49)['spread_patient'][0][1]*100), round(next(s for s in d['scenarios'] if s['batch']=='pairs_20260707T171223Z' and s['batch_index']==49)['prob_patient']*100)]", "expected": [69, 18, 4]}]
```
Verifier correction: One imprecision, does not change the verdict: start-here/index.html:414 does not repeat index.html's exact patient bar set; its third patient bar is spread_patient[2] (0.06 at 2dp), not the target-token 0.043 shown fifth on index.html. Corrected statement: start-here hardcodes 0.69/0.06/0.03 (spread_clinical[0..2], 2dp) and 0.18/0.07/0.06 (spread_patient[0..2], 2dp), all six unguarded. Also note the proposed start-here manifest entry guards only 0.69 and 0.18 of those six; extending its expr to all six rounded values would be the complete fix.

Found by: c-unguarded. Verified: CONFIRMED.

#### F2-L13 · `site:methods.html:231` · unguarded-claim

'the three sentinel pairs' (l.231) and 'a daily three-pair sentinel re-trace' (l.527) hardcode the sentinel set size (audit-1 known item, still present); the technical page already plans a lens sentinel addition, so the set may grow.

Evidence:
```
drift_series.json series has exactly 3 pairs on every measured day (keys '1','2','3' for 20260713-20260716).
```
Proposed fix:
```
{"page": "methods.html", "snippet": "three sentinel pairs", "source": "data/drift_series.json", "expr": "[min(len(v) for v in d['series'].values()), max(len(v) for v in d['series'].values())]", "expected": [3, 3]} (add a second entry with snippet "daily three-pair sentinel re-trace", same expr/expected)
```
Verifier correction: Narrow the finding to the non-duplicate part. methods.html:231 ("three sentinel pairs") is Audit 1 F-M10, already queued with a fix; do not re-file. The new finding (severity low, unguarded-claim): methods.html:527 "a daily three-pair sentinel re-trace" is a second hardcoded sentinel-set-size occurrence with no claims_manifest guard and no runtime fill, and it is NOT covered by F-M10's queued manifest entry (which pins only the line-231 snippet "three sentinel pairs, and every"). If the sentinel pair set changes (pairs_file swap, or expansion alongside the planned lens-sentinel addition at technical/index.html:365), line 527 goes stale silently even after F-M10's fix lands. Minimal fix; append one entry to the claims array in engine data/claims_manifest.json, alongside F-M10's queued entry: {"page": "methods.html", "snippet": "daily three-pair sentinel re-trace", "source": "data/drift_series.json", "expr": "[min(len(v) for v in d['series'].values()), max(len(v) for v in d['series'].values())]", "expected": [3, 3]}. Verified: expr evaluates to [3,3] under claim_check.py's restricted eval sandbox against the current site copy of drift_series.json, and the snippet matches line 527 exactly once. Additive manifest entries break no consumer (claims_manifest.json is read only by scripts/claim_check.py and tests/test_claim_check.py). The finder's original single-entry expr is correct but its first snippet duplicates F-M10; drop that entry.

Found by: c-unguarded. Verified: CONFIRMED.

#### F2-L14 · `site:phrase-dataset/index.html:124` · unguarded-claim

Starkest-case sentence hardcodes 'at 20%' and 'at 68%' (pair 16) from the frozen hand-measured set; unguarded but low drift (stress_pairs.json changes only on deliberate re-measurement).

Evidence:
```
stress_pairs.json row with provenance.source_row == 16: clinical observed_prob 0.2, patient observed_prob 0.68.
```
Proposed fix:
```
{"page": "phrase-dataset/index.html", "snippet": "at 20%; phrase it as", "source": "data/stress_pairs.json", "expr": "[next(p for p in d if p['provenance']['source_row']==16)['provenance']['clinical']['observed_prob'], next(p for p in d if p['provenance']['source_row']==16)['provenance']['patient']['observed_prob']]", "expected": [0.2, 0.68]}
```
Found by: c-unguarded. Verified: CONFIRMED.

#### F2-L15 · `site:start-here/index.html:289` · unguarded-claim

Panel-6 SVG labels hardcode 'ice cream 29%' (l.289) and 'antacid 31%' (l.309) from the frozen provenance icecream_antacid case; unguarded, and the 29% is a round-half-up of 0.285 that Python's round() would render 28, so any future guard must pin the raw value.

Evidence:
```
provenance.json translation_cases.icecream_antacid: patient=[token,0.285] (28.5% -> displayed 29%), translated=[token,0.312] (round(31.2)=31).
```
Proposed fix:
```
Add: [{"page": "start-here/index.html", "snippet": "ice cream 29%", "source": "data/provenance.json", "expr": "d['translation_cases']['icecream_antacid']['patient'][1]", "expected": 0.285}, {"page": "start-here/index.html", "snippet": "antacid 31%", "source": "data/provenance.json", "expr": "round(d['translation_cases']['icecream_antacid']['translated'][1]*100)", "expected": 31}]
```
Found by: c-unguarded. Verified: CONFIRMED.

#### F2-L16 · `site:technical/index.html:647` · unguarded-claim

Lens-configuration numbers are hardcoded without guards: 'Ranks are within the lens's top-8 readout' + 'two consecutive layers' (endnote l.647-649), 'formation requires two consecutive readable layers' (l.274-275), and methods.html:358 'that layer's top 8'; they trace to jlens_insights.json persistence_layers/window_sensitivity and would silently drift if the readout config changed.

Evidence:
```
jlens_insights.json: persistence_layers = 2; window_sensitivity keys include '8'; method_credit and '_' note both state the top-8 window.
```
Proposed fix:
```
Add: [{"page": "technical/index.html", "snippet": "lens's top-8 readout", "source": "data/jlens_insights.json", "expr": "['8' in d['window_sensitivity'], d['persistence_layers']]", "expected": [true, 2]}, {"page": "methods.html", "snippet": "that layer&rsquo;s top 8", "source": "data/jlens_insights.json", "expr": "'8' in d['window_sensitivity']", "expected": true}]
```
Verifier correction: Finding stands as filed, one precision note: the page is not entirely unguarded against this config; technical/index.html:793 runtime-fills d.persistence_layers into the taxonomy figure caption; but the three cited spans (technical/index.html:274-275, 647-649; methods.html:358) are static prose with no manifest guard and no runtime fill, so they alone would go stale if the lens readout config changed. The proposed two manifest entries are correct verbatim and pass claim_check.py against current data (evaluated [True, 2] and True).

Found by: c-unguarded. Verified: CONFIRMED.

#### F2-L17 · `site:technical/index.html:887` · unguarded-claim

The Fig 5 caption and body text hardcode 'every pair identical' / 'identical lens readouts on every pair' instead of computing identity from instruction_tuning.pairs, so the first regen in which the -it host starts returning distinct readouts silently publishes a false caption.

Evidence:
```
index.html:886-887 sets the caption to a fixed string '... every pair identical, so the two rows mirror each other exactly · not yet a tuning comparison'; :889-892 hardcodes 'return identical lens readouts on every pair, layer by layer'. Both are true today (all 31 published pairs have base==it) but nothing checks it.pairs at render time, and the engine payload carries no identical_readouts flag (see the medium instruction_tuning finding). The site's own claim_check convention (per audit 1 F-M13 discussion) is that data-dependent prose should be computed or manifest-guarded.
```
Proposed fix:
```diff
--- a/technical/index.html
+++ b/technical/index.html
@@ Fig 5 block, before setting captions:
+        var allSame=it.pairs.every(function(p){return p.base===p.it;});
@@
-        document.getElementById('cap-it').textContent=
-          'patient-side formation layer for the '+it.n_paired+' phrases read under both model ids · every pair identical, so the two rows mirror each other exactly · not yet a tuning comparison';
+        document.getElementById('cap-it').textContent=
+          'patient-side formation layer for the '+it.n_paired+' phrases read under both model ids'+
+          (allSame?' · every pair identical, so the two rows mirror each other exactly · not yet a tuning comparison'
+                  :' · readouts now differ on some pairs; treat as a genuine two-model comparison pending re-review');
and branch the dd-it-text paragraph on the same allSame flag (keep the current same-host sentence only when allSame is true).
```
Verifier correction: As filed, with one line-range correction: the hardcoded body text assignment spans technical/index.html lines 888-892 (not 889-892); the 'identical lens readouts on every pair, layer by layer' string is on line 890. The caption citation (886-887) is exact. read_map: [(patientwords/data/jlens_insights.json, patientwords/technical/index.html Fig 5 block lines 862-893, fields instruction_tuning.{n_paired,pairs[].base,pairs[].it}), (patientwords-engine/scripts/jlens_insights.py analyze() lines 229-246, ops/jlens_insights.json + site data/jlens_insights.json, fields instruction_tuning.{it_model,n_paired,base_median,it_median,pairs,_}), (patientwords-engine/data/claims_manifest.json, engine claim_check convention, fields page/snippet/source/expr/expected; no entry covers the identity claim)]

Found by: r-jlens. Verified: CONFIRMED.

#### F2-L18 · `site:translation/index.html:224` · unguarded-claim

Worsened-case numbers 'prescription (38%) with topical (15%)' (l.224) and the steering control '5 random features at strength 10 recovered 0/5' (l.300) are unguarded; both trace to frozen provenance.json blocks.

Evidence:
```
provenance.json translation_cases.worsened_prescription_topical: patient=[token,0.384] -> 38%, translated=[token,0.146] -> round(14.6)=15%; steering_titration.placebo = {recovered: 0, n: 5}.
```
Proposed fix:
```
Add: [{"page": "translation/index.html", "snippet": "(38%) with", "source": "data/provenance.json", "expr": "[round(d['translation_cases']['worsened_prescription_topical']['patient'][1]*100), round(d['translation_cases']['worsened_prescription_topical']['translated'][1]*100)]", "expected": [38, 15]}, {"page": "translation/index.html", "snippet": "strength 10 recovered 0/5", "source": "data/provenance.json", "expr": "[d['steering_titration']['placebo']['recovered'], d['steering_titration']['placebo']['n']]", "expected": [0, 5]}]
```
Found by: c-unguarded. Verified: CONFIRMED.

## Refuted candidates

Seven candidates failed adversarial verification and are excluded: two barred re-files of Audit
1 (F-M10, F-M32); a would-be holdout-translation leak (the '72 txcorpus holdout translations'
claim did not reproduce; the real count is holdout-free); a 'no manifest guard' claim on
methods.html:518 that is in fact guarded; a false-dichotomy about the amendment-4 sign-off date
(a third benign explanation holds); a mis-dated deferral-note claim; and one duplicate. Full
verdicts are in the workflow journal.

## Coverage

Recomputed end-to-end from raw committed inputs: model_stats (penalty means, seed-7/boot-5000
bootstrap CIs, BH families, dedupe, the -3.36pp confirmatory), urgency tier application and
downgrade/upgrade counts, the jlens formation census and capture/hijack taxonomy, the
translation-scale joins and gap-closed clipping, and the steering pilot 11/12 and 2/3 counts.
Pre-registration: base Tier B registration and amendments 1-4, holdout hash derivation and its
exclusion across all nine published exporters. Claims: every hardcoded number on all eleven
pages plus share/404, ranked by drift likelihood, each with a proposed manifest entry.

## Addendum: completeness-critic pass and late finder findings

Four findings landed after the main report was committed (the completeness-critic pass plus
finder items surfaced on the final merge). IDs continue the sequence so the earlier IDs stay
stable. Revised totals: 10 high, 31 medium, 20 low (61 unique).

One further candidate was excluded, not filed: a high-severity `site:methods.html:524` item
(the static `52` fallback in `#lim-rt-n` vs `retrace_consistency.json` `pairs_retraced`) is
Audit 1 F-M32 verbatim; the commission bars re-filing Audit 1 findings, so it stays with its
queued Audit 1 entry.

#### F2-M30 · `engine:docs/prereg_divergence_log.md:16` · prereg-mismatch

The registered holdout endpoint date (2026-07-16, amendment 3) has passed without the endpoint run, and the owner-directed deferral is not recorded in the divergence log despite the standing instruction to log it; an unlogged divergence from a registered date.

Evidence:
```
Registered (prereg_amendment3_holdout.md, Owner decisions): "Endpoint date confirmed: 2026-07-16 (end of Tier B collection)." Standing instruction (ops/dashboard.json endpoint_protocol.deferral_note): "When 2026-07-16 passes without the instruction, record the deferral in docs/prereg_divergence_log.md (owner-directed, n..." and decisions_log 2026-07-15: "HOLDOUT stays sealed - owner reconfirmed 'keep waiting for my explicit unseal message'; the registered 2026-07-16 date passing without a run is an owner-directed deferral, to be recorded in docs/prereg_divergence_log.md". Current date 2026-07-17; the log's table (lines 8-15) ends with the 2026-07-14 phrase-keyed entry — no deferral row exists. No published number changes (the seal held; nothing was unsealed), so medium rather than high.
```
Proposed fix:
```diff
--- a/docs/prereg_divergence_log.md
+++ b/docs/prereg_divergence_log.md
@@ -15,6 +15,7 @@
 | 2026-07-14 | holdout exclusion made phrase-keyed | ... | ... | strengthens the seal; amendment 3 adopted 2026-07-14 (`docs/prereg_amendment3_holdout.md`) |
+| 2026-07-17 | holdout endpoint run deferred past the registered date | amendment 3: holdout analyzed once at the endpoint, date confirmed 2026-07-16 | 2026-07-16 passed with the holdout still sealed; unsealing waits for an explicit owner instruction (owner decisions 2026-07-14/15, `ops/dashboard.json` endpoint_protocol) | disclose in writeup; seal intact, amendment 3 analysis plan unchanged |
```
Verifier correction: The finding is accurate as stated. Only a proposal-level nit: the fix would be cleaner inserting the new row as the last table row (after line 15, before the blank line 16 and the closing paragraph at lines 17-18); the diff's `@@ -15,6 +15,7 @@` context count is loose for an 18-line file.

Found by: p-amendments. Verified: CONFIRMED.

#### F2-M31 · `site:data/retrace_consistency.json:4` · recompute-divergence

The published retrace-repeatability (instrument-determinism) bundle is a stale pre-July-15 snapshot that no lane recomputed: prob_spread_max=0.0, prob_spread_mean=0.0, spread_lists_identical_pairs=68 (=all 68), cmass_same_params_spread_max=0.0 do not reproduce from committed trace_out at engine HEAD, and the divergence is present on the exploration split alone, so the methods-page determinism claim ('every repeat reproduced identical probabilities', 'identical top-five lists') is falsified on the next regen.

Evidence:
```
Published patientwords/data/retrace_consistency.json (frontend @bbf5874): lines 3-8 pairs_retraced=68, prob_spread_max=0.0, prob_spread_mean=0.0, top_word_stable_pairs=68, spread_lists_identical_pairs=68, cmass_same_params_spread_max=0.0. Recompute at engine @9696df4 over committed trace_out (SAME script, no code change): 77 pairs; max prob spread 0.027; full spread lists identical only 74/77; cmass same-params max spread 0.0017. Restricting to the EXPLORATION split (holdout excluded via sha1(clinical_prompt)%10==0; 69 explore pairs / 8 holdout): explore-only max prob spread = 0.017 (>0), 2 explore pairs carry nonzero probability spread, 2 explore pairs have non-identical top-k spread lists, explore-only cmass same-params spread = 0.0017 (>0). So every zero in the published file is wrong at current committed inputs even before any holdout row is touched. Reproduction: cd /home/user/audit-wb/patientwords-engine && python3 scripts/retrace_consistency.py --trace-root trace_out --out /tmp/.../retrace_recompute.json (writes only --out; both worktree porcelains empty after run). Aggravators: (a) scripts/retrace_consistency.py emits NO generated_utc/digest (grep for generated|utc|timestamp|digest = NONE), so staleness is undetectable, same undetectability class as the confirmed paired_stats_rigor.json finding; (b) methods.html:223-224 hardcodes the interpretive words 'every repeat reproduced identical probabilities (largest spread <rt-spread>)' and 'identical top-five lists (<rt-lists> pairs)' while rt-spread/rt-lists/rt-n are fetched at runtime (methods.html:641-646) from this file, so the first regen renders 'identical top-five lists (74 pairs)' with prob spread 0.017 and pairs_retraced=77 — a live self-contradiction (74 != 77 under the word 'identical'); (c) validate_frontend_contract.py:291 guards only the TYPES of pairs_retraced/prob_spread_max, not that they are zero, so the regen passes contract. Distinct from the confirmed retrace_consistency.py holdout-leak finding (that flags 2 sealed phrases in the file); this is the separate, un-recomputed staleness of the published determinism numbers.
```
Proposed fix:
```diff
Two-part minimal fix. (1) De-hardcode the determinism prose in patientwords/methods.html so the qualitative word tracks the data instead of a stale snapshot:
--- a/methods.html
+++ b/methods.html
@@ -222,7 +222,7 @@
-      precision the files record (three decimals), every repeat reproduced identical
-      probabilities (largest spread <span id="rt-spread">—</span>), identical top-five
-      lists (<span id="rt-lists">—</span> pairs), and, under the same graph settings,
-      identical clinical-mass shares. The top word never changed
+      precision the files record (three decimals), the largest probability spread across
+      any repeat was <span id="rt-spread">—</span>; top-five lists matched exactly on
+      <span id="rt-lists">—</span> of <span id="rt-n2">—</span> pairs, and, under the same
+      graph settings, clinical-mass shares moved by at most <span id="rt-cmass">—</span>.
+      The top word never changed
       (<span id="rt-stable">—</span> pairs).
(and wire rt-n2/rt-cmass in the existing fetch block at methods.html:636-647 from d.pairs_retraced and d.cmass_same_params_spread_max). (2) Regenerate the site copy from current trace_out AND land the separately-confirmed holdout exclusion in scripts/retrace_consistency.py before republishing, and add a generated_utc stamp to the payload so staleness is detectable; add a value assertion (prob_spread_max plausibility / freshness) to validate_frontend_contract.py:291.
```
Severity: verifier downgraded high->medium (documented/self-disclosed staleness). Mechanism overlaps Audit 1 F-M26 (retrace_consistency.py has no --site auto-publish, so the site copy goes stale); the new, Audit-2-specific angle is claim correctness: every zero in the published bundle (prob_spread_max/mean=0.0, spread_lists_identical_pairs=68 of 68) is already wrong at current committed inputs on the exploration split alone (recompute: 77 pairs, max prob spread 0.027, 74/77 identical spread lists), so the methods-page determinism prose is falsified on the next regen. Fix the publish path per F-M26, then de-hardcode the determinism wording.

Verifier correction: Confirmed as a MEDIUM (not high) drift-prone-unguarded-claim finding. The published data/retrace_consistency.json is a stale snapshot (contains only drift_sentinel_20260713); recompute at engine HEAD over committed trace_out gives pairs_retraced=77, prob_spread_max=0.027, spread_lists_identical_pairs=74/77, cmass_same_params_spread_max=0.0017 (vs published 68/0.0/68 of 68/0.0), the movement coming entirely from newly landed drift_sentinel_20260714/15/16; documented/self-disclosed staleness, so no currently-published number is affirmatively false. The real defect: retrace_consistency.py/.json carry no generated_utc/digest (staleness undetectable; validate_frontend_contract.py:291 type-checks only and does not require a freshness field, unlike sibling specs), and methods.html:223-226 hardcodes the word 'identical' ('every repeat reproduced identical probabilities (largest spread <rt-spread>), identical top-five lists (<rt-lists> pairs)') while rt-spread/rt-lists are runtime-filled (methods.html:641,644), so the next regen renders 'identical top-five lists (74 of 77 pairs)'; a self-contradiction NOT covered by the existing July-15 carve-out at methods.html:228-232, which discloses the 0.027 probability movement and top-word stability but not top-five-list identity. Fix (de-hardcode the determinism prose + add a freshness stamp + a value/freshness assertion in the contract) is correct. The finder's aggravator (b) framing of a wholesale 'live self-contradiction' / 'falsified determinism claim' overstates it because the page already discloses the July-15 movement; the true residual contradiction is limited to the top-five-lists line and the 'identical probabilities (largest spread 0.027)' phrasing.

Found by: critic. Verified: CONFIRMED.

#### F2-L19 · `engine:scripts/export_jlens_depth.py:205` · doc-drift

Approval-timeline inconsistency: the live jlens_depth.json carrying the steering block was generated 2026-07-16T14:14:12Z, one day before both the owner approval date the exporter's own docstring records ('owner-approved for the router's steering column 2026-07-17') and Amendment 4's sign-off ('signed by the owner 2026-07-17'), which the shipped file and page caption cite.

Evidence:
```
Docstring: 'owner-approved for the router's steering column 2026-07-17' (export_jlens_depth.py:204-205); published file: '"generated_utc": "2026-07-16T14:14:12Z"' with the steering block present and its "_" note citing 'Amendment 4 registers the confirmatory version' (patientwords/data/jlens_depth.json:2 and :1568-1571; engine copy byte-identical); amendment status: 'signed by the owner 2026-07-17' (docs/prereg_amendment4_steering.md:3-4); page caption injected at technical/index.html:853: 'Amendment 4 (adopted July 17) registers the confirmatory version'. Either the docstring's approval date is wrong or the steering numbers were live on the site before the recorded approval.
```
Proposed fix:
```diff
Re-run the exporter after the fixes above so generated_utc postdates the recorded approval, and add one dated line to docs/prereg_divergence_log.md, e.g.:
+ 2026-07-17: jlens_depth.json steering block first published 2026-07-16 (export run), one day before the recorded owner approval (steering_split docstring) and Amendment 4 sign-off; content unchanged by the approval. Logged for timeline accuracy.
(If the approval actually occurred 2026-07-16, correct the docstring date at scripts/export_jlens_depth.py:205 instead.)
```
Verifier correction: Real low-severity timeline/doc-drift: the shipped jlens_depth.json records generated_utc 2026-07-16T14:14:12Z while the steering_split docstring (export_jlens_depth.py:205) and Amendment 4 (prereg_amendment4_steering.md:3-4) both record owner approval/sign-off as 2026-07-17, and the caption (technical/index.html:853) cites "adopted July 17". But git shows the steering data, the approval-referencing caption, and the column wiring all shipped in ONE frontend commit (cd6965e, 2026-07-16 14:24:39Z) whose message is titled "Owner decisions 2026-07-17", ~10 minutes after generation; so this is a UTC-timestamp (07-16) vs recorded-working-date (07-17) mismatch within a single approval session, NOT the steering numbers being live on the site a day before approval. The fix should reconcile the date label (either annotate that the 07-17 owner-decision session produced 07-16 UTC timestamps, or correct one of the two dates), and any divergence-log line must not repeat the "published one day before approval" overstatement.

Found by: r-steering. Verified: CONFIRMED.

#### F2-L20 · `engine:trace_out/batch_summary.part_01.json:1` · other

Five unprovenanced hosted batch-summary part files sit committed at the trace_out ROOT (part_01/03/05/07/09; 10 gemma-2-2b 2panel results, no pairs_file field) where the two-level glob trace_out/*/batch_summary*.json of every collector can never see them; harmless today but a quarantine trap: relocating them into any trace_out/<dir>/ would inject 10 unprovenanced rows into the urgency and stats pipelines as patient measurements.

Evidence:
```
Files: trace_out/batch_summary.part_{01,03,05,07,09}.json, each `{"mode": "2panel", "backend": "hosted", "graph_model": "gemma-2-2b", "source_set": "gemmascope-transcoder-16k", ...}` with 2 results (indices 1-10 total), full predictive spreads, no pairs_file. urgency_shift.py:160 globs `trace_out/*/batch_summary.part_*.json` — root files match no consumer glob repo-wide (also export_frontend_simulated.py, export_archive.py, paired_stats.py, drift_sentinel.py, translation_scale.py). Provenance search: their clinical-prompt sha1s match data/simulated/txcorpus_20260714T224455Z.json positions 3-12 by top_prompt, but their patient sides match NOTHING committed (pair-level sha1 search over every list-shaped JSON under data/ and every results[] under trace_out/: 0 hits), so the traced pair set exists in no landed batch file. No published number is affected (verified: the published urgency file reconstructs exactly without them). Risk is the repair path: any move into trace_out/<dir>/ makes them visible to all part-glob collectors with an arbitrary stem, and a txcorpus_-prefixed dir name would instead feed them to translation_scale.py's `txcorpus_*/batch_summary*.json` glob (line 43) — either way unprovenanced rows enter analysis.
```
Proposed fix:
```
Quarantine OUTSIDE trace_out/ (never into a subdirectory of it), e.g.:
  git mv trace_out/batch_summary.part_01.json trace_out/batch_summary.part_03.json \
         trace_out/batch_summary.part_05.json trace_out/batch_summary.part_07.json \
         trace_out/batch_summary.part_09.json ops/quarantine/rootparts_20260707/
plus an ops/quarantine/rootparts_20260707/README.md line: 'batch_summary parts committed to trace_out root by a run with an unset OUT_DIR; pair set matches no landed batch (clinical sides overlap txcorpus_20260714T224455Z top_prompts 3-12); excluded from all analysis; do not move into trace_out/'.
```
Verifier correction: Five unprovenanced hosted batch-summary part files (part_01/03/05/07/09; 10 gemma-2-2b 2panel results, indices 1-10, no pairs_file) sit committed at the trace_out ROOT. They are invisible to the two-level globs of urgency_shift.py:160, paired_stats.py:178, export_archive.py:75, drift_sentinel.py:33, and translation_scale.py:43, and today's published simulated_scenarios.json (14 batches) does not include a trap stamp, so no current number is wrong. But contrary to the finding, they ARE reachable by a live consumer: export_frontend_simulated.py model_dir() lines 120-121 fall back to `ENGINE/"trace_out"` (the root) for BASE_MODEL gemma-2-2b whenever `trace_out/pairs_{stamp}` is not a directory, and read_trace_dir() (line 130) then globs `batch_summary.part_*.json` in that root dir, matching all five files. Three already-landed pairs data files trigger this fallback because they have no bare gemma trace dir: pairs_20260706T172135Z, pairs_20260706T175614Z (no trace dir), and pairs_20260714T135150Z (gemma trace only in the __gemma-2-2b suffixed dir). Exporting any of them would silently read the 10 root rows as that batch's gemma base measurements and pair them with the batch's own data rows, injecting unprovenanced/mismatched scenarios into the published payload. The risk is therefore a live latent corruption of a future export of an already-landed batch (notably pairs_20260714T135150Z, landed 2026-07-17), not only the "relocating into a subdirectory" trap. Quarantining the five files OUTSIDE trace_out/ (per the proposed fix) is still the correct remedy, and separately the bare-gemma-dir absence for those stamps should be reconciled.

Found by: r-urgency. Verified: CONFIRMED.


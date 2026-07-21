---
name: holdout-seal-check
description: Verify no Tier B holdout phrase has leaked into any published artifact (site data, exports, briefs, decks, or this session's own output). Use when asked to "verify no holdout leakage", as the every-cycle integrity check, before/after any publish or export, or whenever a sealed phrase may have been quoted anywhere.
---

# Holdout seal check

Verify that no Tier B confirmatory-holdout phrase appears in any published or
exported artifact. Both repos are public: a single leaked phrase permanently
unseals a pre-registered confirmatory item, and the likeliest leak vector is an
LLM being helpful. That includes you — see the Never list before doing anything.

## The seal (background — do not re-derive, do not re-implement)

- **Amendment 1** (pre-registered 2026-07-09): every accepted Tier B pair is
  assigned by deterministic hash of its accepted clinical prompt —
  `sha1(top_prompt) mod 10 == 0` (~10%) is the holdout, analyzed exactly once
  after collection ends. Interim analyses use only the ~90% explore split.
- **Amendment 3** (in force 2026-07-14): phrase-keyed widening — a phrase
  flagged holdout anywhere is sealed everywhere. The seal keys on the accepted
  prompt, so alias/mitigation stems (`pairs_<STAMP>_tx*`), re-run stems
  (`repeatability_r*`), and trace-time probe extensions all seal under the same
  registered phrase even though those stems don't match the Tier B batch pattern.
- `scripts/tierb_split.py` is the **single implementation** of the rule
  (`is_holdout`, `holdout_phrases`, `stamp_rows`). Never reimplement the hash,
  never hand-classify a row.

## Step 1 — Precondition: run from the working branch

The sealed set derives from `tierb.start_utc` in `ops/dashboard.json`. Live ops
state lives on the **working branch** (currently
`claude/gemma-clinical-colloquial-interp-mavx04`; see the state note in
`ops/routines.md`), NOT main. A main checkout has a null `tierb.start_utc`, so
the sealed set computes **EMPTY** and the check is meaningless (audit
drift-register 1). From the engine repo root:

```bash
git rev-parse --abbrev-ref HEAD   # must be the ops-truth working branch, not main
python -c "from scripts.tierb_split import tierb_start_stamp; s=tierb_start_stamp(); print(s or 'NULL start_utc - wrong branch'); raise SystemExit(0 if s else 1)"
```

If that exits 1, check out the working branch (or pass
`--dashboard <path-to-working-branch-dashboard>`) before proceeding.

## Step 2 — Run the sweep

From the engine repo root, with the site as a sibling checkout:

```bash
python scripts/seal_check.py --site ../patientwords
# defaults: --dashboard ops/dashboard.json --simulated data/simulated --extra docs,ops
```

It recomputes the sealed registry via `tierb_split` and scans the site checkout
plus engine `docs/` and `ops/` (briefs, ledgers, decks under `ops/decks/`,
audits) for every sealed phrase, exact and whitespace/case-normalized. Scanned
suffixes: `.json .html .md .csv .txt .yml`; `modes/`, `.git`, `trace_out/`, and
`data/simulated/` are excluded (the registry's own sources are not leaks). If
you produced any artifact OUTSIDE those roots this session (a reviewer packet,
a scratch export, a release staging dir), add it: `--extra docs,ops,<dir>`.

## Step 3 — Act on the exit code

- **Exit 0 (CLEAN):** report the printed line (N sealed phrases, no hits across
  M roots). Done.
- **Exit 2 (CONFIG ERROR):** the sealed set computed empty — null
  `tierb.start_utc`, wrong branch, or wrong `--simulated` dir. This is NOT a
  clean result and must never be reported as one. Fix the config (Step 1) and
  re-run before doing anything else this cycle.
- **Exit 1 (LEAK):** breach. Go to Step 4 immediately.

## Step 4 — Breach response (2026-07-14 remediation precedent)

1. **STOP all publishing this cycle** — no site pushes, no exports, no digest
   data refresh until remediation is done.
2. **Purge:** redact every sealed phrase in-tree in the flagged files (replace
   with a redaction marker; never move or quote the text elsewhere). If the file
   is a generated data artifact, fix the source/exporter and **re-export** —
   never hand-patch a payload and leave the generator leaking.
3. **Re-run** `python scripts/seal_check.py --site ../patientwords` until exit 0.
4. **Document:** put the hit list — paths + `batch#index` labels + counts ONLY,
   exactly as the script prints them — in the digest headline and add a
   `decisions_pending` entry. Rewriting public git history to remove the leaked
   blobs is an OWNER decision; never do it yourself.

Precedent: the first live run (2026-07-21) caught 8 sealed phrases in the
2026-07-12 reviewer packet; redacted same day, in-tree, owner informed.

## Never (absolute)

- **Never quote, echo, paraphrase closely, translate, or partially reveal a
  holdout phrase in ANY output** — chat, digest, brief, deck, commit message,
  report, filename, this skill's own summary. Leaks are identified by
  path + `batch#index` + count only. The report must not become the leak.
- Never treat exit 2 (empty sealed set) as clean.
- Never reimplement or approximate the split — `scripts/tierb_split.py` only.
- Never run the check against a main checkout's dashboard.
- Never analyze holdout rows while checking the seal: no `paired_stats` on
  holdout rows, no endpoint results, no lifting a withholding gate. Unsealing
  happens only on an explicit owner instruction ("unseal"), never on a date.
- Never rewrite public git history, delete landed batches under
  `data/simulated/`, or edit site page text/HTML — data remediation only.
- Never write secrets or keys into any file; both repos are public.

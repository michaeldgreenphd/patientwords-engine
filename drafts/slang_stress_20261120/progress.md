# Slang & Everyday-Question Stress Pack — Progress Log

- **Branch**: `draft/slang-stress-20261120` (branched off `origin/main` at `d126f7e6`)
- **Status**: **COMPLETE (Exploratory Draft Pack — 320 / 320 stimuli assembled, multi-agent audited across G1–G6, engine-gate validated, awaiting owner, clinical, and patient-language review)**
- **Updated**: 2026-11-21T04:51Z

## Final Batch Matrix

| Batch | Lane | Items | Author | G1 (Validate) | G2 (Sources) | G3 (Facts) | G4 (Language) | G5 (Level) | G6 (Adversary) | Rev1 Edits |
|---|---|---:|---|---|---|---|---|---|---|---:|
| `nt_01` | Next-Token | 50 | `@nt-author-1` | PASS | 50/50 PASS | 50/50 PASS | 50/50 PASS | 50/50 PASS | 50/50 PASS | 8 |
| `nt_02` | Next-Token | 50 | `@nt-author-1` | PASS | 50/50 PASS | 50/50 PASS | 50/50 PASS | 50/50 PASS | 50/50 PASS | 7 |
| `nt_03` | Next-Token | 50 | `@nt-author-2` | PASS | 50/50 PASS | 50/50 PASS | 50/50 PASS | 50/50 PASS | 50/50 PASS | 16 |
| `nt_04` | Next-Token | 50 | `@nt-author-2` | PASS | 50/50 PASS | 50/50 PASS | 50/50 PASS | 50/50 PASS | 50/50 PASS | 18 |
| `adv_01` | Advice | 25 | `@adv-author` | PASS | 25/25 PASS | 25/25 PASS | 25/25 PASS | 25/25 PASS | 25/25 PASS | 5 |
| `adv_02` | Advice | 25 | `@adv-author` | PASS | 25/25 PASS | 25/25 PASS | 25/25 PASS | 25/25 PASS | 25/25 PASS | 5 |
| `adv_03` | Advice | 25 | `@adv-author` | PASS | 25/25 PASS | 25/25 PASS | 25/25 PASS | 25/25 PASS | 25/25 PASS | 3 |
| `adv_04` | Advice | 25 | `@adv-author` | PASS | 25/25 PASS | 25/25 PASS | 25/25 PASS | 25/25 PASS | 25/25 PASS | 1 |
| `petri_b01` | Petri | 5 | `@petri-author` | PASS | 5/5 PASS | 5/5 PASS | 5/5 PASS | 5/5 PASS | 5/5 PASS | 2 |
| `petri_b02` | Petri | 5 | `@petri-author` | PASS | 5/5 PASS | 5/5 PASS | 5/5 PASS | 5/5 PASS | 5/5 PASS | 1 |
| `petri_b03` | Petri | 5 | `@petri-author` | PASS | 5/5 PASS | 5/5 PASS | 5/5 PASS | 5/5 PASS | 5/5 PASS | 0 |
| `petri_b04` | Petri | 5 | `@petri-author` | PASS | 5/5 PASS | 5/5 PASS | 5/5 PASS | 5/5 PASS | 5/5 PASS | 1 |
| **Total** | **3 lanes** | **320** | **4 authors** | **12/12** | **320/320** | **320/320** | **320/320** | **320/320** | **320/320** | **67** |

## Assembly & Engine Gates

- `validate_pack.py --lane all --require-audits`: exit `0`, `0` errors, `0` warnings across `320` stimuli and `60` audit/source JSONs.
- `assemble_pack.py --lane all --require-audits --run-engine-gates`: byte-for-byte deterministic across 2 independent runs; all 3 native engine gates pass with `0` errors, `0` warnings, `0` Tier B holdout seal hits (`183` sealed phrases checked), `0` corpus duplicates, and `0` Round 9–12 exact prompt collisions.
- See `REPORT.md` for full statistics, SHA-256 digests, representative samples, and ready-to-run promotion commands.

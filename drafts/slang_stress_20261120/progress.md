# Slang & Everyday-Question Stress Pack — Progress Log

- **Branch**: `draft/slang-stress-20261120` (branched off `origin/main` at `d126f7e6`)
- **Status**: **FIXUP COMPLETE (`rev2`, post-Claude Code independent review) — 320 / 320 exploratory `outcome_informed` stimuli validated, deterministically re-assembled, and engine-gate verified; awaiting owner, clinician, and patient-language review**
- **Updated**: 2026-11-21T14:32Z

## Final Batch Matrix

| Batch | Lane | Items | Author | G1 (Validate) | G2 (Sources) | G3 (Facts) | G4 (Language) | G5 (Level) | G6 (Adversary) | Rev1 Edits | Post-Review Fixup |
|---|---|---:|---|---|---|---|---|---|---|---:|---:|
| `nt_01` | Next-Token | 50 | `@nt-author-1` | PASS | 50/50 PASS | 50/50 PASS | 50/50 PASS | 50/50 PASS | 50/50 PASS | 8 | 1 |
| `nt_02` | Next-Token | 50 | `@nt-author-1` | PASS | 50/50 PASS | 50/50 PASS | 50/50 PASS | 50/50 PASS | 50/50 PASS | 7 | 2 |
| `nt_03` | Next-Token | 50 | `@nt-author-2` | PASS | 50/50 PASS | 50/50 PASS | 50/50 PASS | 50/50 PASS | 50/50 PASS | 16 | 2 |
| `nt_04` | Next-Token | 50 | `@nt-author-2` | PASS | 50/50 PASS | 50/50 PASS | 50/50 PASS | 50/50 PASS | 50/50 PASS | 18 | 5 |
| `adv_01` | Advice | 25 | `@adv-author` | PASS | 25/25 PASS | 25/25 PASS | 25/25 PASS | 25/25 PASS | 25/25 PASS | 5 | 2 |
| `adv_02` | Advice | 25 | `@adv-author` | PASS | 25/25 PASS | 25/25 PASS | 25/25 PASS | 25/25 PASS | 25/25 PASS | 5 | 2 |
| `adv_03` | Advice | 25 | `@adv-author` | PASS | 25/25 PASS | 25/25 PASS | 25/25 PASS | 25/25 PASS | 25/25 PASS | 3 | 3 |
| `adv_04` | Advice | 25 | `@adv-author` | PASS | 25/25 PASS | 25/25 PASS | 25/25 PASS | 25/25 PASS | 25/25 PASS | 1 | 16 (incl. 12 relabels) |
| `petri_b01` | Petri | 5 | `@petri-author` | PASS | 5/5 PASS | 5/5 PASS | 5/5 PASS | 5/5 PASS | 5/5 PASS | 2 | 5 (all metadata + ss-03) |
| `petri_b02` | Petri | 5 | `@petri-author` | PASS | 5/5 PASS | 5/5 PASS | 5/5 PASS | 5/5 PASS | 5/5 PASS | 1 | 5 (all metadata) |
| `petri_b03` | Petri | 5 | `@petri-author` | PASS | 5/5 PASS | 5/5 PASS | 5/5 PASS | 5/5 PASS | 5/5 PASS | 0 | 5 (all metadata + ss-11, ss-14) |
| `petri_b04` | Petri | 5 | `@petri-author` | PASS | 5/5 PASS | 5/5 PASS | 5/5 PASS | 5/5 PASS | 5/5 PASS | 1 | 5 (all metadata + ss-17, ss-19) |
| **Total** | **3 lanes** | **320** | **4 authors** | **12/12** | **320/320** | **320/320** | **320/320** | **320/320** | **320/320** | **67** | **5 blockers + 25 item edits + 20 Petri metadata** |

## Assembly & Engine Gates (`rev2`)

- `validate_pack.py --lane all --require-audits`: exit `0`, `0` errors, `0` warnings across `320` stimuli and `60` audit/source JSONs (now also enforcing `claim_grade_eligible == false`, Q4 Petri hypotheses, and identical clinical text across Advice multi-variant ladders).
- `assemble_pack.py --lane all --require-audits --run-engine-gates`: byte-for-byte deterministic across 2 independent passes; all 3 native engine gates pass with `0` errors, `0` warnings, `0` Tier B holdout seal hits (`183` sealed phrases checked), and `0` corpus duplicates.
- See `REPORT.md` for full statistics, post-review fixup summary, SHA-256 digests, and verified promotion commands.

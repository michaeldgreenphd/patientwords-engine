# Seal incident 2026-07-21 — reviewer packet (resolved)

**What:** the first live run of `scripts/seal_check.py` (audit R-C) found 8
Amendment-1/3 sealed holdout phrases in
`docs/review/stimulus_review_packet_20260712.csv` (public working branch;
created 2026-07-12, predating the 2026-07-14 phrase-keyed seal widening; all
prior sweeps covered site data only). No phrase text was quoted anywhere in
detection, remediation, or this record.

**Remediation (same day):** the 8 rows' sentence fields redacted in-tree to
`[withheld - Tier B holdout seal, Amendment 1/3]`, sample_ids preserved;
re-check CLEAN (108 sealed phrases, 0 hits). Main was never exposed
(branch-only file).

**Owner decisions (2026-07-21 R2 deck):**
1. **Git history: LEAVE.** The redaction stands; public history is not
   rewritten. Rationale: the seal's scientific purpose (keeping sealed
   phrases out of interim analysis) is served by redaction + quarantine;
   force-rewriting a busy public branch mid-study is disproportionate. The
   phrases remain reachable in pre-2026-07-21 commits of the working branch.
2. **Ratings: QUARANTINE.** No ratings had been returned as of the decision
   (all rating columns blank). If ratings arrive, the 8 packet sample_ids in
   `docs/review/ratings_quarantine.json` are excluded from every interim
   analysis until the confirmatory pass.

**Standing defense:** `seal_check.py` runs every daily cycle (routine §2b)
and gates every publish (publish-site-data skill, step 8b).

# Activation-patching recovery grid — chunk A record (2026-08-10)

## Missed-harvest record (8h journal expiry, per harvest-resolve)

Both activation-patching journal entries for the B1 recovery grid expired from
the active set at ~2026-08-10T00:07Z (8h rule) while their runs were still
queued/running on congested GitHub runners — a queue-slowness artifact, not a
lost run. Recorded here because expired entries cannot be resolved:

- chunk A v2, fired 2026-08-09T16:06:52Z, run 31322929910 — **completed
  success 2026-08-10 ~03:45Z**; parts 01, 06, 11, 16, 21 all landed;
  per-pair coverage 1–25 verified complete.
- chunk B v2, fired 2026-08-09T16:06:54Z, run 31322931218 — released from the
  concurrency group at chunk A's completion; queued for runners as of 04:10Z.
  Parts 26, 31, 36, 41 expected. The patch-wake chain continues to watch it.

## Chunk A results summary (T2 multi-tier downgrade set, pairs 1–25)

Grid: resid_post patching, all 26 layers x prompt positions, normalized
recovery of the clinical target probability in the patient run.

- Pair classes: **16 real-gap** (language_penalty <= -0.01), 8 no-gap flip
  pairs (|penalty| < 0.01 — recovery metric undefined; T2 #4 7 10 12 13 15 18
  21), 1 inverted (#17, patient side higher; metric inapplicable).
- **All 16 real-gap pairs reach full recovery (max >= 1.0).** 12 of the 16
  are owner-validated seeds.
- **Locus:** earliest >=90% recovery at median layer 20.5 (range 6–25),
  overwhelmingly at the final syntactic-slot token (' a', ' my', ' the').
  13/16 pairs recover only late (layers 18–25); best recovery achievable in
  layers <= 12 has median 0.235 across real-gap pairs.
- **Early-recovery exceptions:** T2 #6 (layer 6), #23 (layer 7, full 1.31 at
  a mid-layer pronoun position), #24 (layer 13) — candidate cases where the
  deficit localizes earlier; worth individual inspection before featuring.

Consistent with the j-lens depth census (concept forms late; divergence
decided at the last layers/position): the informal phrasing's deficit is not
fixable by mid-network patching at the swapped words; it persists to where
the answer is assembled.

## Full 44-pair set — final record (2026-08-10, chunk B terminal)

Chunk B v2 (run 31322931218) is terminal: overall conclusion "cancelled"
because ONE matrix job hit the workflow's job timeout — patch (35), job
93343298689-series id 93345053492, cancelled at 4h47m into its measure step
(06:38–11:25Z) with no part written. The other three jobs succeeded:
part_26 (03:18–07:07Z), part_31 (03:18–06:24Z), part_41 (07:07–09:59Z).

**Coverage: 39 of 44 pairs measured; T2 pairs 36–40 LOST to the timeout.**
Refire to complete = one chunk (offsets 35, limit 5) — the GitHub concurrency
group is now empty and the lane journal is clear, but the identical job
already timed out once; if refired, consider two smaller chunks (limit 3 + 2)
to stay under the job ceiling. Held for the owner's word per the
report-only rule for this lane.

Consolidated numbers over the 39 measured pairs:

- Classes: **26 real-gap** (21 of them owner-validated), 10 no-gap flip
  pairs (recovery metric undefined), 3 inverted (patient side higher).
- **26 of 26 real-gap pairs reach full recovery (max >= 1.0).** Mean |gap|
  0.138 in target probability.
- Locus: earliest >=90% recovery at **median layer 20 of 26** (range 6–25);
  23/26 pairs recover only at layer >= 15, at the final syntactic-slot token.
  Best recovery achievable in layers <= 12: median 0.25.
- Early-locus exceptions (all chunk A): T2 #6 (L6), #23 (L7), #24 (L13).

Claim supported: on the multi-tier downgrade set, the informal phrasing's
deficit persists through the middle of the network and is causally
overridable only where the answer is assembled (late layers, final position),
with three localized exceptions. The 8h-expiry missed-harvest record for both
lane entries stands as documented above.

## 44/44 complete (2026-08-11, owner-approved timeout refires)

Refires landed: run 31524608702 (pairs 36-38, part_36) and run 31524611794
(pairs 39-40, part_39), both GitHub-confirmed terminal success; both journal
entries resolved. T2 coverage is COMPLETE at 44/44.

Final consolidated numbers over all 44 pairs:

- Classes: **29 real-gap** (24 owner-validated), 11 no-gap flip pairs
  (recovery metric undefined), 4 inverted (#17 #29 #31 #37).
- **29 of 29 real-gap pairs reach full recovery (max >= 1.0)** — a perfect
  record across the grid. Recovered refire pairs: #36 (1.0 @ L25), #39
  (1.0 @ L23), #40 (1.0 @ L23), all at the final slot token.
- Locus unchanged: earliest >=90% recovery at median layer 20 of 26;
  26/29 pairs recover only at layer >= 15 at the final syntactic-slot token;
  early-locus exceptions remain #6 (L6), #23 (L7), #24 (L13).

The B1 recovery-grid experiment is closed. Successor experiment approved by
the owner 2026-08-11: the lost-late (lens-suppressed) class grid — pairs
where the clinical concept survives to ~L24 then drops, selected
holdout-filtered with real behavioral gaps; stimulus set committed separately.

## Lost-late grid (2026-08-12, prediction test)

Run 31546777739 terminal "cancelled": 4 of 5 jobs succeeded (parts 01/06/16/21
= pairs 1-10, 16-22); the offsets-10 job (pairs 11-15) hit the job timeout —
same failure mode as T2 patch(35). Journal entry expired 07:33 while the run
sat runner-starved (missed-harvest record per harvest-resolve); refire fired
2026-08-12 as two chunks (offsets 10 limit 3, offsets 13 limit 2), the
owner-approved split remedy.

Results over the 17 measured pairs of the lens-suppressed set:

- Classes: **13 real-gap**, 3 no-gap (#3 #8 #22), 0 inverted, 1 metric
  anomaly (#16: near-degenerate gap -0.019 inflates normalized recovery to
  4.15 — excluded, not an early-recovery finding).
- **13 of 13 real-gap pairs reach full recovery (max >= 1.0).**
- **PREDICTION CONFIRMED — late-only recovery, sharper than B1:** earliest
  >=90% at median layer 21 (B1: 20); 5/13 recover ONLY at the final layer 25;
  zero early recoveries (B1 had three). Best recovery in layers <= 12:
  median 0.18 (B1: 0.25).

The lens-suppressed class is causally the latest-deciding class measured:
concepts the lens sees surviving to ~L24 are restorable only at the very end
of the network — the two instruments agree pair-class by pair-class.

## Lost-late grid — FINAL, 22/22 (2026-08-12)

Refires complete: run 31604273031 (pairs 11-13) success, run 31604277972
(pairs 14-15) success; both entries resolved (the 14-15 entry ~20 min before
its 8h expiry). Full coverage 22/22.

Final numbers: **16 real-gap pairs, 16/16 full recovery (max >= 1.0)**;
5 no-gap (#3 #8 #14 #15 #22); 0 inverted; 1 metric anomaly (#16, excluded).
Earliest >=90% recovery: L15-L25, median L21; 5 pairs recover ONLY at L25;
**zero early recoveries anywhere in the set**. Best recovery in layers <= 12:
median 0.18.

The prediction stands at full coverage: the lens-suppressed class is the
latest-deciding class measured, with recovery confined to the final layers
at the final slot token — sharper than the B1 baseline (median L20, three
early exceptions). Cross-instrument closure: lens classification and causal
patching agree pair-class by pair-class; the set also carries full
attribution graphs (traced 22/22) and behavior rows.

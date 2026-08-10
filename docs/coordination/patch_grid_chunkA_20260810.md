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

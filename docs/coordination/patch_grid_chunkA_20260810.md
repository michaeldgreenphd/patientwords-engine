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

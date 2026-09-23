# Disclosure note template — accompanies every reproduction pack send

Fill the brackets; keep the whole note factual and short. Packs go to the
affected vendor BEFORE any public per-model comparison is published (binding
sequencing rule, pre-registration Amendment 3). Record the send with:
`python scripts/advice_eval.py repro-pack --record-sent <PACK_VERSION> --sent-to "<role/channel>"`
— role or channel references only, never private contact details (the log is
public).

Fill the request-id clause from the pack's own README, which counts the
records that carry one: request ids exist only where the provider's response
headers carried one (capture began 2026-07-23; calls routed through
OpenRouter carry none). Never promise request ids the pack does not hold.

Where bracketed versions are given, keep the one that is true for this send
and delete the others (pre-registration Deviation D2 says which applies):

- "Not yet public": the page has never shown per-model results for the model.
- "Already public": the LLM-responses page showed per-model results for the
  model before the pack was sent and still shows them.
- "Formerly public": the page showed them and has since withheld them, as it
  has withheld every Gemini arm since 2026-08-08 (google's packs). Do not use
  "Already public" for such a model: it says the results are still shown.

---

Subject: Measurement disclosure — [vendor] model responses in a public
phrasing study (pack [PACK_VERSION])

We run a public study of how consumer AI assistants respond when the same
clinical situation is phrased in clinical terms versus everyday patient
language. Your model [model id] is one of [N] models measured.
[Not yet public: Before we publish any comparison naming your model, this
pack gives your team]
[Already public: Our public results page has shown per-model results for
your model since [date]. Our pre-registration, amended on 2026-07-23,
requires this pack to reach you before per-model results are published; the
page kept adding them without it, and we record that deviation publicly
([link to Deviation D2]). This pack gives your team]
[Formerly public: Our public results page showed per-model results for your
model from [first date] to [last date], and has withheld them since then
([the reason, as the page states it]). Our pre-registration, amended on
2026-07-23, requires this pack to reach you before per-model results are
published; the page showed them without it, and we record that deviation
publicly ([link to Deviation D2]). This pack gives your team]
every record involving it: full requests, raw responses, the served build
strings, [request ids for all [M] records | request ids for [K] of [M]
records | no request ids: these calls carry none], every judge's coding of
those responses (a primary judge, and where present a second judge used
only to measure inter-judge agreement), our coding rubric, and the exact
commands that verify the records are unaltered and regenerate the analysis
from public files.

Findings at this stage are provisional (draft rubric, machine coding,
pilot n) and the pack's README states every caveat we hold ourselves to. If
your team finds any record, coding, or characterization you dispute,
[Not yet public: we want to know before publication]
[Already public or Formerly public: we want to know]: [issue link].

No response is required for us to proceed, but corrections will be
incorporated and acknowledged.

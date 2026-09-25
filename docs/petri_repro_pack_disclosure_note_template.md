# Disclosure note template — accompanies every Petri reproduction pack send

The Petri lane's counterpart of `docs/repro_pack_disclosure_note_template.md`.
`python -m scripts.petri_audit.cli repro-pack` renders the note into every
pack as `DISCLOSURE_NOTE.md`: it fills the braces from the pack and keeps the
one opening and dispute clause that `--publication-state` names. Only the
text between the `BEGIN` and `END` markers is used; this header is not.

Packs go to the affected vendor BEFORE any public per-model claim is
published (binding sequencing rule, `docs/preregistration_advice.md`,
"Vendor reproduction packs and sequencing"; its scope ruling of 2026-09-23
and decision 16 of `docs/petri_wave2_design.md` bind the Multi-turn page).
Record the send with
`python -m scripts.petri_audit.cli repro-pack --record-sent <PACK_VERSION> --sent-to "<role/channel>"`
on the day it is sent — role or channel references only, never private
contact details (the log is public).

Which publication state is true (pre-registration Deviation D2 says why it
matters):

- `not_yet_public`: no page has shown per-model results from this arm for the
  model. True of the Multi-turn page until it is published.
- `already_public`: a page showed them before the pack was sent and still
  shows them.
- `formerly_public`: a page showed them and has since withheld them.

The last two state dates, a link and a reason the records do not hold, so
they are build inputs: `--public-since` and `--deviation-link` for both,
`--public-until` and `--withheld-reason` (the reason as the page states it)
for `formerly_public`. The builder refuses a state without its inputs, or with
inputs it does not use, and refuses a note that still holds a bracketed field.
The inputs enter the pack's manifest, so its version and `SHA256SUMS` cover
the note as sent: never edit `DISCLOSURE_NOTE.md` after the build (its
checksum would fail, and two notes would share one version); rebuild with the
corrected inputs instead. The request-id clause is counted from the pack's own
records: never promise request ids the pack does not hold.

<!-- BEGIN note -->
Subject: Measurement disclosure — {vendor} model in a public multi-turn
phrasing study (pack {pack_version})

We run a public study of how AI assistants respond when the same situation is
put in clinical terms, in careful lay terms and in everyday patient language.
Its multi-turn arm holds scripted ten-turn conversations with one model,
`{target_model}`, and grades each reply with the same model acting as a
grader.
{opening}
every record of the {run_count} runs involving it: the run manifests, the
sanitised harness logs and transcripts of all {conversations} conversations,
every judgment attached to a reply ({judgments} rows), the rule outcomes and
cost records, the rubric and judge prompts, the pre-registered analysis's
output, and the exact commands that verify the records are unaltered and
regenerate the analysis from public files. {request_id_clause}

The pack's README states the claims this arm's results permit, word for word
as the analysis plan fixed them before the final data, and every caveat we
hold ourselves to. If your team finds any record, judgment, or
characterization you dispute, {dispute}: https://github.com/michaeldgreenphd/patientwords-engine/issues.

No response is required for us to proceed, but corrections will be
incorporated and acknowledged.
<!-- END note -->

<!-- BEGIN opening:not_yet_public -->
Nothing from this arm naming your model is public yet. Before we publish any
result naming it, this pack gives your team
<!-- END opening:not_yet_public -->

<!-- BEGIN opening:already_public -->
Our public results page has shown this arm's results for your model since
{public_since}. The study's pre-registration requires this pack to reach you
before per-model results are published; the page showed them without it, and
we record that deviation publicly ({deviation_link}). This pack gives your
team
<!-- END opening:already_public -->

<!-- BEGIN opening:formerly_public -->
Our public results page showed this arm's results for your model from
{public_since} to {public_until}, and has withheld them since then
({withheld_reason}). The study's pre-registration requires this pack to reach
you before per-model results are published; the page showed them without it,
and we record that deviation publicly ({deviation_link}). This pack gives
your team
<!-- END opening:formerly_public -->

<!-- BEGIN dispute:not_yet_public -->
we want to know before publication
<!-- END dispute:not_yet_public -->

<!-- BEGIN dispute:already_public -->
we want to know
<!-- END dispute:already_public -->

<!-- BEGIN dispute:formerly_public -->
we want to know
<!-- END dispute:formerly_public -->

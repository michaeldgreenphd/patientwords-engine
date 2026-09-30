# Methods endnote draft — study timing (P2, for the owner's voice)

DRAFT ONLY — the owner rewrites this before any of it reaches a page. Every
number below comes from `data/timeline.json`, which is generated entirely
from committed artifacts (batch cost sidecars, git commit dates, the Tier B
start stamp). Nothing is typed in by hand; the nightly cycle keeps it fresh.

Suggested one-line stamp (methods masthead or endnote):

> Measured 6–{end date} July 2026 · {accepted_pairs} generated pairs ·
> ${generation_usd} of API credits · tracing and inference $0 on public CI ·
> Tier B pre-registered before its first batch (verifiable in git history).

Longer form, if wanted:

> The dataset behind these pages was collected in days, not months: Tier A
> generation and tracing ran 6–9 July 2026; the Tier B scale run was
> pre-registered on 9 July (committed while its start stamp was still null)
> and began collecting on 10 July. Generation cost ${generation_usd} in
> total across {generation_batches} batches; every trace and every CPU
> measurement ran free on public GitHub Actions. Each batch's timestamp,
> generator model, and exact cost are in the repository's cost sidecars —
> the timeline strip on the Simulated Scenarios page is drawn from them at
> load time.

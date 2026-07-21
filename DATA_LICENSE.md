# Data license

The code in this repository is licensed under the MIT License (see `LICENSE`).
This file states the terms for the **data** the project authors and publishes,
which the MIT license does not cover.

## What is covered

The following project-authored datasets and measurement outputs are licensed
under [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/):

- `data/simulated/` — the generated stress-test phrase-pair batches and their
  cost sidecars (append-only archives).
- `data/measured/` — the hand-built phrase dataset measured from real patient
  language.
- The measurement outputs this engine commits (`trace_out/` batch summaries,
  lens readout summaries) and the published data payloads in the companion
  site repository ([patientwords](https://github.com/michaeldgreenphd/patientwords),
  `data/*.json` and the collaborator archive CSV).

Attribution: cite the repository as described in `CITATION.cff` (Michael D.
Green, *patientwords-engine*), or link to
<https://michaeldgreenphd.github.io/patientwords/>.

## What is not covered

- Third-party content fetched from external services remains under its own
  terms and is **not** relicensed here. In particular, feature auto-interp
  descriptions and attribution graphs returned by
  [Neuronpedia](https://neuronpedia.org)'s APIs (which appear inside tagged
  trace outputs) are Neuronpedia content.
- Model weights and tokenizers referenced by the pipeline (gemma-2-2b, Gemma
  Scope transcoders, and the other measured models) are distributed by their
  publishers under their own licenses.

## Notes

- Phrase pairs still under the pre-registered Tier B holdout seal are not yet
  published; this license applies to data as and when it is published in these
  repositories.
- A versioned, DOI-carrying data release is planned at the Tier B freeze; until
  then, cite the repository state by commit hash.

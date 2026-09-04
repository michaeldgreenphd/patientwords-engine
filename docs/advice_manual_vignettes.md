# Writing your own advice-arm vignettes (manual source)

The `--source manual` path turns a JSON file you write into a stamped stimuli
file, exactly like the payload-derived sets: append-only under `data/advice/`,
elicited with the same arms/K/ceilings, joined into the same analysis. This is
the arm for **complete, natural consumer messages** — situations that are
ambiguous in content rather than cut off mid-sentence.

## What to write

Each vignette is one situation phrased twice:

- `clinical`: how a clinician (or a patient repeating clinician language)
  would phrase it.
- `patient`: how a person actually types it into a chat box.

Guidelines (the pair texts are the experiment — you own them):

- **Complete thoughts.** Ambiguity is welcome; truncation is not — the
  truncated register effect is measured by the payload sets.
- **One swap axis.** Keep the two versions as close to identical as natural,
  differing in register: same situation, same facts, different words.
- Typos, missing punctuation, run-ons in the patient version are fine and are
  kept verbatim (they are stress stimuli — never corrected).
- No real patient details, no PHI, nothing resembling the Tier B holdout
  phrasings. Both repos are public.
- The ask suffix `What should I do?` is appended to BOTH sides automatically.
  If your text already ends in its own question, say so and the build runs
  with `--ask-suffix ""` instead.

## Fields

Required: `id` (short slug, unique), `clinical`, `patient`.
Optional:

- `notes` — anything you want recorded with the item.
- `reference` — the clinician-adjudicated correct care tier (A2 scoring):
  `{"tier": "self_care" | "routine" | "urgent" | "emergency", "source": ...,
  "adjudicated_by": ..., "date": ...}`. Draft tier vocabulary from
  `data/advice_rubric.draft.json`; this can be added later with the domain
  reviewer — items without it still run, they just aren't accuracy-scored.
- `situation_id` — groups items that describe the same underlying situation
  (B2-B4 designs: paraphrase sets, misattribution, messiness ladders).
- `variant` — labels this item's role within its `situation_id` group.

Template with two placeholder entries (replace both; the placeholder wording
is deliberately non-medical): `docs/advice_manual_vignettes.template.json`.

## What happens when you hand it back

```bash
python scripts/advice_eval.py build-stimuli --source manual \
  --manual-in <your file> --out-dir data/advice
```

The build validates (both sides present, not identical, unique ids, reference
shape), assembles the messages, and writes `data/advice/stimuli_<stamp>.json`.
It is reviewed by eye, committed, and fired like any other set. Manual sets
are supplementary to the registered pilot endpoints unless the
pre-registration is amended before their first fire.

"""Does the register of a question change WHERE the reply sends the person?

The published study measures urgency: does patient phrasing get less urgent advice. Over the
landed advice corpus the urgency answer is no — six of seven models' rank-difference intervals
include zero (data/advice/analysis_stimuli_20260807T153329Z.json). This script asks a different
question of the same corpus: does the reply name a *specialist service* at a different rate.

It is a naming rate, not a referral rate. The vocabulary file's method_note states the
limitation and it is repeated in the emitted bundle: a reply that rules a specialist out still
counts as naming one. The judged dimension `referral_specificity` is the instrument that turns
on recommendation; this is the cheap observational proxy over data that already exists.

Two guards matter for reading the output. The tier-identical stratum re-runs the same estimate
over only those cells where both arms received the same modal tier, so a difference there
cannot be a restatement of an urgency difference. And every row that cannot be measured is
counted and reported by reason rather than dropped (AGENTS.md: no silent failures) — a coverage
figure below 1.0 with no stated reason is a defect, not a result.

Judgments are read under one rubric. The advice archive keys a judgment by response, rubric
digest and judge model, so the same judge can re-judge every response after a rubric change;
pooling digests would mix classifications made under different rubrics and count a re-judged
response twice. The judge of record's rows must therefore carry a single `rubric_sha256`, or
one is chosen with --rubric-digest, and the tier order is read from the rubric file whose
canonical digest equals it (--rubric), never assumed.

Usage:
    python scripts/referral_destination.py [--advice-dir data/advice] [--boot 2000] [--seed 7]
        [--judge claude-haiku-4-5] [--rubric data/advice_rubric.draft.json]
        [--rubric-digest <12 or more hex characters>] [--out referral_destination.json]
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import random
from collections import Counter, defaultdict
from fractions import Fraction
from typing import Any, Iterable

try:  # imported as scripts.referral_destination (tests) vs run as a file from the repo root
    from scripts.advice_eval import canonical_json, sha256_text
except ImportError:
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from advice_eval import canonical_json, sha256_text

VOCAB_PATH = "data/referral_destination_vocab.draft.json"
RUBRIC_PATH = "data/advice_rubric.draft.json"
MIN_DIGEST_PREFIX = 12
PATIENT_ARMS = ("patient", "colloquial")
CLINICAL_ARM = "clinical"


def load_vocab(path: str = VOCAB_PATH) -> dict[str, Any]:
    """The term lists, as data. Refuses a file missing either list rather than scoring zero."""
    with open(path, encoding="utf-8") as handle:
        vocab = json.load(handle)
    for key in ("specialist_services", "emergency_services"):
        terms = vocab.get(key)
        if not isinstance(terms, list) or not terms:
            raise ValueError(f"{path}: '{key}' must be a non-empty list; refusing to score an empty vocabulary")
    return vocab


def select_rubric_digest(judgments: list[dict[str, Any]], judge: str, declared: str | None = None) -> str:
    """The one rubric digest whose judgments are analysed.

    With nothing declared, the judge of record's rows must all carry the same digest; two or more
    is refused, naming each with its row count, rather than pooled. A declared digest may be a
    prefix of at least MIN_DIGEST_PREFIX hex characters and must match exactly one digest present."""
    present = Counter(row["rubric_sha256"] for row in judgments
                      if row.get("judge_model") == judge and row.get("rubric_sha256"))
    listing = ", ".join(f"{digest[:12]} ({n} rows)" for digest, n in sorted(present.items()))
    if not present:
        raise ValueError(f"no row from judge {judge!r} carries a rubric_sha256; refusing to pool rows of unknown rubric")
    if declared is not None:
        if len(declared) < MIN_DIGEST_PREFIX:
            raise ValueError(f"--rubric-digest needs at least {MIN_DIGEST_PREFIX} hex characters, got {declared!r}")
        matches = [digest for digest in present if digest.startswith(declared)]
        if len(matches) != 1:
            raise ValueError(f"--rubric-digest {declared!r} matches {len(matches)} of the digests judge {judge!r} "
                             f"used: {listing}")
        return matches[0]
    if len(present) > 1:
        raise ValueError(f"judge {judge!r} judged under {len(present)} rubric digests ({listing}); pooling them "
                         "mixes classifications made under different rubrics and counts a re-judged response "
                         "twice. Pass --rubric-digest to choose one.")
    return next(iter(present))


def load_rubric_tiers(path: str, digest: str) -> tuple[list[str], Any]:
    """(tier ids least to most urgent, rubric version) from the rubric the judge was shown.

    The file's canonical digest (advice_eval's canonical_json, the one written into every
    judgment) must equal the selected digest; another rubric's tier order is refused, not used."""
    with open(path, encoding="utf-8") as handle:
        rubric = json.load(handle)
    found = sha256_text(canonical_json(rubric))
    if found != digest:
        raise ValueError(f"{path} has canonical digest {found[:12]}, but the judgments analysed were made under "
                         f"{digest[:12]}; the tier order must come from that rubric. Pass --rubric with its file.")
    tiers = [tier.get("id") if isinstance(tier, dict) else None for tier in rubric.get("tiers") or []]
    if not tiers or not all(isinstance(t, str) and t for t in tiers) or len(set(tiers)) != len(tiers):
        raise ValueError(f"{path}: 'tiers' must be a non-empty list of distinct ids; refusing to rank by it")
    return tiers, rubric.get("version")


def _read_jsonl(paths: Iterable[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(paths):
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    records.append(json.loads(line))
    return records


def load_corpus(advice_dir: str) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Responses indexed by their own sha256, and every judgment row. Both families are
    append-only archives, so a stem glob is the documented way to read them."""
    responses = _read_jsonl(glob.glob(os.path.join(advice_dir, "responses_stimuli_*.jsonl")))
    judgments = _read_jsonl(glob.glob(os.path.join(advice_dir, "judgments_stimuli_*.jsonl")))
    by_sha = {r["response_sha256"]: r for r in responses if r.get("response_sha256")}
    return by_sha, judgments


def names_any(text: str, terms: Iterable[str]) -> bool:
    lowered = (text or "").lower()
    return any(term in lowered for term in terms)


def build_cells(
    by_sha: dict[str, dict[str, Any]],
    judgments: list[dict[str, Any]],
    vocab: dict[str, Any],
    judge: str,
    rubric_digest: str,
    tier_rank: dict[str, int],
) -> tuple[dict[tuple[str, str], dict[str, list[tuple[int, bool, bool]]]], Counter]:
    """One entry per (stimulus, model, arm), each holding the per-sample triples
    (tier rank, names a specialist, names an emergency service).

    Every judgment row the primary judge produced under the selected rubric digest is either
    measured or counted in `skipped` under a named reason. Nothing is dropped silently.
    """
    cells: dict[tuple[str, str], dict[str, list[tuple[int, bool, bool]]]] = defaultdict(lambda: defaultdict(list))
    skipped: Counter = Counter()
    specialist = vocab["specialist_services"]
    emergency = vocab["emergency_services"]

    for row in judgments:
        if row.get("judge_model") != judge:
            # Another judge's row is out of scope, not a measurement failure. Counting it as a
            # skip would drag the coverage rate down and hide a real extraction problem behind
            # it, so it is reported on its own line instead.
            skipped["_other_judge_out_of_scope"] += 1
            continue
        if not row.get("rubric_sha256"):
            skipped["judgment_missing_rubric_sha256"] += 1
            continue
        if row["rubric_sha256"] != rubric_digest:
            # Same judge, another rubric: a different instrument, reported on its own line.
            skipped["_other_rubric_digest_out_of_scope"] += 1
            continue
        tier = row.get("tier")
        if tier not in tier_rank:
            skipped["tier_absent_or_unrecognised"] += 1
            continue
        sha = row.get("response_sha256")
        response = by_sha.get(sha) if sha else None
        if response is None:
            skipped["no_response_record_for_this_judgment"] += 1
            continue
        text = response.get("response_text")
        if text is None:
            skipped["response_record_has_no_response_text_field"] += 1
            continue
        if not str(text).strip():
            skipped["response_text_empty"] += 1
            continue
        for field in ("stimulus_id", "model", "arm"):
            if not row.get(field):
                skipped[f"judgment_missing_{field}"] += 1
                break
        else:
            cells[(row["stimulus_id"], row["model"])][row["arm"]].append(
                (tier_rank[tier], names_any(text, specialist), names_any(text, emergency))
            )
    return cells, skipped


def _mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values)


def modal_rank(ranks: list[int]) -> int:
    """The registered per-cell tier summary: the modal tier, a tie between modes broken toward
    the most urgent (docs/preregistration_advice.md Amendment 1; `advice_eval._modal_tier`,
    which a test holds this equal to). A rounded mean rank is not that summary: two arms can
    share a rounded mean while their modal tiers differ."""
    counts = Counter(ranks)
    best = max(counts.values())
    return max(rank for rank, count in counts.items() if count == best)


def _exact_mean(values: Iterable[int]) -> Fraction:
    values = list(values)
    return Fraction(sum(values), len(values))


def _sign(value: Fraction) -> int:
    return (value > 0) - (value < 0)


def sign_agreement(model_means: dict[str, Fraction], pooled_total: Fraction) -> dict[str, Any]:
    """How many models share the pooled estimate's direction, with ties kept apart.

    A model whose mean is exactly zero is `models_tied_at_zero`, never an agreeing model: the
    earlier Boolean test counted zero as agreeing with any non-negative estimate (Codex, PR #29).
    When the pooled estimate is itself exactly zero there is no direction to agree with, and the
    agreeing and opposing counts are null rather than zero."""
    direction = _sign(pooled_total)
    signs = [_sign(m) for m in model_means.values()]
    tied = signs.count(0)
    return {
        "models_agreeing_in_sign": signs.count(direction) if direction else None,
        "models_opposing_sign": signs.count(-direction) if direction else None,
        "models_tied_at_zero": tied,
        "models_by_sign": {"negative": signs.count(-1), "zero": tied, "positive": signs.count(1)},
    }


def cluster_bootstrap_ci(
    per_cluster: dict[str, list[float]], rng: random.Random, n_boot: int
) -> tuple[float, float, float]:
    """Percentile CI over clusters resampled with replacement. Clustering is on the stimulus:
    the same stimulus appears once per model, so treating those as independent would understate
    the interval. Returns (point estimate, lo, hi)."""
    flat = [v for values in per_cluster.values() for v in values]
    point = _mean(flat)
    keys = list(per_cluster)
    draws: list[float] = []
    for _ in range(n_boot):
        picked = [v for key in (rng.choice(keys) for _ in keys) for v in per_cluster[key]]
        draws.append(_mean(picked))
    draws.sort()
    lo = draws[int(0.025 * n_boot)]
    hi = draws[min(int(0.975 * n_boot), n_boot - 1)]
    return point, lo, hi


def estimate(
    cells: dict[tuple[str, str], dict[str, list[tuple[int, bool, bool]]]],
    index: int,
    rng: random.Random,
    n_boot: int,
    tier_identical_only: bool,
) -> dict[str, Any]:
    """Patient-minus-clinical difference on one binary readout, clustered on stimulus.

    `index` selects the triple member: 1 specialist, 2 emergency. A cell contributes only when
    both arms are present; `tier_identical_only` further restricts to cells whose two arms
    carry the same modal tier (`modal_rank`), so the readout cannot be a restatement of the tier.

    Per-model signs are counted on exact rational means, not floats: a model whose cells cancel
    exactly can come out at -5.6e-18 in floating point and would otherwise be counted as
    negative. A model at exactly zero agrees with neither direction and is reported as tied.
    """
    per_stimulus: dict[str, list[float]] = defaultdict(list)
    per_model: dict[str, list[Fraction]] = defaultdict(list)
    used = 0
    for (stimulus_id, model), arms in cells.items():
        patient_arm = next((a for a in PATIENT_ARMS if a in arms), None)
        if patient_arm is None or CLINICAL_ARM not in arms:
            continue
        patient, clinical = arms[patient_arm], arms[CLINICAL_ARM]
        if tier_identical_only and modal_rank([t[0] for t in patient]) != modal_rank([t[0] for t in clinical]):
            continue
        difference = _mean(t[index] for t in patient) - _mean(t[index] for t in clinical)
        per_stimulus[stimulus_id].append(difference)
        per_model[model].append(_exact_mean(t[index] for t in patient) - _exact_mean(t[index] for t in clinical))
        used += 1
    if used == 0:
        raise ValueError("no comparable cells; refusing to report an estimate over an empty set")
    point, lo, hi = cluster_bootstrap_ci(per_stimulus, rng, n_boot)
    model_means = {m: sum(v) / len(v) for m, v in per_model.items()}
    signs = sign_agreement(model_means, sum(d for v in per_model.values() for d in v))
    return {
        "cells": used,
        "stimuli": len(per_stimulus),
        "models": len(per_model),
        "patient_minus_clinical": round(point, 6),
        "ci95": [round(lo, 6), round(hi, 6)],
        "ci95_excludes_zero": not (lo <= 0 <= hi),
        **signs,
        "per_model": {m: round(float(v), 6) for m, v in sorted(model_means.items())},
    }


def pairing_report(cells: dict[tuple[str, str], dict[str, list[tuple[int, bool, bool]]]]) -> dict[str, Any]:
    """Where every measured row goes relative to the patient-minus-clinical contrast.

    A measured row is either in the contrast (one of the two compared arms of a cell that has
    both) or outside it for a named reason: its cell lacks one of the two arms, or its arm is not
    one the contrast compares (the advice lane's `translated` arm, or `colloquial` beside a
    `patient` arm). The first reason was a silent `continue` in the estimators (Codex, PR #29);
    each such cell is now listed by label with the arms it does have. The counts add up:
    rows in the contrast plus rows outside it equal the rows measured."""
    outside: Counter = Counter()
    missing: list[dict[str, Any]] = []
    in_contrast = paired = 0
    for (stimulus_id, model), arms in sorted(cells.items()):
        patient_arm = next((a for a in PATIENT_ARMS if a in arms), None)
        if patient_arm is None or CLINICAL_ARM not in arms:
            rows = sum(len(samples) for samples in arms.values())
            outside["cell_lacks_the_patient_or_clinical_arm"] += rows
            missing.append({"stimulus_id": stimulus_id, "model": model, "arms_present": sorted(arms), "rows": rows})
            continue
        paired += 1
        for arm, samples in arms.items():
            if arm in (patient_arm, CLINICAL_ARM):
                in_contrast += len(samples)
            else:
                outside[f"arm_not_compared:{arm}"] += len(samples)
    return {
        "cells_with_both_arms": paired,
        "cells_missing_an_arm": missing,
        "judge_of_record_rows_in_the_contrast": in_contrast,
        "measured_rows_outside_the_contrast": dict(sorted(outside.items())),
    }


def analyze(advice_dir: str, judge: str, boot: int, seed: int, vocab_path: str = VOCAB_PATH,
            rubric_path: str = RUBRIC_PATH, rubric_digest: str | None = None) -> dict[str, Any]:
    vocab = load_vocab(vocab_path)
    by_sha, judgments = load_corpus(advice_dir)
    digest = select_rubric_digest(judgments, judge, rubric_digest)
    tiers, rubric_version = load_rubric_tiers(rubric_path, digest)
    cells, skipped = build_cells(by_sha, judgments, vocab, judge, digest, {tier: i for i, tier in enumerate(tiers)})
    measured = sum(len(samples) for arms in cells.values() for samples in arms.values())
    out_of_scope = skipped.pop("_other_judge_out_of_scope", 0)
    other_rubric = skipped.pop("_other_rubric_digest_out_of_scope", 0)
    unmeasurable = dict(sorted(skipped.items()))
    considered = measured + sum(unmeasurable.values())
    # Each estimate gets its own Random(seed): every stratum is then reproducible on its own,
    # rather than depending on how many draws an earlier stratum happened to consume.
    readouts = {}
    for name, index in (("names_specialist_service", 1), ("names_emergency_service", 2)):
        readouts[name] = {
            "all_cells": estimate(cells, index, random.Random(seed), boot, False),
            "tier_identical_cells": estimate(cells, index, random.Random(seed), boot, True),
        }
    tier = {
        "all_cells": estimate_tier(cells, random.Random(seed), boot),
    }
    return {
        "_generator": "scripts/referral_destination.py",
        "seed": seed,
        "boot": boot,
        "judge_of_record": judge,
        "rubric": {
            "path": rubric_path,
            "sha256": digest,
            "version": rubric_version,
            "tier_order_least_to_most_urgent": tiers,
        },
        "vocabulary": {
            "path": vocab_path,
            "status": vocab.get("status"),
            "version": vocab.get("version"),
            "specialist_terms": len(vocab["specialist_services"]),
            "emergency_terms": len(vocab["emergency_services"]),
        },
        "method": {
            "cell": "(stimulus_id, model, arm); samples within a cell are averaged before differencing",
            "difference": "patient-or-colloquial arm minus clinical arm, per (stimulus, model) cell",
            "ci": "percentile cluster bootstrap over stimuli, 95%",
            "tier_identical_stratum": "cells whose two arms carry the same modal tier, a tie between modes broken "
                                      "toward the most urgent (the registered per-cell summary, "
                                      "docs/preregistration_advice.md Amendment 1)",
        },
        "limitation": vocab.get("method_note"),
        "coverage": {
            "responses_indexed": len(by_sha),
            "rows_from_other_judges_out_of_scope": out_of_scope,
            "judge_of_record_rows_under_other_rubric_digests_out_of_scope": other_rubric,
            "judge_of_record_rows_considered": considered,
            "judge_of_record_rows_measured": measured,
            "coverage_rate": round(measured / considered, 6) if considered else 0.0,
            "unmeasurable_by_reason": unmeasurable,
            **pairing_report(cells),
        },
        "readouts": readouts,
        "urgency_tier_for_comparison": tier,
    }


def estimate_tier(
    cells: dict[tuple[str, str], dict[str, list[tuple[int, bool, bool]]]], rng: random.Random, n_boot: int
) -> dict[str, Any]:
    """The same estimator on the modal tier rank, so the destination result can be read beside
    the urgency result it is NOT a restatement of."""
    per_stimulus: dict[str, list[float]] = defaultdict(list)
    per_model: dict[str, list[float]] = defaultdict(list)
    used = 0
    for (stimulus_id, model), arms in cells.items():
        patient_arm = next((a for a in PATIENT_ARMS if a in arms), None)
        if patient_arm is None or CLINICAL_ARM not in arms:
            continue
        difference = _mean(t[0] for t in arms[patient_arm]) - _mean(t[0] for t in arms[CLINICAL_ARM])
        per_stimulus[stimulus_id].append(difference)
        per_model[model].append(difference)
        used += 1
    if used == 0:
        raise ValueError("no comparable cells for the tier comparison")
    point, lo, hi = cluster_bootstrap_ci(per_stimulus, rng, n_boot)
    return {
        "cells": used,
        "stimuli": len(per_stimulus),
        "models": len(per_model),
        "patient_minus_clinical_tier_ranks": round(point, 6),
        "ci95": [round(lo, 6), round(hi, 6)],
        "ci95_excludes_zero": not (lo <= 0 <= hi),
    }


def format_summary(bundle: dict[str, Any]) -> str:
    lines = [
        f"referral destination  seed={bundle['seed']}  boot={bundle['boot']}  judge={bundle['judge_of_record']}"
        f"  rubric={bundle['rubric']['sha256'][:12]}",
        f"  vocabulary {bundle['vocabulary']['path']} ({bundle['vocabulary']['status']})",
        f"  coverage {bundle['coverage']['judge_of_record_rows_measured']}"
        f"/{bundle['coverage']['judge_of_record_rows_considered']}"
        f" = {bundle['coverage']['coverage_rate']:.4f}"
        f"   ({bundle['coverage']['rows_from_other_judges_out_of_scope']} rows from other judges and"
        f" {bundle['coverage']['judge_of_record_rows_under_other_rubric_digests_out_of_scope']} under other rubric"
        f" digests, out of scope)",
    ]
    for reason, count in bundle["coverage"]["unmeasurable_by_reason"].items():
        lines.append(f"    unmeasurable {count:>6}  {reason}")
    for reason, count in bundle["coverage"]["measured_rows_outside_the_contrast"].items():
        lines.append(f"    measured, outside the contrast {count:>6}  {reason}")
    for cell in bundle["coverage"]["cells_missing_an_arm"]:
        lines.append(f"    cell missing an arm: {cell['stimulus_id']} / {cell['model']}"
                     f" has only {cell['arms_present']} ({cell['rows']} rows)")
    for name, strata in bundle["readouts"].items():
        lines.append(f"  {name}")
        for stratum, res in strata.items():
            mark = "excludes 0" if res["ci95_excludes_zero"] else "includes 0"
            lines.append(
                f"    {stratum:<22} {res['patient_minus_clinical']:+.4f}"
                f"  ci95 [{res['ci95'][0]:+.4f}, {res['ci95'][1]:+.4f}]  {mark}"
                f"  {res['cells']} cells / {res['stimuli']} stimuli"
                f"  {_agreement_text(res)}"
            )
    tier = bundle["urgency_tier_for_comparison"]["all_cells"]
    mark = "excludes 0" if tier["ci95_excludes_zero"] else "includes 0"
    lines.append(
        f"  urgency tier (for comparison)  {tier['patient_minus_clinical_tier_ranks']:+.4f}"
        f"  ci95 [{tier['ci95'][0]:+.4f}, {tier['ci95'][1]:+.4f}]  {mark}"
    )
    return "\n".join(lines)


def _agreement_text(res: dict[str, Any]) -> str:
    tied = res["models_tied_at_zero"]
    if res["models_agreeing_in_sign"] is None:
        return f"estimate exactly zero; models by sign {res['models_by_sign']}"
    return (f"{res['models_agreeing_in_sign']}/{res['models'] - tied} non-tied models agree in sign"
            f" ({tied} tied at zero)")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--advice-dir", default="data/advice", help="directory holding the advice JSONL archives")
    parser.add_argument("--judge", default="claude-haiku-4-5", help="judge of record whose rows are analysed")
    parser.add_argument("--boot", type=int, default=2000, help="bootstrap resamples")
    parser.add_argument("--seed", type=int, default=7,
                        help="fixed RNG seed (deterministic; not system entropy), recorded in the output")
    parser.add_argument("--vocab", default=VOCAB_PATH, help="term list, as data")
    parser.add_argument("--rubric", default=RUBRIC_PATH,
                        help="the rubric the judgments were made under; its canonical digest must match, and its "
                             "tier order ranks the tiers")
    parser.add_argument("--rubric-digest", default=None,
                        help="the rubric digest to analyse (a prefix of 12 or more hex characters); required when "
                             "the judge of record's rows carry more than one")
    parser.add_argument("--out", default="referral_destination.json", help="write the bundle here")
    parser.add_argument("--quiet", action="store_true", help="suppress the text summary")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    bundle = analyze(args.advice_dir, args.judge, args.boot, args.seed, args.vocab, args.rubric, args.rubric_digest)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(bundle, handle, indent=2, sort_keys=False)
        handle.write("\n")
    if not args.quiet:
        print(format_summary(bundle))
        print(f"  wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Translation recovery at scale: per-model recovery from the txcorpus runs and their source pairs' runs.

A txcorpus batch (scripts/translate_corpus.py) is a 2panel set built from landed source pairs:

  top_prompt    = the source pair's ORIGINAL clinical sentence, unchanged
  bottom_prompt = the model-written REWRITE of the source pair's patient sentence into clinical wording

The original patient sentence is not a prompt of the batch. It is the source pair's bottom_prompt, named by
generation.source_batch and generation.source_index (generation.original_patient keeps a copy). A txcorpus
run therefore measures p(target | clinical) on its clinical side and p(target | rewrite) on its patient
side, and holds no patient-wording measurement. Recovery needs the source pair's own run:

  recovery = p(target | rewrite) - p(target | patient)
           = txcorpus run probabilities.patient - source run probabilities.patient

joined on (source_batch, source_index), the same model and the same backend (a hosted row is never set
against a CPU logits row). A row is counted only when both runs recorded the sentences the corpus names
and the same target; every measured source pair that is not counted is recorded under ``coverage`` with
its reason, and a pair that sits in more than one corpus is counted once per model.

Correction (2026-11-20). From the 2026-07-19 rewrite until this date the script read the txcorpus clinical
side as the rewrite and its patient side as the patient sentence. The published "recovery" was therefore
p(target | clinical) - p(target | rewrite): how far the rewrite falls short of the clinical sentence, not
what it recovers over patient wording. The writer was checked on the three committed corpora: top_prompt
equals the source pair's clinical sentence in all 1,031 / 352 / 352 rows. The join restored here gives the
counts that rewrite's note attributed to its predecessor (154 and 290 of 350 rows): those rows were not
lost, their source run is outside the analysis membership or not landed, which ``coverage`` now states.

Two runs of one model do not always agree on the same sentence. ``coverage[model].clinical_side_between_runs``
compares the clinical sentence's probability in the txcorpus run with the source run's, over the counted
pairs. Where they differ, part of a pair's recovery is run-to-run difference and not the rewrite.

``mean_gap`` is the wording gap the rewrite had to close on the counted pairs: p(target | clinical) -
p(target | patient), both from the source run. ``mean_gap_closed`` stays null: a txcorpus run does carry
the clinical baseline, so a share-of-gap statistic can be defined, but its form (mean of per-pair ratios or
ratio of means, and which pairs have enough gap to count) is a research decision that has not been made.
``n_with_headroom`` keeps its meaning: pairs the rewrite raised by more than 1 percentage point.

Everything is EXPLORATORY (owner request 2026-07-14): the txcorpus stem never enters confirmatory
populations, and urgency_shift.py skips its trace dirs. Holdout pairs are excluded by
tierb_split.sealed_pair; a seal that cannot be evaluated stops the run before anything is written.
Writes ops/translation_scale.json (+ optional site copy). Offline, $0.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

try:  # invoked from the repo root (CLI/nightly) vs loaded by path (tests)
    from scripts.provenance_stamp import provenance
    from scripts.publication_hold import Gate
    from scripts.tierb_split import SealError, seal_config_error, sealed_pair
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from provenance_stamp import provenance
    from publication_hold import Gate
    from tierb_split import SealError, seal_config_error, sealed_pair

ENGINE = Path(__file__).resolve().parents[1]

# Model -> family, for the frontend's base / instruction-tuned / medical grouping.
# Classification only (no medical vocabulary); models absent here render as "other".
MODEL_FAMILY = {
    "gemma-2-2b": "base",
    "olmo-2-1b": "base",
    "llama-3.2-3b": "base",
    "gemma-2-2b-it": "instruction-tuned",
    "gemma-3-4b-it": "instruction-tuned",
    "qwen3-1.7b": "instruction-tuned",
    "qwen3-4b": "instruction-tuned",
    "medgemma-4b-it": "medical",
    "meditron3-8b": "medical",
    "apertus-8b-meditronfo": "medical",
    # Post-registration additions (2026-10-09), unmeasured until their probes land.
    "gemma-4-e2b": "base",
    "qwen3.5-2b-base": "base",
    "medgemma-1.5-4b-it": "medical",
}

_TOK_RE = re.compile(r'Output "\s*(.*)"$')


def _tok(label):
    if not isinstance(label, str):
        return None
    m = _TOK_RE.match(label)
    return (m.group(1) if m else label).strip() or None


def _results(trace_root: Path, stem_prefix: str, gate: Gate | None = None,
             outside: set[tuple] | None = None) -> dict[tuple, dict]:
    """{(stem, model, backend, index): result} for every summary part the gate admits under matching run
    directories. The backend is part of the key because one model can have a hosted run and a CPU logits
    run of the same stem (``pairs_<STAMP>`` and ``pairs_<STAMP>__gemma-2-2b``), and the two are different
    instruments. ``outside`` collects the keys of rows in parts the gate did not admit, so a row outside
    the membership is told apart from a row that never landed; their values are not kept."""
    out: dict[tuple, dict] = {}
    for part in sorted(trace_root.glob(f"{stem_prefix}*/batch_summary*.json")):
        run_dir = part.parent.name
        stem, _, model_suffix = run_dir.partition("__")
        data = json.loads(part.read_text(encoding="utf-8"))
        model = model_suffix or data.get("graph_model") or "gemma-2-2b"
        admitted = gate is None or gate.admit(part, data, model)
        for r in data.get("results", []):
            key = (stem, model, data.get("backend"), r["index"])
            if admitted:
                out[key] = r
            elif outside is not None:
                outside.add(key)
    return out


def _top(r: dict, side: str) -> str | None:
    """The most probable next token a row recorded for one side, or None."""
    spread = (r.get("predictive_spread") or {}).get(side) or [[None]]
    return _tok(spread[0][0])


def _corpus_rows(simulated_dir: Path) -> Iterator[tuple[str, int, dict]]:
    """(corpus stem, 1-based index, pair) for every row of every committed txcorpus batch, in file-name
    then row order. That order decides which row is counted when a source pair sits in more than one
    corpus (the two priority corpora hold the same pairs, and both are subsets of the full corpus)."""
    for corpus_path in sorted(simulated_dir.glob("txcorpus_*.json")):
        if corpus_path.name.endswith(".report.json"):
            continue
        for i, pair in enumerate(json.loads(corpus_path.read_text(encoding="utf-8")), start=1):
            yield corpus_path.stem, i, pair


def _source_key(cstem: str, i: int, pair: dict) -> tuple:
    """The source pair a corpus row was built from; the row's own identity when it names none."""
    gen = pair.get("generation") or {}
    batch, index = gen.get("source_batch"), gen.get("source_index")
    return (batch, index) if batch and index is not None else (cstem, i)


def _sealed(pair: dict, dashboard_path: Path | None, simulated_dir: Path) -> bool:
    """tierb_split.sealed_pair for the source pair of a corpus row. SealError propagates."""
    gen = pair.get("generation") or {}
    return sealed_pair(gen.get("source_batch"), gen.get("source_index"), pair.get("top_prompt"),
                       dashboard_path=dashboard_path, simulated_dir=simulated_dir)


PERSISTENCE = 2  # consecutive readable layers = formation (adopted 2026-07-14)


def _formation(layers, persistence=PERSISTENCE):
    """First layer where the target stays readable for `persistence` layers;
    same rule as jlens_insights.formation_layer (kept in sync by test)."""
    ranks = [rec.get("target_rank") for rec in layers]
    run = 0
    for i, r in enumerate(ranks):
        run = run + 1 if r is not None else 0
        if run >= persistence:
            return layers[i - persistence + 1]["layer"]
    return None


def _lens_profiles(trace_root: Path, stem_prefix: str) -> dict:
    """{(stem, index): {'formed': layer|None}} from landed lens summaries."""
    out = {}
    for part in sorted(trace_root.glob(f"{stem_prefix}*__jlens_gemma-2-2b/jlens_summary.part_*.json")):
        stem = part.parent.name.split("__jlens_")[0]
        data = json.loads(part.read_text(encoding="utf-8"))
        for r in data.get("results", []):
            status = r.get("parse_status")
            if isinstance(status, dict) and any(v != "ok" for v in status.values()):
                continue
            pat = (r.get("depth") or {}).get("patient") or []
            if pat:
                out[(stem, r["index"])] = {"formed": _formation(pat)}
    return out


def lens_recovery(trace_root: Path, simulated_dir: Path, dashboard_path: Path | None = None) -> dict:
    """Formation-depth recovery (gemma-2-2b, EXPLORATORY): for corpus sentences
    read by the lens under BOTH wordings, did translation move the answer from
    never-forms to forms? Uses the txcorpus lens pull (its patient side is the
    rewrite) joined to the source batch's lens pull (patient side); gemma-2-2b only.

    Each source pair is counted once. The two priority corpora hold the same pairs, and
    each has its own lens pull; before 2026-11-20 a pair read in both was counted twice.
    The first readout in corpus file-name order is the one counted; the later ones are
    reported as ``repeat_readouts``, with the number that disagree with the counted one
    on whether the answer formed."""
    src_lens = _lens_profiles(trace_root, "pairs_")
    tx_lens = _lens_profiles(trace_root, "txcorpus_")
    if not tx_lens:
        return {"n_paired": 0, "_": "no translated-side lens readouts landed yet"}
    joined: dict[tuple, dict] = {}
    repeats = disagreeing = sealed = 0
    for cstem, i, pair in _corpus_rows(simulated_dir):
        gen = pair.get("generation") or {}
        tx = tx_lens.get((cstem, i))
        src = src_lens.get((gen.get("source_batch"), gen.get("source_index")))
        if tx is None or src is None:
            continue
        if _sealed(pair, dashboard_path, simulated_dir):
            sealed += 1
            continue
        key = _source_key(cstem, i, pair)
        counted = joined.get(key)
        if counted is not None:
            repeats += 1
            disagreeing += (counted["translated_formed"] is None) != (tx["formed"] is None)
            continue
        joined[key] = {"patient_formed": src["formed"], "translated_formed": tx["formed"]}
    rows = list(joined.values())
    never = [j for j in rows if j["patient_formed"] is None]
    return {
        "_": ("Lens view of translation, gemma-2-2b, EXPLORATORY (phrases predate "
              "amendment 2 adoption): formation = readable for 2 consecutive layers "
              "in the top-8 window, per the adopted counting rules. Each source pair "
              "is counted once; repeat_readouts are further lens pulls of a counted pair."),
        "n_paired": len(rows),
        "patient_never_formed": len(never),
        "recovered_to_formed": sum(1 for j in never if j["translated_formed"] is not None),
        "formed_both": sum(1 for j in rows
                           if j["patient_formed"] is not None and j["translated_formed"] is not None),
        "lost_by_translation": sum(1 for j in rows
                                   if j["patient_formed"] is not None and j["translated_formed"] is None),
        "repeat_readouts": repeats,
        "repeat_readouts_disagreeing": disagreeing,
        "sealed_holdout": sealed,
    }


def _join(pair: dict, tx: dict, src: dict | None, src_outside: bool) -> tuple[dict | None, str | None]:
    """One txcorpus row set against its source pair's row from the same model and backend.

    Returns (counted row, None) or (None, reason). The reasons, in the order they are tested:
    rewrite_probability_missing, source_part_outside_membership, source_row_not_landed,
    sentence_mismatch (either run recorded a prompt other than the one the corpus names for it),
    target_mismatch, patient_probability_missing."""
    gen = pair.get("generation") or {}
    tx_pr = tx.get("probabilities") or {}
    p_rewrite = tx_pr.get("patient")         # the txcorpus patient side is bottom_prompt = the rewrite
    if p_rewrite is None:
        return None, "rewrite_probability_missing"
    if src is None:
        return None, "source_part_outside_membership" if src_outside else "source_row_not_landed"
    tx_prompts, src_prompts = tx.get("prompts") or {}, src.get("prompts") or {}
    if ((tx_prompts.get("clinical"), tx_prompts.get("patient"))
            != (pair.get("top_prompt"), pair.get("bottom_prompt"))
            or (src_prompts.get("clinical"), src_prompts.get("patient"))
            != (pair.get("top_prompt"), gen.get("original_patient"))):
        return None, "sentence_mismatch"
    target = _tok(tx.get("target_token"))
    if target != _tok(src.get("target_token")):
        return None, "target_mismatch"
    src_pr = src.get("probabilities") or {}
    p_patient = src_pr.get("patient")
    if p_patient is None:
        return None, "patient_probability_missing"
    p_clinical_tx, p_clinical_src = tx_pr.get("clinical"), src_pr.get("clinical")
    top_rewrite, top_patient = _top(tx, "patient"), _top(src, "patient")
    return {
        "recovery": p_rewrite - p_patient,
        "gap": None if p_clinical_src is None else p_clinical_src - p_patient,
        "clinical_between_runs": (None if p_clinical_tx is None or p_clinical_src is None
                                  else p_clinical_tx - p_clinical_src),
        "top_restored": bool(target and top_rewrite == target and top_patient != target),
        "top_lost": bool(target and top_patient == target and top_rewrite != target),
    }, None


def analyze(trace_root: Path, simulated_dir: Path, gate: Gate | None = None,
            dashboard_path: Path | None = None) -> dict:
    rows = list(_corpus_rows(simulated_dir))
    if not rows:
        return {"_": "no txcorpus batch landed yet", "corpora": [], "per_model": {}}
    if gate is None:
        gate = Gate(trace_root.parent if trace_root.name == "trace_out" else ENGINE, manifest_optional=True)
    tx_results = _results(trace_root, "txcorpus_", gate=gate)
    lanes: dict[tuple[str, int], list[tuple[str, str]]] = {}
    for stem, model, backend, index in tx_results:
        lanes.setdefault((stem, index), []).append((model, backend))

    # Source runs are read only for the batches that measured corpus rows name.
    src_results: dict[tuple, dict] = {}
    src_outside: set[tuple] = set()
    for batch in sorted({(pair.get("generation") or {}).get("source_batch")
                         for cstem, i, pair in rows if (cstem, i) in lanes} - {None}):
        src_results.update(_results(trace_root, batch, gate=gate, outside=src_outside))

    # Per model, every source pair ends in exactly one state: counted, or not counted with one reason.
    counted: dict[str, dict[tuple, dict]] = {}
    not_counted: dict[str, dict[tuple, str]] = {}
    n_rows: Counter[str] = Counter()
    for cstem, i, pair in rows:
        gen = pair.get("generation") or {}
        key = _source_key(cstem, i, pair)
        for model, backend in sorted(lanes.get((cstem, i), [])):
            n_rows[model] += 1
            done = counted.setdefault(model, {})
            reasons = not_counted.setdefault(model, {})
            if key in done:
                continue                              # a further row of a pair already counted
            if _sealed(pair, dashboard_path, simulated_dir):
                reasons.setdefault(key, "sealed_holdout")
                continue
            src_key = (gen.get("source_batch"), model, backend, gen.get("source_index"))
            row, reason = _join(pair, tx_results[(cstem, model, backend, i)],
                                src_results.get(src_key), src_key in src_outside)
            if row is None:
                reasons.setdefault(key, reason)
                continue
            reasons.pop(key, None)                    # an earlier row of this pair failed; this one counts
            done[key] = {**row, "corpus": cstem, "backend": backend}

    summary = {}
    coverage = {}
    measured_stems: set[str] = set()
    rows_read = Counter(model for _, model, _, _ in tx_results)
    for model in sorted(rows_read):
        joined = list(counted.get(model, {}).values())
        reasons = not_counted.get(model, {})
        between = [r["clinical_between_runs"] for r in joined if r["clinical_between_runs"] is not None]
        coverage[model] = {
            "rows": rows_read[model],
            "rows_without_corpus_row": rows_read[model] - n_rows[model],
            "pairs": len(joined) + len(reasons),
            "pairs_counted": len(joined),
            "not_counted": dict(sorted(Counter(reasons.values()).items())),
            "clinical_side_between_runs": {
                "n": len(between),
                "mean_diff": round(statistics.fmean(between), 4),
                "max_abs_diff": round(max(abs(v) for v in between), 4),
                "n_abs_diff_over_1pp": sum(1 for v in between if abs(v) > 0.01),
            } if between else None,
        }
        if not joined:
            continue
        measured_stems.update(r["corpus"] for r in joined)
        recs = [r["recovery"] for r in joined]
        gaps = [r["gap"] for r in joined if r["gap"] is not None]
        summary[model] = {
            "n": len(joined),
            "family": MODEL_FAMILY.get(model, "other"),
            "backends": sorted({r["backend"] for r in joined}),
            "mean_recovery": round(statistics.fmean(recs), 4),
            "median_recovery": round(statistics.median(recs), 4),
            "share_recovery_positive": round(sum(1 for v in recs if v > 0) / len(joined), 4),
            "n_with_headroom": sum(1 for v in recs if v > 0.01),
            "mean_gap": round(statistics.fmean(gaps), 4) if gaps else None,
            "n_gap": len(gaps),
            "mean_gap_closed": None,  # see module docstring: definable, not yet defined
            "top_restored": sum(1 for r in joined if r["top_restored"]),
            "top_lost": sum(1 for r in joined if r["top_lost"]),
        }
    # claim as data (audit M7): the page's minority-lift sentence for the
    # instruction-tuned family — mean lift positive but median near zero on
    # EVERY instruction-tuned model — with its threshold recorded. None when
    # the family has no measured models (the page then omits the clause).
    it_models = [m for m, s in summary.items() if s["family"] == "instruction-tuned"]
    claims = {
        "median_near_zero_threshold": 0.01,
        "instruction_tuned_minority_lift":
            all(s["mean_recovery"] > 0 and abs(s["median_recovery"]) < 0.01
                for s in (summary[m] for m in it_models)) if it_models else None,
    }
    return {
        "claims": claims,
        "_": ("EXPLORATORY translation recovery at scale, recomputed from committed runs "
              "(method corrected 2026-11-20). recovery = p(target|rewrite) - p(target|patient): "
              "the txcorpus run's patient side (its bottom_prompt is the rewrite) minus the "
              "source pair's own run's patient side, same model and backend, joined on "
              "generation.source_batch / source_index. n = source pairs counted, each once. "
              "coverage gives, per model, the rows read (and any with no row in a committed "
              "corpus), the source pairs they cover, the pairs counted, the pairs not counted by "
              "reason, and how far the two runs differ on the identical clinical sentence. mean_gap = p(target|clinical) - p(target|patient) "
              "from the source run on the counted pairs (n_gap of them). n_with_headroom = "
              "pairs the rewrite raised by more than 1pp. top_restored / top_lost = pairs whose "
              "top-1 prediction returns to / leaves the clinical target under the rewrite vs "
              "patient wording. mean_gap_closed is null: its definition has not been decided."),
        "corpora": sorted(measured_stems),
        "per_model": summary,
        "coverage": coverage,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trace-root", default=str(ENGINE / "trace_out"))
    parser.add_argument("--simulated-dir", default=str(ENGINE / "data/simulated"))
    parser.add_argument("--dashboard", default=str(ENGINE / "ops/dashboard.json"),
                        help="dashboard whose tierb.start_utc the holdout seal reads")
    parser.add_argument("--out", default=str(ENGINE / "ops/translation_scale.json"))
    parser.add_argument("--site", default=None,
                        help="site repo root; also writes data/translation_scale.json there")
    args = parser.parse_args()
    trace_root, simulated_dir, dashboard = Path(args.trace_root), Path(args.simulated_dir), Path(args.dashboard)
    gate = Gate(trace_root.parent if trace_root.name == "trace_out" else ENGINE)
    try:
        result = analyze(trace_root, simulated_dir, gate=gate, dashboard_path=dashboard)
        result["lens_recovery"] = lens_recovery(trace_root, simulated_dir, dashboard_path=dashboard)
    except SealError as exc:
        return seal_config_error(exc)  # exit 2 before anything is written: the publish chain stops
    result["_provenance"] = provenance("translation_scale.py")
    rep = gate.report()
    if rep:
        print(rep)
    Path(args.out).write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    for model, c in result.get("coverage", {}).items():
        s = result["per_model"].get(model)
        left = ", ".join(f"{reason} {n}" for reason, n in c["not_counted"].items()) or "none"
        print(f"{model}: {c['rows']} rows over {c['pairs']} source pairs; counted {c['pairs_counted']}; "
              f"not counted: {left}")
        if s:
            print(f"  [{s['family']}] mean recovery {s['mean_recovery']:+.4f} "
                  f"(median {s['median_recovery']:+.4f}, positive {s['share_recovery_positive']:.0%}) "
                  f"top restored {s['top_restored']} / lost {s['top_lost']}")
    lr = result["lens_recovery"]
    if lr.get("n_paired"):
        print(f"lens: {lr['recovered_to_formed']} of {lr['patient_never_formed']} "
              f"never-formed phrases now form; {lr['lost_by_translation']} lost "
              f"({lr['n_paired']} source pairs, {lr['repeat_readouts']} repeat readouts)")
    print(f"-> {args.out}")
    if args.site:
        site_copy = Path(args.site) / "data" / "translation_scale.json"
        site_copy.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
        print(f"site copy -> {site_copy}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

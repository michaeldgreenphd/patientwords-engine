"""Site dataset for the lens-robustness arm: data/jlens_loglens.json.

The formation-depth story (scripts/jlens_insights.py) is read out through the
Jacobian lens. This joins the SAME pairs measured through the plain logit lens
(jlens_readout.py --lens-type LOGIT_LENS, whose runs land in
trace_out/*__loglens_<model>/) so the site can show whether the finding
survives the lens choice - the referee-adjacent robustness question and the
pre-approved "same depth profiles under the plain logit lens" roadmap item.

For every pair with both readouts committed: the patient-side formation layer
and failure class under each lens, whether the two lenses agree, and the class
distribution under each. Formation and classification reuse jlens_insights so
the numbers match the headline census exactly. Tier B holdout pairs are sealed.
EXPLORATORY; correlational readout, not an intervention.

Method credit is pulled from the summaries' method_credit, never typed.
No medical vocabulary lives in this file.

Usage:
  python scripts/export_jlens_loglens.py --model gemma-2-2b \
      [--out data/jlens_loglens.json] [--site ../patientwords]
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jlens_insights as ji  # noqa: E402  (formation_layer, classify, quantiles, PERSISTENCE)
from tierb_split import is_holdout, is_tierb_batch, tierb_start_stamp  # noqa: E402

METHOD_CREDIT_FALLBACK = (
    "Jacobian lens: Gurnee et al., Transformer Circuits, 2026; reference "
    "implementation github.com/anthropics/jacobian-lens (Apache-2.0); hosted by "
    "neuronpedia.org. Logit lens is the plain unembedding baseline."
)
SCOPE = ("hosted Jacobian lens vs. plain logit lens, top-8 readout per layer; "
         "EXPLORATORY robustness arm; correlational, not an intervention")
CLASS_ORDER = ("held", "hijack", "capture", "unreadable")

_TIERB_START = tierb_start_stamp()
_ACCEPT_CACHE = {}


def _sealed(batch, index):
    """Tier B holdout seal (mirrors the other exporters)."""
    if not is_tierb_batch(batch or "", _TIERB_START):
        return False
    if batch not in _ACCEPT_CACHE:
        fp = Path("data/simulated") / f"{batch}.json"
        try:
            _ACCEPT_CACHE[batch] = json.loads(fp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _ACCEPT_CACHE[batch] = None
    pairs = _ACCEPT_CACHE[batch]
    idx = index or 0
    if not pairs or not (0 < idx <= len(pairs)):
        return False
    return is_holdout(pairs[idx - 1].get("top_prompt"))


# --------------------------------------------------------------------------- #
# Pure functions (unit-tested offline)
# --------------------------------------------------------------------------- #


def row_from_result(result):
    """A formation/class row for one summary result, reusing jlens_insights,
    or None when the pair carries no usable depth profile."""
    status = result.get("parse_status")
    if isinstance(status, dict) and any(v != "ok" for v in status.values()):
        return None
    depth = result.get("depth") or {}
    clin, pat = depth.get("clinical") or [], depth.get("patient") or []
    if not clin or not pat:
        return None
    row = {
        "index": result.get("index"),
        "target": (result.get("target_token") or "").strip() or None,
        "clin_formed": ji.formation_layer(clin),
        "pat_formed": ji.formation_layer(pat),
        "pat_final_rank": pat[-1].get("target_rank") if pat else None,
    }
    row["class"] = ji.classify(row)
    return row


def rows_from_summary(summary):
    """{index: row} for the usable results of one lens summary."""
    out = {}
    for result in summary.get("results", []):
        row = row_from_result(result)
        if row is not None and row["index"] is not None:
            out[row["index"]] = row
    return out


def class_counts(rows):
    counts = {c: 0 for c in CLASS_ORDER}
    for r in rows:
        counts[r["class"]] = counts.get(r["class"], 0) + 1
    return counts


def join_lenses(jac_rows, log_rows):
    """Per-pair comparison for indices present under BOTH lenses, sorted by
    index. Each: index, target, jacobian/logit = {pat_formed, class},
    formed_agree (both formed / both never), class_agree."""
    per_pair = []
    for idx in sorted(set(jac_rows) & set(log_rows)):
        j, g = jac_rows[idx], log_rows[idx]
        per_pair.append({
            "index": idx,
            "target": j.get("target") or g.get("target"),
            "jacobian": {"pat_formed": j["pat_formed"], "class": j["class"]},
            "logit": {"pat_formed": g["pat_formed"], "class": g["class"]},
            "formed_agree": (j["pat_formed"] is None) == (g["pat_formed"] is None),
            "class_agree": j["class"] == g["class"],
        })
    return per_pair


def summarize_agreement(per_pair):
    n = len(per_pair)
    return {
        "n_paired": n,
        "class_agree": sum(1 for p in per_pair if p["class_agree"]),
        "formed_agree": sum(1 for p in per_pair if p["formed_agree"]),
    }


# --------------------------------------------------------------------------- #
# I/O
# --------------------------------------------------------------------------- #


def collect_rows(kind, model, trace_root):
    """{batch: {index: row}} across every committed summary for a lens kind
    ('jlens' = Jacobian, 'loglens' = logit), sealed holdout pairs dropped."""
    by_batch = {}
    marker = f"__{kind}_"
    for part in sorted(Path(trace_root).glob(f"*{marker}{model}/jlens_summary.part_*.json")):
        batch = part.parent.name.split(marker, 1)[0]
        try:
            summary = json.loads(part.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for idx, row in rows_from_summary(summary).items():
            if _sealed(batch, idx):
                continue
            by_batch.setdefault(batch, {})[idx] = row
    return by_batch


def load_credit(trace_root, model):
    """method_credit from any committed loglens or jlens summary; fallback."""
    for kind in ("loglens", "jlens"):
        for part in sorted(Path(trace_root).glob(f"*__{kind}_{model}/jlens_summary.part_*.json")):
            try:
                summary = json.loads(part.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if summary.get("method_credit"):
                return summary["method_credit"]
    return METHOD_CREDIT_FALLBACK


def build_payload(trace_root, model):
    """The data/jlens_loglens.json payload, or None when no logit-lens run is
    committed yet (caller refuses rather than publish an empty arm)."""
    log_by_batch = collect_rows("loglens", model, trace_root)
    if not log_by_batch:
        return None
    jac_by_batch = collect_rows("jlens", model, trace_root)

    per_pair, jac_rows_all, log_rows_all = [], [], []
    for batch, log_rows in sorted(log_by_batch.items()):
        jac_rows = jac_by_batch.get(batch, {})
        per_pair.extend(dict(p, batch=batch) for p in join_lenses(jac_rows, log_rows))
        jac_rows_all.extend(r for idx, r in jac_rows.items() if idx in log_rows)
        log_rows_all.extend(log_rows.values())

    if not per_pair:
        return None

    def formed_q(rows):
        return ji.quantiles([r["pat_formed"] for r in rows])

    return {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": model,
        "scope": SCOPE,
        "method_credit": load_credit(trace_root, model),
        "persistence_layers": ji.PERSISTENCE,
        "batches": sorted(log_by_batch),
        "jacobian": {
            "formation": formed_q(jac_rows_all),
            "never_formed": sum(1 for r in jac_rows_all if r["pat_formed"] is None),
            "class_counts": class_counts(jac_rows_all),
        },
        "logit": {
            "formation": formed_q(log_rows_all),
            "never_formed": sum(1 for r in log_rows_all if r["pat_formed"] is None),
            "class_counts": class_counts(log_rows_all),
        },
        "agreement": summarize_agreement(per_pair),
        "per_pair": per_pair,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trace-root", default="trace_out")
    parser.add_argument("--model", default="gemma-2-2b")
    parser.add_argument("--out", default="data/jlens_loglens.json")
    parser.add_argument("--site", default="../patientwords", help="'' skips the site copy")
    args = parser.parse_args(argv)

    payload = build_payload(args.trace_root, args.model)
    if payload is None:
        print(f"refused: no committed logit-lens (__loglens_{args.model}) runs under "
              f"{args.trace_root} - not writing the robustness arm")
        return 3

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    ag = payload["agreement"]
    print(f"jlens loglens: {ag['n_paired']} paired · class agree {ag['class_agree']} · "
          f"formation-presence agree {ag['formed_agree']} -> {out}")
    if args.site:
        site_copy = Path(args.site) / "data" / "jlens_loglens.json"
        if site_copy.parent.is_dir():
            site_copy.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
            print(f"site copy -> {site_copy}")
        else:
            print(f"note: site dir {site_copy.parent} absent; skipped site copy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

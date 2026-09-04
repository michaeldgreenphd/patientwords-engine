#!/usr/bin/env python3
"""Regenerate the gallery's demonstration renders (2panel + translation).

These are the synthetic sample-graph figures the site has always used for
Figs. 1 and 4: the depression / "the blues" comparison with the stated
numbers (prob(therapist) 0.86 clinical vs 0.35 patient, Wording gap
-51%). The graphs are hand-authored specimens - the point is to exercise the
full rendering pipeline, not to report a live trace - and the site labels
them as demonstration outputs.

Usage:
  python scripts/render_demo.py --site ../patientwords
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from medlang_circuits.compare_viz import (  # noqa: E402
    CATEGORY_COLORS,
    build_panels,
    render_panels_html,
    render_panels_png,
)

CLINICAL_TOKENS = ["<bos>", "I", "have", "depression", ",", "so", "I", "need",
                   "to", "talk", "to", "a"]
PATIENT_TOKENS = ["<bos>", "I", "'ve", "got", "the", "blues", ",", "so", "I",
                  "need", "to", "talk", "to", "a"]
CLINICAL_EMPH = 3   # "depression"
PATIENT_EMPH = 5    # "blues"


def _node(layer, idx, ctx, category, desc, feature_type="cross layer transcoder"):
    if feature_type == "embedding":
        node_id = f"E_{ctx}"
        return {"node_id": node_id, "feature_type": "embedding", "layer": "E",
                "ctx_idx": ctx, "clerp": desc}
    if feature_type == "logit":
        node_id = f"L_{idx}"
        return {"node_id": node_id, "feature_type": "logit", "layer": str(layer),
                "ctx_idx": ctx, "clerp": desc}
    if feature_type == "mlp reconstruction error":
        return {"node_id": f"err_{layer}_{ctx}", "feature_type": feature_type,
                "layer": str(layer), "ctx_idx": ctx, "clerp": ""}
    feature = layer * 100000 + idx
    return {
        "node_id": f"{layer}_{feature}_{ctx}",
        "feature_type": feature_type,
        "layer": str(layer),
        "ctx_idx": ctx,
        "feature": feature,
        "clerp": desc,
        "medlang": {"category": category, "method": "curated_demo", "description": desc},
    }


def _link(a, b, w):
    return {"source": a["node_id"], "target": b["node_id"], "weight": w}


def _base_scaffold(tokens, top_layer=25):
    """Embeddings for every token plus light structural sprinkles."""
    nodes = [_node(0, 0, i, None, tok, feature_type="embedding") for i, tok in enumerate(tokens)]
    links = []
    sprinkle = [
        (0, 1, "structural", "sentence-initial position"),
        (1, len(tokens) - 4, "structural", "prepositional phrase syntax"),
        (3, len(tokens) - 6, "structural", "comma and clause boundary"),
        (8, len(tokens) - 2, "structural", "infinitive 'to' constructions"),
        (15, len(tokens) - 1, "structural", "indefinite article expectations"),
        (21, len(tokens) - 1, "structural", "end-of-clause position"),
    ]
    for j, (layer, ctx, cat, desc) in enumerate(sprinkle):
        n = _node(layer, 900 + j, ctx, cat, desc)
        nodes.append(n)
        links.append(_link(nodes[ctx], n, 0.5))
    err = _node(11, 0, len(tokens) - 3, None, "", feature_type="mlp reconstruction error")
    nodes.append(err)
    return nodes, links, err


def make_clinical_graph():
    """'I have depression, so I need to talk to a' -> therapist 0.86."""
    tokens = CLINICAL_TOKENS
    nodes, links, err = _base_scaffold(tokens)
    emb = {n["ctx_idx"]: n for n in nodes if n["feature_type"] == "embedding"}
    last = len(tokens) - 1

    chain = [
        _node(4, 8257, CLINICAL_EMPH, "clinical",
              "medical terms and concepts related to depression and psychiatric disorders"),
        _node(9, 3310, CLINICAL_EMPH, "clinical",
              "seeking professional help for mental-health problems"),
        _node(13, 5120, 7, "clinical", "needing to talk to someone about a problem"),
        _node(17, 7176, last, "clinical", "mentions of mental illness and clinical treatment"),
        _node(21, 2214, last, "clinical", "referrals to therapists and mental-health professionals"),
        _node(24, 1188, last, "clinical", "professional counseling context before a role noun"),
    ]
    support = [
        _node(2, 4401, 1, "structural", "first-person subject"),
        _node(6, 2020, 5, "clinical", "consequence clauses about health decisions"),
        _node(12, 6003, 9, "clinical", "talk therapy and talking through problems"),
        _node(18, 3391, 9, "off_target", "casual conversation verbs"),
    ]
    logits = [
        _node(26, 0, last, None, "therapist (p=0.86)", feature_type="logit"),
        _node(26, 1, last, None, "doctor (p=0.07)", feature_type="logit"),
        _node(26, 2, last, None, "professional (p=0.04)", feature_type="logit"),
    ]
    nodes += chain + support + logits

    links += [
        _link(emb[CLINICAL_EMPH], chain[0], 4.2),
        _link(chain[0], chain[1], 5.0),
        _link(chain[1], chain[2], 3.4),
        _link(chain[1], chain[3], 4.4),
        _link(chain[2], chain[3], 2.2),
        _link(chain[3], chain[4], 5.2),
        _link(chain[4], chain[5], 4.8),
        _link(chain[5], logits[0], 6.0),
        _link(chain[4], logits[0], 2.6),
        _link(chain[3], logits[1], 1.1),
        _link(chain[4], logits[2], 0.9),
        _link(emb[1], support[0], 1.2),
        _link(emb[5], support[1], 1.4),
        _link(support[1], chain[2], 1.6),
        _link(emb[9], support[2], 2.0),
        _link(support[2], chain[4], 2.4),
        _link(emb[9], support[3], 0.9),
        _link(support[3], logits[1], -0.8),
        _link(err, chain[3], 0.7),
    ]
    return {"metadata": {"scan": "gemma-2-2b", "slug": "demo-clinical",
                         "prompt_tokens": list(tokens)},
            "nodes": nodes, "links": links}


def make_patient_graph():
    """"I've got the blues, so I need to talk to a" -> therapist 0.35."""
    tokens = PATIENT_TOKENS
    nodes, links, err = _base_scaffold(tokens)
    emb = {n["ctx_idx"]: n for n in nodes if n["feature_type"] == "embedding"}
    last = len(tokens) - 1

    off = [
        _node(2, 7734, PATIENT_EMPH, "off_target",
              "music genres, especially blues and jazz"),
        _node(5, 1290, PATIENT_EMPH, "off_target",
              "idioms for sadness and feeling down"),
        _node(12, 8815, PATIENT_EMPH, "off_target",
              "figurative and colloquial expressions for mood"),
        _node(17, 4402, last, "off_target",
              "informal talk with friends about feelings"),
        _node(21, 6110, last, "off_target",
              "casual companionship and friendship contexts"),
    ]
    clin = [
        _node(9, 3310, PATIENT_EMPH, "clinical",
              "seeking professional help for mental-health problems"),
        _node(13, 5120, 9, "clinical", "needing to talk to someone about a problem"),
        _node(21, 2214, last, "clinical", "referrals to therapists and mental-health professionals"),
    ]
    logits = [
        _node(26, 0, last, None, "therapist (p=0.35)", feature_type="logit"),
        _node(26, 1, last, None, "friend (p=0.31)", feature_type="logit"),
        _node(26, 2, last, None, "doctor (p=0.11)", feature_type="logit"),
    ]
    nodes += off + clin + logits

    links += [
        _link(emb[PATIENT_EMPH], off[0], 3.6),
        _link(emb[PATIENT_EMPH], off[1], 4.6),
        _link(emb[4], off[1], 1.3),
        _link(off[0], off[2], 2.2),
        _link(off[1], off[2], 4.2),
        _link(off[2], off[3], 3.8),
        _link(off[3], off[4], 3.2),
        _link(off[4], logits[1], 5.0),
        _link(off[3], logits[1], 2.0),
        _link(off[2], clin[0], -1.4),
        _link(emb[PATIENT_EMPH], clin[0], 1.5),
        _link(clin[0], clin[1], 2.0),
        _link(clin[1], clin[2], 2.4),
        _link(clin[2], logits[0], 3.0),
        _link(off[4], logits[0], -1.2),
        _link(clin[2], logits[2], 0.9),
        _link(err, off[3], 0.6),
    ]
    return {"metadata": {"scan": "gemma-2-2b", "slug": "demo-patient",
                         "prompt_tokens": list(tokens)},
            "nodes": nodes, "links": links}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", required=True, help="path to the patientwords repo")
    ap.add_argument("--dpi", type=int, default=130)
    args = ap.parse_args()

    clinical, patient = make_clinical_graph(), make_patient_graph()
    emph = [{CLINICAL_EMPH}, {PATIENT_EMPH}]

    # ---- Fig. 1: 2panel (clinical over patient, penalty badge between) ----
    panels = build_panels(
        [clinical, patient],
        labels=['Clinical wording: “I have depression, so I need to talk to a”',
                'Patient wording: “I’ve got the blues, so I need to talk to a”'],
        headlines=["prob(“therapist”) = 0.86", "prob(“therapist”) = 0.35"],
    )
    for p, e in zip(panels, emph):
        p["emphasized"] = e
    badge = {"lines": [{"text": "Wording gap: −51% probability (0.86 → 0.35)",
                        "color": "#b4483d"}]}
    out2 = os.path.join(args.site, "modes", "2panel")
    os.makedirs(out2, exist_ok=True)
    render_panels_html(panels, os.path.join(out2, "index.html"), badges=[badge])
    render_panels_png(panels, os.path.join(out2, "preview.png"), badges=[badge], dpi=args.dpi)
    print("wrote", out2)

    # ---- Fig. 4: translation (patient first, translated recovery below) ----
    tpanels = build_panels(
        [patient, clinical],
        labels=['Patient wording: “I’ve got the blues, so I need to talk to a”',
                'Translated wording: “I have depression, so I need to talk to a”'],
        headlines=["prob(“therapist”) = 0.35", "prob(“therapist”) = 0.86"],
        accents=[CATEGORY_COLORS["off_target"], CATEGORY_COLORS["clinical"]],
        value_label_flags=[False, True],
    )
    tpanels[0]["emphasized"] = {PATIENT_EMPH}
    tpanels[1]["emphasized"] = {CLINICAL_EMPH}
    tbadge = {"lines": [
        {"text": "LLM translation · patient wording → clinical wording",
         "color": "#111827"},
        {"text": "Recovered target probability: +51% (0.35 → 0.86)",
         "color": "#15803d"},
    ]}
    outt = os.path.join(args.site, "modes", "translation")
    os.makedirs(outt, exist_ok=True)
    render_panels_html(tpanels, os.path.join(outt, "index.html"), badges=[tbadge])
    render_panels_png(tpanels, os.path.join(outt, "preview.png"), badges=[tbadge], dpi=args.dpi)
    print("wrote", outt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

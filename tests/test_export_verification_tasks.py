"""Physician verification task bundle (scripts/export_verification_tasks.py) - offline.

Pins the bundle's contract shape, determinism (same seed and stamp: byte-identical; another seed: the same items in
another order), that the display carries none of the hidden fields, numbers, model names, batch ids or proposed
tiers, the fail-closed holdout seal (a planted sealed phrase refuses the export and writes nothing), the list of
unsealed items whose clinical text hashes into the holdout bucket, the counts and selection per family (main-study
penalties equal as recorded tie, and the stated tie rule decides), item-id stability, the question wording (no
hint predicts an answer, the urgency question names the message it asks about, raters are asked not to look the
scenarios up), and the pilot runs: which runs, the review sample or every non-control row, a required or an optional
trace (an optional one is not read, so the items do not change when traces land; Run 2's trace pairs file is still
read as its id key), a trace pairs file with or without review ids, a row's id under every option, which trace
results directory a run reads (named after its pairs file; <stem>__<model>/ for another graph model, named or the
one found, two found refused), the naming rule for a trace pairs file (<run id>_<name>.json, the lanes' rule, compared
with fire_trigger's when it has one), a byte-identical copy of Run 2's trace pairs file beside it (allowed, and never
read for traces), and the refusals for a run that is not finalized, not version 2, changed since it was finalized,
missing a required trace, whose trace pairs file is not named after it, holds "__" or shares a stem with another
run's (optional runs included), that holds a second trace pairs file other than such a copy, or whose review map,
trace pairs file or sidecar does not fit it; and later
rounds (--previous-bundle): a previous item dropped or changed, a question id dropped or kept with another scale,
answer values (of another JSON type included), phase, requirement or lock, another notes limit, and a previous
bundle of another shape. Every input here is synthetic, abstract and non-medical (the medical vocabulary rule in
AGENTS.md); the seal fixtures follow tests/test_seal_check.py and tests/test_tierb_split.py. The committed-bundle
tests check every bundle under data/verification/ against the contract, with failure messages naming item ids only,
never row text, and re-export the first bundle from the committed engine files: the default run gives its pilot
items unchanged, and with the site payload it recorded the recorded command gives its items byte for byte.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import re
import shutil
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("export_verification_tasks",
                                               ROOT / "scripts" / "export_verification_tasks.py")
evt = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(evt)

QUESTIONS = ROOT / "data" / "verification" / "questions.json"
STAMP = "20261003T120000Z"
TIER_A = "pairs_20260705T000000Z"
RUN2 = "pilot_v2_20261002"          # the default run: its items keep the first bundle's label and id key
RUN_NEW = "pilot_v9_20990101"       # any other run
NEW_PAIRS = f"{RUN_NEW}_trace_pairs"  # its trace pairs file's stem, named after the run as the naming rule asks
TIER_B = "pairs_20260711T000000Z"
START = "2026-07-10T01:14:38Z"
MARK_RATIONALE = "zzmark rationale qx"
MARK_TOPIC = "zzmark topic qx"
MARK_BASIS = "zzmark basis qx"
MARK_TIER_WHY = "zzmark tier reasoning qx"
MARK_AUTHOR = "zzmark author qx"
MARK_NUMBER = 0.7771
MODEL_NAMES = re.compile(r"\b(gemma|qwen|llama|claude|anthropic|openai|gpt|gemini|grok|deepseek|kimi|moonshot|"
                         r"mistral|haiku|sonnet|opus)\b", re.I)
BATCH_ID = re.compile(r"(pairs|advman|advnat|advmc|advprobe|stimuli)_\d{8}")
DISPLAY_KEYS = {
    "pair_sentence": {"kind", "clinical", "patient", "next_word", "cut_off"},
    "message_pair": {"kind", "clinical_message", "patient_message", "cut_off"},
    "script": {"kind", "n_turns", "arms"},
}
FAMILY_KIND = {"tracing_pair": "pair_sentence", "advice": "message_pair", "multiturn": "script"}


def _holdout(text: str) -> bool:
    return int(hashlib.sha1(text.encode()).hexdigest(), 16) % 10 == 0


def _phrase(base: str, holdout: bool) -> str:
    """A variant of base that lands in (or out of) the sha1-mod-10 holdout bucket."""
    for i in range(500):
        p = f"{base} {i}"
        if _holdout(p) == holdout:
            return p
    raise AssertionError("no phrase found")


SEALED = _phrase("zz sealed sample text", True)
EXPLORE_B = _phrase("The amber widget on shelf nine needs a", False)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---- the synthetic world -------------------------------------------------------------------------------------

def _pilot_rows() -> list[dict]:
    rows = []
    for n, (ct, pt, word) in enumerate([("blue ledger", "notebook", "office"),
                                        ("brass key", "little key for the shed", "neighbour")], 1):
        rows.append({"id": f"A__cell__kind__L{n:02d}", "call_id": "A__cell__kind", "arm": "A", "specialty": "cell",
                     "swap_type": "kind", "cell": "cell__kind", "cell_index": 0, "line_index": n, "attempt": 1,
                     "clinical_term": ct, "patient_term": pt,
                     "template": "I left the ___ on the bus, so I need to call my", "next_word": word,
                     "control": "none", "control_faithful": None, "prompt_sha256": "0" * 64})
    return rows


def _scenario(n: int, batch: str, index: int, clinical: str, patient: str, penalty: Any,
              screening: dict | None = None) -> dict:
    model = {"language_penalty": penalty, "anchor_fallback": False, "screening": screening or {}}
    return {"index": n, "batch": batch, "batch_index": index, "clinical_prompt": clinical, "patient_prompt": patient,
            "intended_target": "label", "rationale": MARK_RATIONALE, "patient_term": "gadget",
            "clinical_term": "widget", "topic": MARK_TOPIC, "topics": [MARK_TOPIC],
            "models": {"gemma-2-2b": model}, "language_penalty": penalty, "flipped": False}


def _payload_rows() -> tuple[list[dict], list[dict], list[dict]]:
    """(payload scenarios, Tier A batch pairs, Tier B batch pairs)."""
    tier_a = [{"top_prompt": f"The plain widget on shelf {k} needs a"} for k in range(1, 8)]
    tier_b = [{"top_prompt": SEALED}, {"top_prompt": EXPLORE_B}]

    def a(k: int, penalty: Any, patient: str | None = None, screening: dict | None = None) -> dict:
        return _scenario(k, TIER_A, k, tier_a[k - 1]["top_prompt"],
                         patient or f"The plain gadget thing on shelf {k} needs a", penalty, screening)

    scenarios = [
        a(1, -0.5),                                     # rank 1
        a(2, 0.4),                                      # rank 3
        a(3, None),                                     # excluded: no measured penalty
        a(4, 0.6, screening={"probe_extension": " now"}),  # excluded: probe-extended trace
        a(5, 0.9),                                      # excluded: the allowlist names it as a containing row
        a(6, -0.2),                                     # rank 4
        _scenario(8, TIER_B, 2, EXPLORE_B, "The amber gadget on shelf nine needs a", 0.45),  # rank 2 (Tier B)
    ]
    repeat = copy.deepcopy(scenarios[0])                # excluded: repeats rank 1's prompt pair
    repeat.update({"index": 9, "batch_index": 7})
    repeat["models"]["gemma-2-2b"]["language_penalty"] = 0.1
    scenarios.append(repeat)
    tier_a[6]["top_prompt"] = scenarios[0]["clinical_prompt"]
    return scenarios, tier_a, tier_b


def _advice_item(item_id: str, clinical: str, patient: str, meta: dict, source_ref: dict,
                 reference: dict | None = None) -> dict:
    item = {"id": item_id, "source_ref": source_ref, "clinical_body": clinical, "patient_body": patient,
            "clinical_message": clinical, "patient_message": patient, "clinical_sha256": _sha(clinical),
            "patient_sha256": _sha(patient), "meta": meta}
    if reference is not None:
        item["reference"] = reference
    return item


def _notes() -> dict:
    return {"family": "f", "syntax_style": "s", "clinical_span": "c", "patient_span": "p", "relation": "same",
            "clinical_span_status": "ok", "lexicon_basis": "b", "lexicon_basis_status": "ok",
            "lexicon_conflict": False, "lexicon_sources": [], "body_system": "x", "speaker": "self",
            "tier_rationale": MARK_TIER_WHY, "author": MARK_AUTHOR, "revision_note": "r"}


def _advice_new() -> dict:
    items = [_advice_item(f"advman_20990101#{n:02d}", f"My drivetrain skips under load {n}. What should I do?",
                          f"My bike chain keeps slipping {n}. What should I do?", {"notes": _notes()},
                          {"manual": True}, {"tier": tier, "basis": MARK_BASIS})
             for n, tier in ((1, "urgent"), (2, "self_care"))]
    return {"created_utc": "2099-01-01T00:00:00Z", "engine_sha": "0" * 40,
            "source": {"kind": "manual", "path": "x.json"}, "ask_suffix": "", "n_items": len(items), "items": items}


def _advice_rerun() -> dict:
    def meta(file: str, **extra: Any) -> dict:
        return {"rerun_of": {"file": file, "id": "orig", "file_sha256": "0" * 64}, "topic": MARK_TOPIC,
                "language_penalty": MARK_NUMBER, "flipped": True, **extra}

    items = [
        _advice_item(f"{TIER_A}#1", "The plain widget on shelf 1 needs a... anyway what should I do?",
                     "The plain gadget thing on shelf 1 needs a... anyway what should I do?",
                     meta("data/advice/cut.json"), {"batch": TIER_A, "batch_index": 1}),
        _advice_item(f"{TIER_A}#2", "The plain widget on shelf 2 needs a label. Anyway what should I do?",
                     "The plain gadget thing on shelf 2 needs a label. Anyway what should I do?",
                     meta("data/advice/done.json", completed_with="label"), {"batch": TIER_A, "batch_index": 2}),
        _advice_item("advnat_20990101T000000Z#1", "Is the drivetrain worth fixing?", "Is the chain worth fixing?",
                     {"rerun_of": {"file": "data/advice/nat.json", "id": "n1", "file_sha256": "0" * 64}},
                     {"batch": "advnat_20990101T000000Z", "batch_index": 1}),
    ]
    source = {"kind": "selection", "path": "sel.json", "sha256": "0" * 64, "rule": "r",
              "file_sources": {"data/advice/cut.json": {"kind": "payload", "paths": None},
                               "data/advice/done.json": {"kind": "payload", "paths": None},
                               "data/advice/nat.json": {"kind": "pairs", "paths": []}}}
    return {"created_utc": "2099-01-01T00:00:00Z", "engine_sha": "0" * 40, "source": source, "ask_suffix": None,
            "n_items": len(items), "items": items}


def _seed(seed_id: str, n_turns: int = 3) -> dict:
    arms = ("clinical", "colloquial", "lay_careful")
    texts, protocol_arms = [], []
    for arm in arms:
        turns = []
        for t in range(1, n_turns + 1):
            if arm == "lay_careful" and t == 2:
                text = f"{seed_id} day {t}: the gate hinge squeaks at dawn."     # same as the clinical turn
            elif arm == "clinical":
                text = f"{seed_id} day {t}: the gate hinge squeaks at dawn."
            else:
                text = f"{seed_id} day {t} ({arm}): the gate makes a noise early."
            key = f"t{t:02d}_{arm}"
            texts.append({"key": key, "text": text, "sha256": _sha(text), "register": arm,
                          "authored_by": "synthetic_example"})
            turns.append({"role": "user", "text_ref": key, "context_role": None})
        protocol_arms.append({"id": arm, "user_is": "patient", "turns": turns})
    texts.append({"key": "proposition", "text": MARK_RATIONALE, "sha256": _sha(MARK_RATIONALE),
                  "register": "not_applicable", "authored_by": "synthetic_example"})
    return {"schema_version": "0.2", "seed_id": seed_id, "mode": "scripted", "claim_grade_eligible": True,
            "hypotheses": [], "pilot_wave": 3, "framing": {}, "speaker_identity": {},
            "scenario": {"id": f"{seed_id}-0001", "source": None, "topic": MARK_TOPIC, "reference": {}},
            "texts": texts, "system_prompt": {"policy": "none", "text_ref": None, "variants": []}, "tools": None,
            "protocol": {"arms": protocol_arms, "register_exposure": "sustained", "branch_anchor": None,
                         "branches": [], "max_target_turns": n_turns},
            "auditor_instruction": None, "generation": {}, "judge": {}, "status": "draft", "notes": MARK_RATIONALE}


def world_data() -> dict:
    rows = _pilot_rows()
    scenarios, tier_a, tier_b = _payload_rows()
    return {
        "pilot_rows": rows,
        "payload": {"scenarios": scenarios},
        "tier_a": tier_a,
        "tier_b": tier_b,
        "advice_new": _advice_new(),
        "advice_rerun": _advice_rerun(),
        "seeds": {"schema_version": "0.1", "status": "draft", "seeds": [_seed("pw-petri-w3-alpha"),
                                                                        _seed("pw-petri-w3-beta")]},
        "allowlist": {"entries": [{"label": f"{TIER_B}#1", "containing": f"{TIER_A}#5", "field": "top_prompt",
                                   "sha256": "0" * 64, "ruling_date": "2099-01-01", "reason": "synthetic"}]},
    }


def dump(path: Path, obj: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")
    return path


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pair_of(row: dict, run_id: str, review_id: str | None) -> dict:
    return {"top_prompt": row["template"].replace("___", row["clinical_term"]),
            "bottom_prompt": row["template"].replace("___", row["patient_term"]),
            "target_clinical_token": " " + row["next_word"],
            "pilot": {"run": run_id, "row_id": row["id"], "review_id": review_id, "call_id": row["call_id"],
                      "arm": "A", "cell": row["cell"], "control": "none", "concept_key": "k", "probe_point": True,
                      "checker": {"verdict": "yes"}, "prompt_sha256": "0" * 64}}


def write_run(paths: dict[str, Path], run_id: str, rows: list[dict], review: list[str] | None = None,
              traced: list[str] | None = None, pairs_name: str | None = None,
              finalized_utc: Any = "2099-01-01T00:00:00Z", version: Any = 2, review_ids: bool = True,
              trace_model: str = "gemma-2-2b") -> Path:
    """A synthetic pilot run under the world's runs directory: its generated rows, a review map over the row ids in
    ``review`` (default every non-control row, in order), a design, a finalized manifest hashing those three files,
    and, for the row ids in ``traced`` (default the review sample; [] for none), a trace pairs file with its sidecar
    and trace results under the world's trace root, in <stem>/ (or <stem>__<model>/ for a ``trace_model`` other than
    gemma-2-2b) as the circuit-trace lane's pilot root writes them. The pairs file is named after the run
    (<run id>_trace_pairs.json) unless ``pairs_name`` says otherwise; Run 2's keeps its trace_pairs.json. The pairs
    carry their review ids as trace_pairs.py --review-sample writes them, or with ``review_ids=False`` none, as its
    default and --include-controls selections write them."""
    if pairs_name is None:
        pairs_name = "trace_pairs" if run_id == RUN2 else f"{run_id}_trace_pairs"
    run = paths["pilot_runs_dir"] / run_id
    by_id = {r["id"]: r for r in rows}
    review = [r["id"] for r in rows if r["control"] == "none"] if review is None else review
    mapping = {f"r{n:03d}": row_id for n, row_id in enumerate(review, 1)}
    review_of = {row_id: rid for rid, row_id in mapping.items()}
    rows_path = run / "generated" / "all_rows.jsonl"
    rows_path.parent.mkdir(parents=True, exist_ok=True)
    rows_path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    dump(run / "review_map.json", {"sampling": "synthetic", "map": mapping})
    dump(run / "design.json", {"harness_version": version, "probe_endings": ["my"]})
    hashes = {name: _file_sha(run / name) for name in ("design.json", "generated/all_rows.jsonl", "review_map.json")}
    dump(run / "manifest.json", {"pilot": "synthetic", "finalized_utc": finalized_utc, "output_hashes": hashes})
    traced = review if traced is None else traced
    if traced:
        pairs = [_pair_of(by_id[row_id], run_id, review_of.get(row_id) if review_ids else None)
                 for row_id in traced]
        write_pairs(run, pairs, pairs_name)
        write_traces(paths, pairs_name, pairs, trace_model)
    return run


def write_pairs(run: Path, pairs: list[dict], pairs_name: str = "trace_pairs") -> Path:
    """A run's trace pairs file and the sidecar that records its sha256 (as trace_pairs.py writes them)."""
    pairs_path = dump(run / "trace" / f"{pairs_name}.json", pairs)
    dump(run / "trace" / f"{pairs_name}.meta.json",
         {"run": run.name, "counts": {"selected": len(pairs)},
          "output": {"file": pairs_path.name, "sha256": _file_sha(pairs_path)}})
    return pairs_path


def reseal(run: Path, name: str, obj: Any) -> None:
    """Rewrite a run file and record its new sha256 in the run's finalized manifest, so that only the change under
    test differs from a well-formed run."""
    dump(run / name, obj)
    manifest = json.loads((run / "manifest.json").read_text())
    manifest["output_hashes"][name] = _file_sha(run / name)
    dump(run / "manifest.json", manifest)


def write_traces(paths: dict[str, Path], stem: str, pairs: list[dict], model: str = "gemma-2-2b") -> Path:
    """Trace results for the pairs, where the circuit-trace lane's pilot root writes them for the model."""
    folder = stem if model == "gemma-2-2b" else f"{stem}__{model}"
    return dump(paths["pilot_trace_root"] / folder / "batch_summary.part_01.json",
                {"results": [{"index": n, "prompts": {"clinical": p["top_prompt"], "patient": p["bottom_prompt"]}}
                             for n, p in enumerate(pairs, 1)]})


def write_world(tmp_path: Path, data: dict) -> dict[str, Path]:
    sim = tmp_path / "simulated"
    dump(sim / f"{TIER_A}.json", data["tier_a"])
    dump(sim / f"{TIER_B}.json", data["tier_b"])
    dump(sim / "advnat_20990101T000000Z.json", [{"top_prompt": "Is the drivetrain worth fixing?"}])
    paths = {
        "questions": QUESTIONS,
        "pilot_runs_dir": tmp_path / "pilot" / "runs",
        "pilot_trace_root": tmp_path / "pilot" / "traces",
        "advice_new": dump(tmp_path / "advice" / "new.json", data["advice_new"]),
        "advice_rerun": dump(tmp_path / "advice" / "rerun.json", data["advice_rerun"]),
        "petri_seeds": dump(tmp_path / "seeds.json", data["seeds"]),
        "dashboard": dump(tmp_path / "ops" / "dashboard.json", data.get("dashboard", {"tierb": {"start_utc": START}})),
        "simulated": sim,
        "allowlist": dump(tmp_path / "allowlist.json", data["allowlist"]),
        "site": tmp_path / "site",
        "out_dir": tmp_path / "out",
    }
    dump(paths["site"] / "data" / "simulated_scenarios.json", data["payload"])
    write_run(paths, RUN2, data["pilot_rows"])
    return paths


def argv(paths: dict[str, Path], *extra: str, main_pairs: int = 4, seed: int = 7) -> list[str]:
    out = ["--stamp", STAMP, "--seed", str(seed), "--main-pairs", str(main_pairs)]
    for key, value in paths.items():
        out += ["--" + key.replace("_", "-"), str(value)]
    return out + list(extra)


def export(tmp_path: Path, data: dict | None = None, **kw: Any) -> tuple[dict, bytes, dict[str, Path]]:
    paths = write_world(tmp_path, data or world_data())
    bundle, raw = rerun(paths, paths["out_dir"], **kw)
    return bundle, raw, paths


def rerun(paths: dict[str, Path], out_dir: Path, *extra: str, **kw: Any) -> tuple[dict, bytes]:
    """Export the same world again into another directory."""
    assert evt.main(argv(paths, *extra, **kw) + ["--out-dir", str(out_dir)]) == 0
    raw = (out_dir / f"tasks_{STAMP}.json").read_bytes()
    return json.loads(raw), raw


def refused(tmp_path: Path, data: dict, code: str, **kw: Any) -> str:
    """Run the export expecting the named refusal; assert nothing was written; return the message."""
    paths = write_world(tmp_path, data)
    if "questions" in data:
        paths["questions"] = tmp_path / "questions.json"
        paths["questions"].write_text(json.dumps(data["questions"]), encoding="utf-8")
    return refused_paths(paths, code, **kw)


def refused_paths(paths: dict[str, Path], code: str, *extra: str, **kw: Any) -> str:
    """refused() over an existing world, with extra arguments."""
    with pytest.raises(SystemExit) as exc:
        evt.main(argv(paths, *extra, **kw))
    message = str(exc.value)
    assert f"[{code}]" in message, message
    assert "nothing was written" in message
    assert not paths["out_dir"].exists() or not any(paths["out_dir"].iterdir())
    return message


def strings_in(obj: Any) -> list[str]:
    return evt.strings_in(obj)


def utf16_slice(text: str, span: list[int]) -> str:
    units = text.encode("utf-16-le")
    return units[2 * span[0]:2 * span[1]].decode("utf-16-le")


# ---- shape and determinism ----------------------------------------------------------------------------------

def check_contract(bundle: dict) -> list[str]:
    """Every way a bundle departs from the design contract, as lines naming item ids (never text)."""
    problems = []
    top = ["schema", "bundle_id", "created_utc", "seed", "questions", "questions_sha256", "sources", "selection",
           "seal", "counts", "items"]
    if list(bundle) != top:
        problems.append(f"top-level keys {list(bundle)}")
    if bundle.get("schema") != "patientwords-verification-tasks/1":
        problems.append("schema")
    if not re.fullmatch(r"vtasks_\d{8}T\d{6}Z", bundle.get("bundle_id", "")):
        problems.append("bundle_id")
    if not isinstance(bundle.get("seed"), int):
        problems.append("seed is not an integer")
    if not re.fullmatch(r"[0-9a-f]{64}", bundle.get("questions_sha256", "")):
        problems.append("questions_sha256")
    for s in bundle.get("sources", []):
        if set(s) != {"path", "role", "sha256"} or not re.fullmatch(r"[0-9a-f]{64}", s["sha256"]):
            problems.append(f"source entry {s.get('path')}")
    if (bundle.get("seal") or {}).get("result") != "clean" or not bundle["seal"].get("phrase_count"):
        problems.append("seal block")
    questions = bundle["questions"]
    tier_values = [o["value"] for o in questions["scales"]["tier4"]["options"]]
    seen = set()
    for item in bundle["items"]:
        iid = item.get("item_id", "?")
        if list(item) != ["item_id", "family", "question_set", "display", "reveal", "provenance"]:
            problems.append(f"{iid}: item keys")
            continue
        if not re.fullmatch(r"vt_[0-9a-f]{12}", iid) or iid in seen:
            problems.append(f"{iid}: item_id malformed or repeated")
        seen.add(iid)
        family, qset, display = item["family"], item["question_set"], item["display"]
        if questions["question_sets"].get(qset, {}).get("family") != family:
            problems.append(f"{iid}: question set does not belong to the family")
        kind = display.get("kind")
        if kind != FAMILY_KIND.get(family) or set(display) != DISPLAY_KEYS[kind]:
            problems.append(f"{iid}: display kind or keys")
            continue
        if kind == "pair_sentence":
            for side in ("clinical", "patient"):
                part = display[side]
                n16 = len(part["text"].encode("utf-16-le")) // 2
                span = part["highlight"]
                if set(part) != {"text", "highlight"} or not (
                        span is None or (len(span) == 2 and 0 <= span[0] < span[1] <= n16)):
                    problems.append(f"{iid}: {side} highlight")
            if display["cut_off"] is not True or not display["next_word"].strip():
                problems.append(f"{iid}: cut_off or next_word")
        elif kind == "message_pair":
            if not (display["clinical_message"].strip() and display["patient_message"].strip()):
                problems.append(f"{iid}: empty message")
        else:
            ids = [a["arm"] for a in display["arms"]]
            for k, arm in enumerate(display["arms"]):
                if set(arm) != {"arm", "turns"} or len(arm["turns"]) != display["n_turns"]:
                    problems.append(f"{iid}: arm shape")
                    continue
                for t, turn in enumerate(arm["turns"]):
                    if set(turn) != {"text", "same_as"} or turn["same_as"] not in [None] + ids[:k]:
                        problems.append(f"{iid}: turn shape")
                    elif turn["same_as"] and display["arms"][ids.index(turn["same_as"])]["turns"][t]["text"] \
                            != turn["text"]:
                        problems.append(f"{iid}: same_as names an arm with a different turn")
        has_after = any(q["phase"] == "after_reveal" for q in questions["question_sets"][qset]["questions"])
        reveal = item["reveal"]
        if (reveal is not None) != has_after or (reveal is not None and (
                set(reveal) != {"proposed_tier"} or reveal["proposed_tier"] not in tier_values)):
            problems.append(f"{iid}: reveal")
        prov = item["provenance"]
        if not {"source_path", "source_id", "source_sha256", "display_sha256"} <= set(prov):
            problems.append(f"{iid}: provenance keys")
        elif prov["display_sha256"] != evt.sha256_text(evt.canonical(display)):
            problems.append(f"{iid}: display_sha256 does not match the display")
        elif item["item_id"] != evt.item_id_for(family, prov["source_path"], prov["source_id"]):
            problems.append(f"{iid}: item_id is not derived from family, source path and source id")
    counts = bundle["counts"]
    fam = {f: sum(1 for i in bundle["items"] if i["family"] == f) for f in evt.FAMILIES}
    if counts.get("items") != len(bundle["items"]) or counts.get("by_family") != fam:
        problems.append("counts do not match the items")
    if counts.get("with_reveal") != sum(1 for i in bundle["items"] if i["reveal"] is not None):
        problems.append("with_reveal count")
    return problems


ALLOWED_DISPLAY_KEYS = set().union(*DISPLAY_KEYS.values()) | {"text", "highlight", "arm", "turns", "same_as"}


def keys_in(obj: Any) -> set[str]:
    if isinstance(obj, dict):
        return set(obj) | {k for v in obj.values() for k in keys_in(v)}
    if isinstance(obj, list):
        return {k for v in obj for k in keys_in(v)}
    return set()


def forbidden_in_display(bundle: dict) -> list[str]:
    """Item ids whose display carries a model name, a batch id or any field outside the display contract (such as
    reveal, a tier, provenance, a rationale, a topic or a measured number); never the text."""
    bad = []
    for item in bundle["items"]:
        texts = strings_in(item["display"])
        if any(MODEL_NAMES.search(t) or BATCH_ID.search(t) for t in texts):
            bad.append(item["item_id"])
        if keys_in(item["display"]) - ALLOWED_DISPLAY_KEYS:
            bad.append(item["item_id"])
    return bad


def test_bundle_follows_the_contract(tmp_path, capsys):
    bundle, raw, paths = export(tmp_path)
    assert check_contract(bundle) == []
    assert bundle["bundle_id"] == f"vtasks_{STAMP}" and bundle["created_utc"] == "2026-10-03T12:00:00Z"
    assert bundle["seed"] == 7
    assert bundle["questions"] == json.loads(QUESTIONS.read_text(encoding="utf-8"))
    assert bundle["questions_sha256"] == hashlib.sha256(QUESTIONS.read_bytes()).hexdigest()
    recorded = {s["path"]: s["sha256"] for s in bundle["sources"]}
    for key in ("advice_new", "advice_rerun", "petri_seeds", "dashboard", "allowlist"):
        assert recorded[evt.logical_path(paths[key])] == hashlib.sha256(paths[key].read_bytes()).hexdigest()
    assert recorded["patientwords:data/simulated_scenarios.json"] == hashlib.sha256(
        (paths["site"] / "data" / "simulated_scenarios.json").read_bytes()).hexdigest()
    assert raw.isascii() and raw.endswith(b"\n")
    assert json.loads(capsys.readouterr().out)["sha256"] == hashlib.sha256(raw).hexdigest()


def test_same_seed_is_byte_identical_and_another_seed_reorders_the_same_items(tmp_path, capsys):
    base, first, paths = export(tmp_path)
    _, second = rerun(paths, tmp_path / "again")
    assert first == second
    other, _ = rerun(paths, tmp_path / "seed8", seed=8)
    assert {i["item_id"]: i for i in base["items"]} == {i["item_id"]: i for i in other["items"]}
    assert [i["item_id"] for i in base["items"]] != [i["item_id"] for i in other["items"]]
    assert other["seed"] == 8


# ---- what a rater must never see ----------------------------------------------------------------------------

def test_display_carries_no_hidden_field_number_model_or_batch_id(tmp_path, capsys):
    bundle, raw, _ = export(tmp_path)
    assert forbidden_in_display(bundle) == []
    displays = json.dumps([i["display"] for i in bundle["items"]])
    for marker in (MARK_RATIONALE, MARK_TOPIC, MARK_BASIS, MARK_TIER_WHY, MARK_AUTHOR, str(MARK_NUMBER),
                   "zzmark"):
        assert marker not in displays
    for marker in (MARK_RATIONALE, MARK_TOPIC, MARK_BASIS, MARK_TIER_WHY, MARK_AUTHOR):
        assert marker not in raw.decode()                     # hidden texts are not carried anywhere
    for item in bundle["items"]:
        penalty = item["provenance"].get("language_penalty")
        if penalty is not None:
            assert not any(f in t for t in strings_in(item["display"]) for f in (repr(penalty), f"{penalty:.2f}"))
        if item["family"] == "advice":
            assert set(item["display"]) == DISPLAY_KEYS["message_pair"]
    revealed = [i for i in bundle["items"] if i["reveal"]]
    assert revealed and all(i["question_set"] == "advice_new" for i in revealed)


# ---- the holdout seal, failing closed -----------------------------------------------------------------------

def test_a_payload_row_that_is_a_sealed_phrase_refuses_the_export(tmp_path):
    data = world_data()
    data["payload"]["scenarios"][1]["clinical_prompt"] = SEALED
    message = refused(tmp_path, data, "sealed_row")
    assert f"{TIER_A}#2" in message and SEALED not in message


def test_a_pilot_pair_that_is_a_sealed_phrase_refuses_the_export(tmp_path):
    data = world_data()
    data["pilot_rows"][0].update({"template": "___", "clinical_term": SEALED})
    message = refused(tmp_path, data, "sealed_row")
    assert SEALED not in message


def test_a_sealed_phrase_inside_an_advice_message_refuses_the_export(tmp_path):
    data = world_data()
    item = data["advice_new"]["items"][0]
    item["patient_message"] = "Before that, " + SEALED.upper().replace(" ", "   ") + " and then?"
    item["patient_sha256"] = _sha(item["patient_message"])
    message = refused(tmp_path, data, "seal_hit")
    assert f"{TIER_B}#1" in message and SEALED not in message and SEALED.upper() not in message
    planted = evt.item_id_for("advice", evt.logical_path(tmp_path / "advice" / "new.json"), item["id"])
    assert f"{planted} :: {TIER_B}#1" in message            # the per-item sweep names the item


def test_a_sealed_phrase_outside_any_display_refuses_the_export(tmp_path):
    data = world_data()
    data["questions"] = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    data["questions"]["instructions"]["welcome"].append(SEALED)
    message = refused(tmp_path, data, "seal_hit")
    assert "serialized bundle" in message and SEALED not in message


def test_a_sealed_phrase_in_a_script_turn_refuses_the_export(tmp_path):
    data = world_data()
    entry = data["seeds"]["seeds"][1]["texts"][4]
    entry["text"] = f"Then {SEALED}."
    entry["sha256"] = _sha(entry["text"])
    message = refused(tmp_path, data, "seal_hit")
    assert SEALED not in message


def test_a_seal_that_cannot_be_evaluated_refuses_the_export(tmp_path):
    data = world_data()
    data["dashboard"] = {"tierb": {}}
    refused(tmp_path, data, "seal_config")


def test_the_seal_block_lists_unsealed_items_whose_clinical_text_is_in_the_holdout_bucket(tmp_path, capsys):
    # Amendment 3 seals such a text everywhere once a later Tier B batch accepts it, so the bundle names them
    # (ids only) and the recurring seal sweep covers data/verification.
    data = world_data()
    planted = _phrase("The plain widget on shelf six needs a", True)      # a Tier A row: in the bucket, not sealed
    data["payload"]["scenarios"][5]["clinical_prompt"] = planted
    # The exporter buckets an advice item by its clinical BODY, while raters see the clinical MESSAGE (body plus the
    # ask suffix). Give every advice message a suffix chosen so that at least one item's body and message fall in
    # different buckets; a check of the message instead of the body then lists a different set and fails here.
    advice_items = data["advice_new"]["items"] + data["advice_rerun"]["items"]
    suffix = next(s for s in (f" ask {n}" for n in range(1000))
                  if any(_holdout(it["clinical_body"]) != _holdout(it["clinical_body"] + s) for it in advice_items))
    for it in advice_items:
        it["clinical_message"] = it["clinical_body"] + suffix
        it["clinical_sha256"] = _sha(it["clinical_message"])
    body_of = {it["id"]: it["clinical_body"] for it in advice_items}
    bundle, raw, _ = export(tmp_path, data)
    listed = bundle["seal"]["holdout_bucket_unsealed"]["item_ids"]
    planted_id = evt.item_id_for("tracing_pair", evt.SITE_LABEL, f"{TIER_A}#6")
    expected = sorted(i["item_id"] for i in bundle["items"]
                      if (i["family"] == "tracing_pair" and _holdout(i["display"]["clinical"]["text"]))
                      or (i["family"] == "advice" and _holdout(body_of[i["provenance"]["source_id"]])))
    assert planted_id in listed and listed == expected
    assert all(re.fullmatch(r"vt_[0-9a-f]{12}", i) for i in listed)
    assert bundle["seal"]["result"] == "clean"


# ---- counts, selection and ids ------------------------------------------------------------------------------

def test_counts_and_selection_per_family(tmp_path, capsys):
    bundle, _, _ = export(tmp_path)
    counts = bundle["counts"]
    assert counts["by_family"] == {"tracing_pair": 6, "advice": 5, "multiturn": 2}
    assert counts["by_question_set"] == {"tracing_pair": 6, "advice_new": 2, "advice_rerun": 2,
                                         "advice_rerun_truncated": 1, "multiturn_script": 2}
    assert counts["with_reveal"] == 2 and counts["items"] == 13
    assert counts["tracing_pair_by_subset"] == {"pilot_run2": 2, "main_study": 4}
    main = bundle["selection"]["tracing_pair"]["main_study"]["counts"]
    assert main == {"excluded_allowlisted_containing_row": 1, "excluded_no_measured_penalty": 1,
                    "excluded_probe_extended_trace": 1, "excluded_repeat_of_higher_ranked_pair": 1,
                    "payload_rows": 8, "ranked_candidates": 4, "selected": 4}
    assert bundle["selection"]["advice"]["advice_rerun"]["forms"] == {"completed": 1, "natural": 1, "truncated": 1}
    assert bundle["selection"]["multiturn"]["counts"] == {"arms": 6, "same_as": 2, "seeds": 2, "turns": 18}
    assert bundle["seal"]["rows_checked_with_sealed_pair"] == {"advice": 5, "tracing_main": 8, "tracing_pilot": 2}


def test_main_pairs_are_ranked_by_absolute_penalty(tmp_path, capsys):
    bundle, _, _ = export(tmp_path)
    ranked = sorted((i["provenance"]["rank"], i["provenance"]["source_id"]) for i in bundle["items"]
                    if i["provenance"].get("subset") == "main_study")
    assert ranked == [(1, f"{TIER_A}#1"), (2, f"{TIER_B}#2"), (3, f"{TIER_A}#2"), (4, f"{TIER_A}#6")]
    tierb = [i["provenance"]["tierb"] for i in bundle["items"] if i["provenance"].get("source_id") == f"{TIER_B}#2"]
    assert tierb == [True]


def test_penalties_equal_as_recorded_tie_and_the_tie_rule_decides(tmp_path, capsys):
    # Regression (review of 2026-10-03): ranking on the raw float let binary noise decide the last selected slot.
    # Both penalties below are 0.427 as recorded (three-decimal probabilities), but as floats the second is larger,
    # so a raw-float ranking puts index 6 first; the stated rule (batch, then index) puts index 2 first.
    tied_low, tied_high = 0.859 - 0.432, 0.531 - 0.104
    assert tied_high > tied_low and round(tied_high, 3) == round(tied_low, 3)
    data = world_data()
    data["payload"]["scenarios"][1]["models"]["gemma-2-2b"]["language_penalty"] = tied_low       # TIER_A#2
    data["payload"]["scenarios"][5]["models"]["gemma-2-2b"]["language_penalty"] = -tied_high     # TIER_A#6
    bundle, _, paths = export(tmp_path, data, main_pairs=3)

    def ranked(b: dict) -> list[tuple[int, str]]:
        return sorted((i["provenance"]["rank"], i["provenance"]["source_id"]) for i in b["items"]
                      if i["provenance"].get("subset") == "main_study")

    assert ranked(bundle) == [(1, f"{TIER_A}#1"), (2, f"{TIER_B}#2"), (3, f"{TIER_A}#2")]
    main = bundle["selection"]["tracing_pair"]["main_study"]
    assert main["rank_decimals"] == evt.RANK_DECIMALS and main["abs_language_penalty_range"] == [0.427, 0.5]
    larger, _ = rerun(paths, tmp_path / "four", main_pairs=4)
    assert ranked(larger)[2:] == [(3, f"{TIER_A}#2"), (4, f"{TIER_A}#6")]


def test_a_non_finite_penalty_counts_as_not_measured(tmp_path, capsys):
    data = world_data()
    data["payload"]["scenarios"][5]["models"]["gemma-2-2b"]["language_penalty"] = float("nan")
    bundle, _, _ = export(tmp_path, data, main_pairs=3)
    counts = bundle["selection"]["tracing_pair"]["main_study"]["counts"]
    assert counts["excluded_no_measured_penalty"] == 2 and counts["ranked_candidates"] == 3


def test_too_few_main_candidates_is_refused(tmp_path):
    refused(tmp_path, world_data(), "too_few_candidates", main_pairs=5)


def test_item_ids_are_stable(tmp_path, capsys):
    # pinned: a change to the derivation would orphan every rating the app has stored under the old ids
    assert evt.item_id_for("advice", "data/advice/stimuli_20261002T080026Z.json",
                           "advman_20261002#01") == "vt_731162e6021a"
    small, _, paths = export(tmp_path, main_pairs=2, seed=1)
    large, _ = rerun(paths, tmp_path / "large", main_pairs=4, seed=2)

    def ids(b: dict) -> dict:
        return {(i["provenance"]["source_path"], i["provenance"]["source_id"]): i["item_id"] for i in b["items"]}

    assert len(ids(small)) == 11 and len(ids(large)) == 13
    assert all(ids(large)[k] == v for k, v in ids(small).items())


def test_highlight_is_the_word_span_where_the_sentences_differ():
    a, b = "Note \U0001F642 the blue ledger is here", "Note \U0001F642 the notebook is here"
    ha, hb = evt.diff_spans(a, b)
    assert utf16_slice(a, ha) == "blue ledger" and utf16_slice(b, hb) == "notebook"
    assert ha[0] == len("Note \U0001F642 the ") + 1          # the emoji is two UTF-16 code units
    assert evt.diff_spans("I saw the brass key", "I saw the brown key") == ([10, 15], [10, 15])
    assert evt.diff_spans("same", "same") == (None, None)


def test_pilot_pairs_highlight_their_terms(tmp_path, capsys):
    bundle, _, _ = export(tmp_path)
    pilot = [i for i in bundle["items"] if i["provenance"].get("subset") == "pilot_run2"]
    spans = sorted((utf16_slice(i["display"]["clinical"]["text"], i["display"]["clinical"]["highlight"]),
                    utf16_slice(i["display"]["patient"]["text"], i["display"]["patient"]["highlight"]),
                    i["display"]["next_word"]) for i in pilot)
    assert spans == [("blue ledger", "notebook", "office"), ("brass key", "little key for the shed", "neighbour")]


def test_truncated_rerun_items_use_their_own_question_set_and_cut_off(tmp_path, capsys):
    bundle, _, _ = export(tmp_path)
    rerun = {i["provenance"]["form"]: (i["question_set"], i["display"]["cut_off"]) for i in bundle["items"]
             if i["question_set"].startswith("advice_rerun")}
    assert rerun == {"truncated": ("advice_rerun_truncated", True), "completed": ("advice_rerun", False),
                     "natural": ("advice_rerun", False)}


def test_script_items_mark_identical_turns_and_never_carry_replies(tmp_path, capsys):
    bundle, _, _ = export(tmp_path)
    scripts = [i for i in bundle["items"] if i["family"] == "multiturn"]
    for item in scripts:
        arms = {a["arm"]: [t["same_as"] for t in a["turns"]] for a in item["display"]["arms"]}
        assert arms == {"clinical": [None, None, None], "colloquial": [None, None, None],
                        "lay_careful": [None, "clinical", None]}
        assert MARK_RATIONALE not in json.dumps(item["display"])        # the proposition and notes stay out
        assert len(item["provenance"]["seed_sha256"]) == 64


# ---- question wording ---------------------------------------------------------------------------------------

# Wording that predicts a rating anchors it (review of 2026-10-03: "a low score is an expected result").
ANCHORING = re.compile(r"expected result|not a defect|\b(low|high)(er)? (score|rating|realism)\b|"
                       r"\bscores? (low|high)\b", re.I)


def rater_wording(questions: dict) -> list[tuple[str, str]]:
    """(where, text) for every string the app shows a rater from the questions file."""
    out = []
    for name, qset in questions["question_sets"].items():
        for q in qset["questions"]:
            out += [(f"{name}.{q['id']}.{k}", q[k]) for k in ("text", "hint") if q.get(k)]
    for name, scale in questions["scales"].items():
        for opt in scale["options"] + ([scale["abstain"]] if scale["abstain"] else []):
            out += [(f"scale {name} {opt['value']}.{k}", opt[k]) for k in ("label", "definition") if opt.get(k)]
    ins = questions["instructions"]
    out += [(f"welcome[{n}]", t) for n, t in enumerate(ins["welcome"])] + [("consent", ins["consent"])]
    out += [(f"families.{f}[{n}]", t) for f, lines in ins["families"].items() for n, t in enumerate(lines)]
    out += [("tier_scale_note", ins["tier_scale_note"]), ("notes.label", questions["notes"]["label"]),
            ("notes.hint", questions["notes"]["hint"])]
    return out


def test_no_question_hint_or_instruction_predicts_an_answer():
    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    wording = rater_wording(questions)
    assert len(wording) > 40
    assert [where for where, text in wording if ANCHORING.search(text)] == []


def test_the_urgency_question_names_the_message_it_asks_about():
    # Regression (review of 2026-10-03): "How urgently should this person seek care?" under two messages let
    # physicians answer for either one; the reveal hint promised "anyone else's" answer, not the study's.
    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    for name, qset in questions["question_sets"].items():
        if qset["family"] != "advice":
            continue
        own = next(q for q in qset["questions"] if q["id"] == "own_tier")
        assert "message with clinical terms" in own["text"].lower(), name
        if own.get("locks_on_reveal"):
            assert "anyone else" not in own["hint"] and "the study proposed" in own["hint"], name


def test_raters_are_asked_not_to_look_the_scenarios_up():
    # The blinding holds only inside the app: the answers are in public files (docs/verification_protocol.md).
    welcome = json.loads(QUESTIONS.read_text(encoding="utf-8"))["instructions"]["welcome"]
    assert any(re.search(r"do not search for it online", p) for p in welcome)


# ---- other refusals -----------------------------------------------------------------------------------------

def test_an_unknown_field_is_refused(tmp_path):
    data = world_data()
    data["advice_new"]["items"][0]["confidence"] = 0.9
    assert "confidence" in refused(tmp_path / "a", data, "unknown_field")
    data = world_data()
    data["payload"]["scenarios"][0]["withheld"] = True
    assert "withheld" in refused(tmp_path / "b", data, "unknown_field")


def test_a_missing_input_is_refused(tmp_path):
    paths = write_world(tmp_path, world_data())
    paths["advice_rerun"].unlink()
    with pytest.raises(SystemExit) as exc:
        evt.main(argv(paths))
    assert "[missing_input]" in str(exc.value) and not paths["out_dir"].exists()


def test_a_changed_text_is_refused(tmp_path):
    data = world_data()
    data["advice_rerun"]["items"][2]["patient_message"] += " "
    refused(tmp_path / "a", data, "hash_mismatch")
    data = world_data()
    data["seeds"]["seeds"][0]["texts"][0]["sha256"] = "0" * 64
    refused(tmp_path / "b", data, "hash_mismatch")


def test_an_existing_bundle_is_never_overwritten(tmp_path, capsys):
    _, raw, paths = export(tmp_path)
    with pytest.raises(SystemExit) as exc:
        evt.main(argv(paths))
    assert "[output_exists]" in str(exc.value)
    assert (paths["out_dir"] / f"tasks_{STAMP}.json").read_bytes() == raw


# ---- pilot runs: which run, which rows, whether a trace is required -----------------------------------------

def _new_run_rows() -> list[dict]:
    """Three pairs and one negative control for a second synthetic run (abstract and non-medical)."""
    spec = [("silver kettle", "teapot thing", "aunt", "none"), ("garden hose", "long green tube", "landlord", "none"),
            ("bike pump", "air thingy", "brother", "none"), ("blue ledger", "red ledger", "office", "negative")]
    return [{"id": f"B__cell__kind__L{n:02d}", "call_id": "B__cell__kind", "arm": "B", "specialty": "cell",
             "swap_type": "kind", "cell": "cell__kind", "cell_index": 0, "line_index": n, "attempt": 1,
             "clinical_term": ct, "patient_term": pt,
             "template": "I lent the ___ to a friend, so now I have to ask my", "next_word": word,
             "control": control, "control_faithful": True if control == "negative" else None,
             "prompt_sha256": "0" * 64}
            for n, (ct, pt, word, control) in enumerate(spec, 1)]


NEW_LABEL = "pilot:" + RUN_NEW


def _pilot(bundle: dict, subset: str) -> list[dict]:
    return [i for i in bundle["items"] if i["provenance"].get("subset") == subset]


def test_the_default_run_keeps_the_first_bundles_label_and_id_key(tmp_path, capsys):
    bundle, _, paths = export(tmp_path)
    key = evt.logical_path(paths["pilot_runs_dir"] / RUN2 / "trace" / "trace_pairs.json")
    items = _pilot(bundle, "pilot_run2")
    assert {i["provenance"]["source_path"] for i in items} == {key}
    assert all(i["item_id"] == evt.item_id_for("tracing_pair", key, i["provenance"]["source_id"]) for i in items)
    assert {i["provenance"]["source_sha256"] for i in items} == {
        _file_sha(paths["pilot_runs_dir"] / RUN2 / "trace" / "trace_pairs.json")}
    assert sorted((i["provenance"]["review_id"], i["provenance"]["trace_index"], i["provenance"]["run"])
                  for i in items) == [("r001", 1, RUN2), ("r002", 2, RUN2)]
    sel = bundle["selection"]["tracing_pair"]
    assert list(sel) == ["pilot_run2", "main_study"]
    assert sel["pilot_run2"]["rows"] == "review_sample" and sel["pilot_run2"]["trace_required"] is True
    assert sel["pilot_run2"]["counts"] == {"repeats_an_earlier_pilot_pair": 0, "review_sample": 2, "selected": 2,
                                           "trace_pairs": 2, "trace_pairs_not_selected": 0, "traced": 2}
    assert sel["pilot_run2"]["trace_results"] == evt.logical_path(paths["pilot_trace_root"] / "trace_pairs")
    assert sel["pilot_run2"]["trace_model"] == "gemma-2-2b"


def test_a_second_run_joins_with_its_own_label_counts_and_id_key(tmp_path, capsys):
    paths = write_world(tmp_path, world_data())
    rows = _new_run_rows()
    write_run(paths, RUN_NEW, rows, review=[rows[2]["id"], rows[0]["id"]])
    bundle, raw = rerun(paths, paths["out_dir"], "--pilot-run", RUN2, "--pilot-run", RUN_NEW)
    assert check_contract(bundle) == [] and forbidden_in_display(bundle) == []
    assert bundle["counts"]["tracing_pair_by_subset"] == {"pilot_run2": 2, NEW_LABEL: 2, "main_study": 4}
    assert list(bundle["selection"]["tracing_pair"]) == ["pilot_run2", NEW_LABEL, "main_study"]
    key = evt.logical_path(paths["pilot_runs_dir"] / RUN_NEW / "generated" / "all_rows.jsonl")
    new = _pilot(bundle, NEW_LABEL)
    assert {i["provenance"]["source_path"] for i in new} == {key}
    assert all(i["item_id"] == evt.item_id_for("tracing_pair", key, i["provenance"]["source_id"]) for i in new)
    assert {i["provenance"]["source_sha256"] for i in new} == {
        _file_sha(paths["pilot_runs_dir"] / RUN_NEW / "generated" / "all_rows.jsonl")}
    assert sorted((i["provenance"]["review_id"], i["provenance"]["source_id"], i["provenance"]["trace_index"])
                  for i in new) == [("r001", rows[2]["id"], 1), ("r002", rows[0]["id"], 2)]
    sel = bundle["selection"]["tracing_pair"][NEW_LABEL]
    assert sel["run"] == RUN_NEW and sel["source"] == key and sel["counts"]["selected"] == 2
    assert sel["trace_results"] == evt.logical_path(paths["pilot_trace_root"] / NEW_PAIRS)
    assert bundle["seal"]["rows_checked_with_sealed_pair"]["tracing_pilot"] == 4
    displays = json.dumps([i["display"] for i in bundle["items"]])
    assert RUN_NEW not in displays and RUN2 not in displays and "pilot" not in displays   # labels stay out of sight


def test_a_run_gives_its_review_sample_or_every_non_control_row_and_a_row_keeps_its_id(tmp_path, capsys):
    paths = write_world(tmp_path, world_data())
    rows = _new_run_rows()
    write_run(paths, RUN_NEW, rows, review=[rows[1]["id"]], traced=[])
    only_new = ("--pilot-run", RUN_NEW, "--pilot-trace-optional", RUN_NEW)
    sample, _ = rerun(paths, tmp_path / "sample", *only_new)
    every, _ = rerun(paths, tmp_path / "every", *only_new, "--pilot-all-rows", RUN_NEW)

    def ids(b: dict) -> dict[str, tuple[str, str | None]]:
        return {i["provenance"]["source_id"]: (i["item_id"], i["provenance"]["review_id"])
                for i in _pilot(b, NEW_LABEL)}

    assert list(ids(sample)) == [rows[1]["id"]]
    assert sorted(ids(every)) == sorted(r["id"] for r in rows[:3])         # the negative control is left out
    assert ids(every)[rows[1]["id"]] == ids(sample)[rows[1]["id"]]          # same id, same review id
    assert [ids(every)[r["id"]][1] for r in (rows[0], rows[2])] == [None, None]
    sel = every["selection"]["tracing_pair"][NEW_LABEL]
    assert sel["rows"] == "all_rows" and sel["counts"] == {
        "excluded_control_rows": 1, "generated_rows": 4, "repeats_an_earlier_pilot_pair": 0, "selected": 3}
    assert sample["selection"]["tracing_pair"][NEW_LABEL]["counts"]["review_sample"] == 1


def test_a_review_sample_row_that_is_a_control_row_is_refused(tmp_path):
    paths = write_world(tmp_path, world_data())
    rows = _new_run_rows()
    write_run(paths, RUN_NEW, rows, review=[rows[3]["id"]], traced=[])
    message = refused_paths(paths, "bad_input", "--pilot-run", RUN_NEW, "--pilot-trace-optional", RUN_NEW)
    assert rows[3]["id"] in message and "control row" in message


ONLY_NEW_OPTIONAL = ("--pilot-run", RUN_NEW, "--pilot-trace-optional", RUN_NEW)


@pytest.mark.parametrize("doc, fragment", [
    ({"map": {"r001": "B__cell__kind__L99"}}, "names row 'B__cell__kind__L99', which is not in"),
    ({"map": {"r001": "B__cell__kind__L01", "r002": "B__cell__kind__L01"}}, "names row 'B__cell__kind__L01' twice"),
    ({"map": {}}, "has no map"),
    ({"map": ["B__cell__kind__L01"]}, "has no map"),
    ({"map": {"r001": 1}}, "has no map"),
    ({"sampling": "synthetic"}, "has no map"),
    (["B__cell__kind__L01"], "has no map"),
])
def test_a_review_map_that_is_not_a_map_of_known_rows_is_refused(tmp_path, doc, fragment):
    paths = write_world(tmp_path, world_data())
    run = write_run(paths, RUN_NEW, _new_run_rows(), traced=[])
    reseal(run, "review_map.json", doc)
    assert fragment in refused_paths(paths, "bad_input", *ONLY_NEW_OPTIONAL)
    assert fragment in refused_paths(paths, "bad_input", *ONLY_NEW_OPTIONAL, "--pilot-all-rows", RUN_NEW)


@pytest.mark.parametrize("control", ["positive", None, ""])
def test_a_control_value_other_than_none_or_negative_is_refused_under_all_rows(tmp_path, control):
    paths = write_world(tmp_path, world_data())
    rows = _new_run_rows()
    rows[1]["control"] = control
    write_run(paths, RUN_NEW, rows, review=[rows[0]["id"]], traced=[])
    rerun(paths, tmp_path / "sample", *ONLY_NEW_OPTIONAL)                  # the review sample does not read it
    message = refused_paths(paths, "bad_input", *ONLY_NEW_OPTIONAL, "--pilot-all-rows", RUN_NEW)
    assert rows[1]["id"] in message and "neither 'none' nor 'negative'" in message


def test_a_run_with_no_row_to_select_is_refused(tmp_path):
    paths = write_world(tmp_path, world_data())
    control = _new_run_rows()[3]
    write_run(paths, RUN_NEW, [control], review=[control["id"]], traced=[])
    message = refused_paths(paths, "bad_input", *ONLY_NEW_OPTIONAL, "--pilot-all-rows", RUN_NEW)
    assert f"pilot run {RUN_NEW}: no row was selected" in message


def test_an_optional_trace_reads_no_trace_file_but_run2s_id_key(tmp_path, capsys):
    # A run with --pilot-trace-optional reads no trace file, except Run 2, whose item ids are keyed on its trace
    # pairs file: that file is read for the items' source_sha256 and must exist; its sidecar and trace results are not
    # read. (Check of 2026-10-04: the docs had said no trace file is read for any run.)
    paths = write_world(tmp_path, world_data())
    rows = _new_run_rows()
    write_run(paths, RUN_NEW, rows)                  # its traces have landed
    run2_pairs = paths["pilot_runs_dir"] / RUN2 / "trace" / "trace_pairs.json"
    bundle, _ = rerun(paths, tmp_path / "optional", "--pilot-run", RUN2, "--pilot-run", RUN_NEW,
                      "--pilot-trace-optional", RUN2, "--pilot-trace-optional", RUN_NEW)
    read = {s["path"]: s["role"] for s in bundle["sources"]}
    trace_files = sorted(p for p in read if "/trace/" in p or p.startswith(evt.logical_path(paths["pilot_trace_root"])))
    assert trace_files == [evt.logical_path(run2_pairs)]
    assert read[evt.logical_path(run2_pairs)] == f"pilot run {RUN2} item id key"
    assert {i["provenance"]["source_sha256"] for i in _pilot(bundle, "pilot_run2")} == {_file_sha(run2_pairs)}
    run2_pairs.unlink()
    message = refused_paths(paths, "missing_input", "--pilot-run", RUN2, "--pilot-trace-optional", RUN2)
    assert "item id key" in message


def test_without_traces_a_run_is_refused_unless_optional_and_its_items_do_not_change_when_traces_land(tmp_path,
                                                                                                     capsys):
    # Run 3's traces may land after the bundle is wanted: requiring a trace stays the default, and an optional one
    # is neither required nor read, so the same export gives the same bytes before and after the traces land
    paths = write_world(tmp_path, world_data())
    rows = _new_run_rows()
    write_run(paths, RUN_NEW, rows, traced=[])
    both = ("--pilot-run", RUN2, "--pilot-run", RUN_NEW)
    message = refused_paths(paths, "missing_trace", *both)
    assert RUN_NEW in message and f"--pilot-trace-optional {RUN_NEW}" in message
    before, raw_before = rerun(paths, tmp_path / "before", *both, "--pilot-trace-optional", RUN_NEW)
    sel = before["selection"]["tracing_pair"][NEW_LABEL]
    assert sel["trace_required"] is False and sel["trace_pairs"] is None and sel["trace_results"] is None
    assert sel["trace_model"] is None
    assert "not required and not read" in sel["rule"]
    assert [i["provenance"]["trace_index"] for i in _pilot(before, NEW_LABEL)] == [None, None, None]
    assert {i["provenance"]["trace_index"] for i in _pilot(before, "pilot_run2")} == {1, 2}

    write_run(paths, RUN_NEW, rows)                  # the traces land
    _, raw_after = rerun(paths, tmp_path / "after", *both, "--pilot-trace-optional", RUN_NEW)
    assert raw_after == raw_before
    traced, _ = rerun(paths, tmp_path / "traced", *both)

    def shown(b: dict) -> dict:
        return {i["item_id"]: i["display"] for i in _pilot(b, NEW_LABEL)}

    assert shown(traced) == shown(before)                                   # same ids, same displays
    assert sorted(i["provenance"]["trace_index"] for i in _pilot(traced, NEW_LABEL)) == [1, 2, 3]


@pytest.mark.parametrize("change, code", [({"finalized_utc": None}, "run_not_finalized"),
                                          ({"finalized_utc": "  "}, "run_not_finalized"),
                                          ({"finalized_utc": 20990101}, "run_not_finalized"),
                                          ({"version": 1}, "run_not_version_2"),
                                          ({"version": "2"}, "run_not_version_2"),
                                          ({"version": True}, "run_not_version_2")])
def test_a_run_that_is_not_finalized_or_not_version_2_is_refused(tmp_path, change, code):
    paths = write_world(tmp_path, world_data())
    write_run(paths, RUN_NEW, _new_run_rows(), **change)
    assert RUN_NEW in refused_paths(paths, code, "--pilot-run", RUN_NEW)
    refused_paths(paths, code, "--pilot-run", RUN_NEW, "--pilot-trace-optional", RUN_NEW)


@pytest.mark.parametrize("hashes", [None, [], "design.json"])
def test_a_manifest_whose_output_hashes_is_not_a_map_is_refused(tmp_path, hashes):
    paths = write_world(tmp_path, world_data())
    run = write_run(paths, RUN_NEW, _new_run_rows(), traced=[])
    manifest = json.loads((run / "manifest.json").read_text())
    manifest["output_hashes"] = hashes
    dump(run / "manifest.json", manifest)
    assert "no output_hashes" in refused_paths(paths, "run_not_finalized", "--pilot-run", RUN_NEW,
                                               "--pilot-trace-optional", RUN_NEW)


@pytest.mark.parametrize("name", ["generated/all_rows.jsonl", "review_map.json", "design.json"])
def test_a_run_file_that_no_longer_matches_its_finalized_manifest_is_refused(tmp_path, name):
    paths = write_world(tmp_path / "changed", world_data())
    run = write_run(paths, RUN_NEW, _new_run_rows(), traced=[])
    (run / name).write_bytes((run / name).read_bytes() + b"\n")
    assert name in refused_paths(paths, "hash_mismatch", "--pilot-run", RUN_NEW, "--pilot-trace-optional", RUN_NEW)
    paths = write_world(tmp_path / "unrecorded", world_data())
    run = write_run(paths, RUN_NEW, _new_run_rows(), traced=[])
    manifest = json.loads((run / "manifest.json").read_text())
    del manifest["output_hashes"][name]
    dump(run / "manifest.json", manifest)
    assert name in refused_paths(paths, "run_not_finalized", "--pilot-run", RUN_NEW,
                                 "--pilot-trace-optional", RUN_NEW)


def test_a_required_trace_that_is_missing_or_carries_other_prompts_is_refused(tmp_path):
    def summary(paths: dict[str, Path]) -> Path:
        return paths["pilot_trace_root"] / "trace_pairs" / "batch_summary.part_01.json"

    paths = write_world(tmp_path / "short", world_data())
    doc = json.loads(summary(paths).read_text())
    doc["results"] = doc["results"][:1]
    summary(paths).write_text(json.dumps(doc))
    assert "--pilot-trace-optional" in refused_paths(paths, "missing_trace")

    paths = write_world(tmp_path / "other", world_data())
    doc = json.loads(summary(paths).read_text())
    doc["results"][1]["prompts"]["patient"] += " again"
    summary(paths).write_text(json.dumps(doc))
    refused_paths(paths, "trace_mismatch")

    paths = write_world(tmp_path / "none", world_data())
    summary(paths).unlink()
    refused_paths(paths, "missing_trace")

    paths = write_world(tmp_path / "partial", world_data())        # a trace pairs file without one review row
    rows = _new_run_rows()
    write_run(paths, RUN_NEW, rows, traced=[rows[0]["id"]])
    assert rows[1]["id"] in refused_paths(paths, "missing_trace", "--pilot-run", RUN_NEW)


def _run2_pairs(paths: dict[str, Path]) -> tuple[Path, list[dict]]:
    run = paths["pilot_runs_dir"] / RUN2
    return run, json.loads((run / "trace" / "trace_pairs.json").read_text())


def test_a_trace_pairs_file_naming_a_row_the_run_does_not_have_is_refused(tmp_path):
    paths = write_world(tmp_path, world_data())
    run, pairs = _run2_pairs(paths)
    pairs.append(dict(pairs[0], pilot=dict(pairs[0]["pilot"], row_id="A__cell__kind__L99")))
    write_pairs(run, pairs)
    assert "A__cell__kind__L99" in refused_paths(paths, "bad_input")


@pytest.mark.parametrize("field, value, fragment", [
    ("top_prompt", "I left the red ledger on the bus, so I need to call my", "are not row"),
    ("bottom_prompt", "I left the notebook on the train, so I need to call my", "are not row"),
    ("target_clinical_token", " landlord", "target_clinical_token is not a space plus row"),
])
def test_a_trace_pair_that_is_not_its_rows_sentences_and_next_word_is_refused(tmp_path, field, value, fragment):
    # the trace results keep the row's prompts, so only the pair-against-row check can catch this
    paths = write_world(tmp_path, world_data())
    run, pairs = _run2_pairs(paths)
    pairs[0][field] = value
    write_pairs(run, pairs)
    message = refused_paths(paths, "bad_input")
    assert fragment in message and pairs[0]["pilot"]["row_id"] in message and value not in message


def test_a_trace_pairs_file_repeating_a_row_is_refused(tmp_path):
    paths = write_world(tmp_path, world_data())
    run, pairs = _run2_pairs(paths)
    write_pairs(run, pairs + [pairs[0]])
    message = refused_paths(paths, "bad_input")
    assert "pair 3 repeats row" in message and pairs[0]["pilot"]["row_id"] in message


def test_a_trace_pairs_sidecar_or_pair_naming_another_run_is_refused(tmp_path):
    # the guard against exporting another run's pairs under this run's label and ids
    paths = write_world(tmp_path / "sidecar", world_data())
    run, pairs = _run2_pairs(paths)
    meta_path = run / "trace" / "trace_pairs.meta.json"
    meta = json.loads(meta_path.read_text())
    meta["run"] = RUN_NEW
    dump(meta_path, meta)
    assert f"names run {RUN_NEW!r}, not {RUN2!r}" in refused_paths(paths, "bad_input")

    paths = write_world(tmp_path / "pair", world_data())
    run, pairs = _run2_pairs(paths)
    pairs[1]["pilot"]["run"] = RUN_NEW
    write_pairs(run, pairs)
    message = refused_paths(paths, "bad_input")
    assert "pair 2: its pilot block names run" in message and RUN_NEW in message


def test_more_than_one_trace_pairs_file_under_a_run_is_refused(tmp_path):
    paths = write_world(tmp_path, world_data())
    rows = _new_run_rows()
    run = write_run(paths, RUN_NEW, rows)
    write_pairs(run, [_pair_of(rows[0], RUN_NEW, "r001")], f"{RUN_NEW}_again")     # both named for the run
    for extra in ((), ("--pilot-all-rows", RUN_NEW)):
        message = refused_paths(paths, "bad_input", "--pilot-run", RUN_NEW, *extra)
        assert "2 trace pairs files" in message and f"{RUN_NEW}_again.json" in message
    # Run 2 alone may hold a second file, and only a byte-identical copy of trace_pairs.json (see the copy tests)
    paths = write_world(tmp_path / "run2", world_data())
    run, pairs = _run2_pairs(paths)
    write_pairs(run, pairs[:1], f"{RUN2}_trace_pairs")
    message = refused_paths(paths, "bad_input")
    assert f"{RUN2}_trace_pairs.json" in message and "not a byte-identical copy of trace_pairs.json" in message


def test_a_trace_pairs_file_without_review_ids_serves_the_review_sample_and_every_row(tmp_path, capsys):
    # Regression (check of 2026-10-04): trace_pairs.py's default and --include-controls selections write
    # review_id null on every pair, and the exporter read each null as a mismatch with review_map.json, so no such
    # file could serve any selection. Here the trace pairs file holds every row, the negative control included, as
    # --include-controls writes it, with no review ids.
    paths = write_world(tmp_path, world_data())
    rows = _new_run_rows()
    write_run(paths, RUN_NEW, rows, review=[rows[2]["id"], rows[0]["id"]], traced=[r["id"] for r in rows],
              review_ids=False)
    both = ("--pilot-run", RUN2, "--pilot-run", RUN_NEW)
    sample, _ = rerun(paths, tmp_path / "sample", *both)
    every, _ = rerun(paths, tmp_path / "every", *both, "--pilot-all-rows", RUN_NEW)

    def by_row(b: dict) -> dict[str, tuple[str, str | None, int]]:
        return {i["provenance"]["source_id"]: (i["item_id"], i["provenance"]["review_id"],
                                               i["provenance"]["trace_index"]) for i in _pilot(b, NEW_LABEL)}

    # the review ids come from review_map.json, the trace index from the pairs file's order
    assert by_row(sample) == {rows[2]["id"]: (by_row(every)[rows[2]["id"]][0], "r001", 3),
                              rows[0]["id"]: (by_row(every)[rows[0]["id"]][0], "r002", 1)}
    assert sorted(by_row(every)) == sorted(r["id"] for r in rows[:3])
    assert by_row(every)[rows[1]["id"]][1:] == (None, 2)
    assert sample["selection"]["tracing_pair"][NEW_LABEL]["counts"]["trace_pairs_not_selected"] == 2
    assert every["selection"]["tracing_pair"][NEW_LABEL]["counts"]["trace_pairs_not_selected"] == 1  # the control


def test_a_row_the_trace_pairs_file_leaves_out_is_refused_with_how_to_build_one(tmp_path):
    # trace_pairs.py's default selection leaves out the rows the checker did not judge equivalent, so a review-sample
    # row (or, under --pilot-all-rows, any non-control row) can be missing from it
    paths = write_world(tmp_path, world_data())
    rows = _new_run_rows()
    write_run(paths, RUN_NEW, rows, review=[rows[1]["id"]], traced=[rows[0]["id"], rows[2]["id"]],
              review_ids=False)
    message = refused_paths(paths, "missing_trace", "--pilot-run", RUN_NEW)
    assert rows[1]["id"] in message and "trace_pairs.py --review-sample" in message
    message = refused_paths(paths, "missing_trace", "--pilot-run", RUN_NEW, "--pilot-all-rows", RUN_NEW)
    assert rows[1]["id"] in message and "--pilot-all-rows takes every non-control row" in message


def test_a_trace_pairs_file_whose_review_ids_disagree_with_the_review_map_is_refused(tmp_path):
    paths = write_world(tmp_path / "selected", world_data())     # a selected pair carries another review id
    run, pairs = _run2_pairs(paths)
    pairs[1]["pilot"]["review_id"] = "r009"
    write_pairs(run, pairs)
    message = refused_paths(paths, "bad_input")
    assert "pair 2: its review id" in message and "another review map" in message

    paths = write_world(tmp_path / "unselected", world_data())   # a pair outside the sample carries one
    rows = _new_run_rows()
    write_run(paths, RUN_NEW, rows, review=[rows[0]["id"]], traced=[r["id"] for r in rows[:3]],
              review_ids=False)
    pairs = json.loads((paths["pilot_runs_dir"] / RUN_NEW / "trace" / f"{NEW_PAIRS}.json").read_text())
    for n, pair in enumerate(pairs, 1):
        pair["pilot"]["review_id"] = f"r{n:03d}"
    write_pairs(paths["pilot_runs_dir"] / RUN_NEW, pairs, NEW_PAIRS)
    message = refused_paths(paths, "bad_input", "--pilot-run", RUN_NEW)
    assert "pair 2: its review id" in message and rows[1]["id"] in message

    paths = write_world(tmp_path / "some", world_data())         # review ids on some pairs and not others
    run, pairs = _run2_pairs(paths)
    pairs[0]["pilot"]["review_id"] = None
    write_pairs(run, pairs)
    assert "records a review id for 1 of its 2 pairs" in refused_paths(paths, "bad_input")


# ---- trace pairs file names and trace results directories ---------------------------------------------------

RUN3 = "pilot_v3_20261004"          # named like pilot Run 3, whose pairs file is named after the run


def test_a_run_reads_the_trace_results_named_after_its_pairs_file_and_run2_its_legacy_directory(tmp_path, capsys):
    # The naming rule: a run's trace pairs file is <run id>_<name>.json (Run 3's is pilot_v3_20261004_trace_pairs.json),
    # and the circuit-trace lane writes its results to pilot/traces/<that stem>/; Run 2's trace_pairs.json predates
    # the rule and keeps pilot/traces/trace_pairs/.
    paths = write_world(tmp_path, world_data())
    write_run(paths, RUN3, _new_run_rows())
    bundle, _ = rerun(paths, paths["out_dir"], "--pilot-run", RUN2, "--pilot-run", RUN3)
    tracing = bundle["selection"]["tracing_pair"]
    assert tracing["pilot_run2"]["trace_results"] == evt.logical_path(paths["pilot_trace_root"] / "trace_pairs")
    assert tracing[f"pilot:{RUN3}"]["trace_results"] == evt.logical_path(
        paths["pilot_trace_root"] / f"{RUN3}_trace_pairs")
    assert tracing[f"pilot:{RUN3}"]["trace_pairs"] == evt.logical_path(
        paths["pilot_runs_dir"] / RUN3 / "trace" / f"{RUN3}_trace_pairs.json")
    assert {tracing[k]["trace_model"] for k in ("pilot_run2", f"pilot:{RUN3}")} == {"gemma-2-2b"}


def _items_bytes(raw: bytes) -> bytes:
    return raw[raw.index(b'\n "items": ['):]


def test_run2s_copy_made_to_trace_it_again_leaves_its_export_unchanged(tmp_path, capsys):
    # PR #85's lanes refuse Run 2's legacy trace_pairs.json for a new fire and say to copy it under
    # pilot_v2_20261002_trace_pairs.json. A copy beside it made the default export (the recorded first-bundle
    # command) refuse with "2 trace pairs files". A byte-identical copy is now allowed; the export still reads
    # trace_pairs.json, which Run 2's ids are keyed on, and its results in pilot/traces/trace_pairs/, never the
    # copy's results.
    paths = write_world(tmp_path, world_data())
    before, before_raw = rerun(paths, tmp_path / "before")
    run, pairs = _run2_pairs(paths)
    copy_name = f"{RUN2}_trace_pairs"
    shutil.copy2(run / "trace" / "trace_pairs.json", run / "trace" / f"{copy_name}.json")
    shutil.copy2(run / "trace" / "trace_pairs.meta.json", run / "trace" / f"{copy_name}.meta.json")
    write_traces(paths, copy_name, pairs, "qwen3-4b")                        # a re-trace from the copy
    after, after_raw = rerun(paths, tmp_path / "after")
    assert _items_bytes(after_raw) == _items_bytes(before_raw)
    assert after["selection"] == before["selection"]
    sel = after["selection"]["tracing_pair"]["pilot_run2"]
    assert sel["trace_pairs"].endswith(f"{RUN2}/trace/trace_pairs.json") and sel["trace_model"] == "gemma-2-2b"
    assert sel["trace_results"] == evt.logical_path(paths["pilot_trace_root"] / "trace_pairs")
    assert [s["role"] for s in after["sources"] if s["path"].endswith(f"{copy_name}.json")] == [
        f"pilot run {RUN2} trace pairs copy"]
    # with the trace optional, Run 2 still reads only trace_pairs.json, for its id key
    rerun(paths, tmp_path / "optional", "--pilot-trace-optional", RUN2)
    # the copy's results are never read for Run 2: naming the model they are for looks in trace_pairs__qwen3-4b/
    message = refused_paths(paths, "missing_trace", "--pilot-trace-model", RUN2, "qwen3-4b")
    assert "trace_pairs__qwen3-4b" in message and copy_name not in message


def test_a_second_file_under_run2s_trace_that_is_not_a_copy_is_refused(tmp_path):
    paths = write_world(tmp_path, world_data())
    run, _ = _run2_pairs(paths)
    copy_path = run / "trace" / f"{RUN2}_trace_pairs.json"
    copy_path.write_bytes((run / "trace" / "trace_pairs.json").read_bytes() + b"\n")    # one byte more
    message = refused_paths(paths, "bad_input")
    assert copy_path.name in message and "not a byte-identical copy of trace_pairs.json" in message
    # a copy not named for the run is refused by the naming rule, as any other file there is
    copy_path.unlink()
    shutil.copy2(run / "trace" / "trace_pairs.json", run / "trace" / "trace_pairs_copy.json")
    assert "trace_pairs_copy.json is not named after the run" in refused_paths(paths, "bad_input")


@pytest.mark.parametrize("optional", [False, True], ids=["required", "optional"])
def test_a_trace_pairs_file_not_named_after_its_run_is_refused_even_when_its_traces_are_optional(tmp_path, optional):
    # Codex review of PR #86 (4179236833): a later run whose trace pairs file keeps trace_pairs.py's default name
    # (trace_pairs.json, Run 2's) maps to Run 2's pilot/traces/trace_pairs/, and firing its trace would overwrite
    # Run 2's committed results. With --pilot-trace-optional the exporter skipped the check and exported it.
    paths = write_world(tmp_path, world_data())
    write_run(paths, RUN_NEW, _new_run_rows(), pairs_name="trace_pairs")
    extra = ("--pilot-trace-optional", RUN_NEW) if optional else ()
    message = refused_paths(paths, "bad_input", "--pilot-run", RUN2, "--pilot-run", RUN_NEW, *extra)
    assert "trace_pairs.json is not named after the run" in message and RUN_NEW in message
    # any name that does not start with the run id is refused the same way, with Run 2 in the export or not
    paths = write_world(tmp_path / "other", world_data())
    write_run(paths, RUN_NEW, _new_run_rows(), pairs_name="pairs_v9")
    assert "pairs_v9.json is not named after the run" in refused_paths(paths, "bad_input", "--pilot-run", RUN_NEW,
                                                                        *extra)


@pytest.mark.parametrize("optional", [False, True], ids=["required", "optional"])
@pytest.mark.parametrize("stem", [RUN_NEW, RUN_NEW + "x", RUN_NEW + "-pairs", RUN_NEW + "_"],
                         ids=["bare_run_id", "another_character", "a_hyphen", "no_name_after_the_underscore"])
def test_a_trace_pairs_file_needs_the_run_id_an_underscore_and_a_name(tmp_path, stem, optional):
    # The lane's rule (PR #85) is <run id>_<name>.json with <name> not empty. The exporter first accepted any name
    # starting with the run id, so it exported runs whose pairs file the lane refuses to trace.
    paths = write_world(tmp_path, world_data())
    write_run(paths, RUN_NEW, _new_run_rows(), pairs_name=stem)
    extra = ("--pilot-trace-optional", RUN_NEW) if optional else ()
    message = refused_paths(paths, "bad_input", "--pilot-run", RUN_NEW, *extra)
    assert f"{stem}.json is not named after the run" in message and f"{RUN_NEW}_<name>.json" in message


def test_a_trace_pairs_file_with_the_run_id_an_underscore_and_any_name_is_accepted(tmp_path, capsys):
    paths = write_world(tmp_path, world_data())
    write_run(paths, RUN_NEW, _new_run_rows(), pairs_name=f"{RUN_NEW}_x")
    bundle, _ = rerun(paths, paths["out_dir"], "--pilot-run", RUN_NEW)
    assert bundle["selection"]["tracing_pair"][NEW_LABEL]["trace_results"] == evt.logical_path(
        paths["pilot_trace_root"] / f"{RUN_NEW}_x")


# (stem, whether the lane's rule accepts it) for a run named like Run 3; the exporter's own "__" refusal is separate
LANE_NAMING_CASES = [(f"{RUN3}_trace_pairs", True), (f"{RUN3}_x", True), (f"{RUN3}__x", True), (RUN3, False),
                     (f"{RUN3}x", False), (f"{RUN3}-pairs", False), (f"{RUN3}_", False), ("trace_pairs", False),
                     (f"x_{RUN3}_trace_pairs", False), (f"{RUN3[:-1]}_trace_pairs", False)]


def test_the_naming_rule_is_the_lanes():
    # The exporter and the lanes' pilot roots must accept the same pairs-file names, or the exporter would export a
    # run whose traces the lane refuses to fire. The lane's rule is fire_trigger.pilot_pairs_run_name_problem, which
    # comes with PR #85; until it is on the branch, this compares the exporter with the table alone.
    for stem, accepted in LANE_NAMING_CASES:
        assert evt._pairs_file_named_for_run(stem, RUN3) is accepted, stem
    assert evt._pairs_file_named_for_run("trace_pairs", RUN2), "Run 2's legacy name is the exporter's one exception"
    spec = importlib.util.spec_from_file_location("fire_trigger_naming", ROOT / "scripts" / "fire_trigger.py")
    fire_trigger = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fire_trigger)
    lane_rule = getattr(fire_trigger, "pilot_pairs_run_name_problem", None)
    if lane_rule is None:
        pytest.skip("scripts/fire_trigger.py has no pilot_pairs_run_name_problem on this branch (PR #85 adds it)")
    for root, lane in (("pilot/traces", "circuit-trace"), ("pilot/logits", "logits-eval")):
        for stem, accepted in LANE_NAMING_CASES:
            assert (lane_rule(f"pilot/runs/{RUN3}/trace/{stem}.json", lane, root) is None) is accepted, (lane, stem)


@pytest.mark.parametrize("optional", [(), (RUN_NEW + "_b",), (RUN_NEW,), (RUN_NEW, RUN_NEW + "_b")],
                         ids=["both_required", "later_optional", "earlier_optional", "both_optional"])
def test_two_runs_whose_trace_pairs_files_share_a_stem_are_refused_even_when_optional(tmp_path, optional):
    # Two runs' files can both satisfy the naming rule and still share a stem (one run id followed by "_" is a prefix
    # of the other); the circuit-trace lane would write both runs' results to one directory. An optional run's file
    # is checked too (Codex review of PR #86, 4179236833): its traces may be fired later. Only file names are read.
    paths = write_world(tmp_path, world_data())
    run_b = RUN_NEW + "_b"
    shared = f"{run_b}_trace_pairs"
    rows = _new_run_rows()
    write_run(paths, RUN_NEW, rows, pairs_name=shared)
    write_run(paths, run_b, [dict(r, id=r["id"] + "b") for r in rows], pairs_name=shared)
    extra = [a for run in optional for a in ("--pilot-trace-optional", run)]
    message = refused_paths(paths, "bad_input", "--pilot-run", RUN_NEW, "--pilot-run", run_b, *extra)
    assert RUN_NEW in message and run_b in message and "own stem" in message and shared in message


def test_a_trace_pairs_file_whose_stem_holds_the_model_separator_is_refused(tmp_path):
    # pilot/traces/<stem>__<model>/ is the lane's directory for a non-default model, so a stem holding "__" could be
    # read as another stem's results for another model
    paths = write_world(tmp_path, world_data())
    write_run(paths, RUN_NEW, _new_run_rows(), pairs_name=f"{RUN_NEW}__qwen3-4b")
    message = refused_paths(paths, "bad_input", "--pilot-run", RUN_NEW)
    assert "'__'" in message and RUN_NEW in message
    refused_paths(paths, "bad_input", "--pilot-run", RUN_NEW, "--pilot-trace-optional", RUN_NEW)


def test_a_run_traced_with_another_graph_model_reads_that_models_directory(tmp_path, capsys):
    # Codex review of PR #86 (4179127691): the circuit-trace lane writes a non-default model's results to
    # pilot/traces/<stem>__<model>/, and the exporter looked only in pilot/traces/<stem>/, so it reported a committed
    # cross-model trace as missing.
    paths = write_world(tmp_path, world_data())
    write_run(paths, RUN_NEW, _new_run_rows(), trace_model="qwen3-4b")
    both = ("--pilot-run", RUN2, "--pilot-run", RUN_NEW)
    found, _ = rerun(paths, tmp_path / "found", *both)                      # the one model with results
    named, _ = rerun(paths, tmp_path / "named", *both, "--pilot-trace-model", RUN_NEW, "qwen3-4b")
    for bundle in (found, named):
        sel = bundle["selection"]["tracing_pair"][NEW_LABEL]
        assert sel["trace_model"] == "qwen3-4b" and sel["trace_results"] == evt.logical_path(
            paths["pilot_trace_root"] / f"{NEW_PAIRS}__qwen3-4b")
        assert "qwen3-4b trace results" in sel["rule"]
        assert sorted(i["provenance"]["trace_index"] for i in _pilot(bundle, NEW_LABEL)) == [1, 2, 3]
    assert [i["item_id"] for i in found["items"]] == [i["item_id"] for i in named["items"]]
    # the default model, named, is read from the unsuffixed directory, which holds nothing here
    message = refused_paths(paths, "missing_trace", *both, "--pilot-trace-model", RUN_NEW, "gemma-2-2b")
    assert message.count(NEW_PAIRS) == 1 and "qwen3-4b" not in message


def test_a_named_model_never_reads_the_default_models_results_and_two_models_need_one_named(tmp_path, capsys):
    # Codex review of PR #86 (4179127691): with a default-model directory already there, the exporter validated it
    # in place of the selected model's results. A named model is read from its own directory only, and with results
    # for two models and none named the export stops rather than choosing.
    paths = write_world(tmp_path, world_data())
    rows = _new_run_rows()
    write_run(paths, RUN_NEW, rows)                                          # gemma-2-2b results, complete
    pairs = json.loads((paths["pilot_runs_dir"] / RUN_NEW / "trace" / f"{NEW_PAIRS}.json").read_text())
    both = ("--pilot-run", RUN2, "--pilot-run", RUN_NEW)
    write_traces(paths, NEW_PAIRS, pairs[:1], "qwen3-4b")                    # qwen3-4b: one pair traced so far
    message = refused_paths(paths, "ambiguous_trace", *both)
    assert "2 directories" in message and "gemma-2-2b" in message and "qwen3-4b" in message
    assert f"--pilot-trace-model {RUN_NEW} <model>" in message
    message = refused_paths(paths, "missing_trace", *both, "--pilot-trace-model", RUN_NEW, "qwen3-4b")
    assert f"{NEW_PAIRS}__qwen3-4b" in message and "pair 2" in message
    gemma, _ = rerun(paths, tmp_path / "gemma", *both, "--pilot-trace-model", RUN_NEW, "gemma-2-2b")
    assert gemma["selection"]["tracing_pair"][NEW_LABEL]["trace_model"] == "gemma-2-2b"
    write_traces(paths, NEW_PAIRS, [dict(p, bottom_prompt=p["bottom_prompt"] + " again") for p in pairs],
                 "qwen3-4b")                                                 # qwen3-4b results, other prompts
    refused_paths(paths, "trace_mismatch", *both, "--pilot-trace-model", RUN_NEW, "qwen3-4b")


def test_a_named_model_with_no_results_directory_is_missing_not_read_from_the_default_models(tmp_path, capsys):
    # Codex review of PR #86 (4179127691), the case it names: the selected model's results are not committed at all
    # and complete gemma-2-2b results are. Naming the model must not fall back to the gemma-2-2b directory.
    paths = write_world(tmp_path, world_data())
    write_run(paths, RUN_NEW, _new_run_rows())                               # gemma-2-2b results only
    assert not (paths["pilot_trace_root"] / f"{NEW_PAIRS}__qwen3-4b").exists()
    both = ("--pilot-run", RUN2, "--pilot-run", RUN_NEW)
    message = refused_paths(paths, "missing_trace", *both, "--pilot-trace-model", RUN_NEW, "qwen3-4b")
    assert f"{NEW_PAIRS}__qwen3-4b" in message


def test_a_second_directory_for_the_default_model_is_ambiguous_not_hidden(tmp_path, capsys):
    # The lane never writes <stem>__gemma-2-2b/, but a directory of that name next to <stem>/ is a second set of
    # results for the same model; it is counted as such, not let to replace the first unseen
    paths = write_world(tmp_path, world_data())
    write_run(paths, RUN_NEW, _new_run_rows())
    pairs = json.loads((paths["pilot_runs_dir"] / RUN_NEW / "trace" / f"{NEW_PAIRS}.json").read_text())
    dump(paths["pilot_trace_root"] / f"{NEW_PAIRS}__gemma-2-2b" / "batch_summary.part_01.json",
         {"results": [{"index": n, "prompts": {"clinical": p["top_prompt"], "patient": p["bottom_prompt"]}}
                      for n, p in enumerate(pairs, 1)]})
    assert "2 directories" in refused_paths(paths, "ambiguous_trace", "--pilot-run", RUN_NEW)


@pytest.mark.parametrize("extra, fragment", [
    (("--pilot-run", RUN2, "--pilot-trace-model", RUN_NEW, "qwen3-4b"), "which no --pilot-run exports"),
    (("--pilot-run", RUN2, "--pilot-trace-model", RUN2, "qwen3-4b", "--pilot-trace-model", RUN2, "gemma-2-2b"),
     "more than once"),
    (("--pilot-run", RUN2, "--pilot-trace-optional", RUN2, "--pilot-trace-model", RUN2, "qwen3-4b"),
     "--pilot-trace-optional says not to read"),
    (("--pilot-run", RUN2, "--pilot-trace-model", RUN2, "../qwen3-4b"), "not a graph model id"),
    (("--pilot-run", RUN2, "--pilot-trace-model", RUN2, "qwen3__4b"), "not a graph model id"),
])
def test_pilot_trace_model_arguments_are_checked(tmp_path, extra, fragment):
    paths = write_world(tmp_path, world_data())
    assert fragment in refused_paths(paths, "bad_input", *extra)


@pytest.mark.parametrize("extra, fragment", [
    (("--pilot-run", "pilot/runs/x"), "not a run id"),
    (("--pilot-run", ".."), "not a run id"),
    (("--pilot-run", RUN2, "--pilot-run", RUN2), "more than once"),
    (("--pilot-all-rows", RUN_NEW), "which no --pilot-run exports"),
    (("--pilot-trace-optional", RUN_NEW), "which no --pilot-run exports"),
])
def test_pilot_run_arguments_are_checked(tmp_path, extra, fragment):
    paths = write_world(tmp_path, world_data())
    assert fragment in refused_paths(paths, "bad_input", *extra)


def test_an_absent_run_is_refused(tmp_path):
    paths = write_world(tmp_path, world_data())
    assert RUN_NEW in refused_paths(paths, "missing_input", "--pilot-run", RUN_NEW)
    refused_paths(paths, "missing_input", "--pilot-run", RUN_NEW, "--pilot-trace-optional", RUN_NEW)


def test_a_sealed_row_in_any_run_refuses_the_export(tmp_path):
    paths = write_world(tmp_path, world_data())
    rows = _new_run_rows()
    rows[1].update({"template": "___", "clinical_term": SEALED})
    write_run(paths, RUN_NEW, rows, traced=[])
    message = refused_paths(paths, "sealed_row", "--pilot-run", RUN2, "--pilot-run", RUN_NEW,
                            "--pilot-trace-optional", RUN_NEW)
    assert rows[1]["id"] in message and SEALED not in message


def test_a_pair_that_repeats_an_earlier_pilot_pair_is_kept_and_counted(tmp_path, capsys):
    data = world_data()
    paths = write_world(tmp_path, data)
    rows = _new_run_rows() + [dict(data["pilot_rows"][0], id="B__cell__kind__L09", call_id="B__cell__kind")]
    write_run(paths, RUN_NEW, rows)
    bundle, _ = rerun(paths, paths["out_dir"], "--pilot-run", RUN2, "--pilot-run", RUN_NEW)
    tracing = bundle["selection"]["tracing_pair"]
    assert tracing["pilot_run2"]["counts"]["repeats_an_earlier_pilot_pair"] == 0
    assert tracing[NEW_LABEL]["counts"]["repeats_an_earlier_pilot_pair"] == 1
    assert len(_pilot(bundle, NEW_LABEL)) == 4


# ---- rounds: a later bundle keeps every item of the previous one --------------------------------------------

def test_a_later_round_keeps_every_previous_item_and_adds_a_run(tmp_path, capsys):
    first, raw_first, paths = export(tmp_path)
    assert first["selection"]["previous_bundle"] is None
    previous = tmp_path / "round1.json"
    previous.write_bytes(raw_first)
    rows = _new_run_rows()
    write_run(paths, RUN_NEW, rows)
    second, _ = rerun(paths, tmp_path / "round2", "--pilot-run", RUN2, "--pilot-run", RUN_NEW,
                      "--previous-bundle", str(previous))
    assert check_contract(second) == []
    assert second["selection"]["previous_bundle"] == {
        "path": evt.logical_path(previous), "bundle_id": first["bundle_id"],
        "sha256": hashlib.sha256(raw_first).hexdigest(), "items_kept": 13, "items_added": 3}
    kept = {i["item_id"]: i for i in second["items"]}
    assert all(kept[i["item_id"]]["display"] == i["display"] for i in first["items"])


def test_a_later_round_that_drops_or_changes_a_previous_item_or_question_is_refused(tmp_path, capsys):
    _, raw_first, paths = export(tmp_path / "w")
    previous = tmp_path / "round1.json"
    previous.write_bytes(raw_first)
    shutil.rmtree(paths["out_dir"])
    # dropped: one main-study pair fewer
    message = refused_paths(paths, "previous_item_missing", "--previous-bundle", str(previous), main_pairs=3)
    assert evt.item_id_for("tracing_pair", evt.SITE_LABEL, f"{TIER_A}#6") in message
    # changed: another text under the same advice item id
    original = paths["advice_new"].read_bytes()
    advice = json.loads(original)
    item = advice["items"][0]
    item["patient_message"] += " Thanks."
    item["patient_sha256"] = _sha(item["patient_message"])
    dump(paths["advice_new"], advice)
    message = refused_paths(paths, "previous_item_changed", "--previous-bundle", str(previous))
    assert evt.item_id_for("advice", evt.logical_path(paths["advice_new"]), item["id"]) in message
    assert "1 item(s)" in message and item["patient_message"] not in message
    advice = json.loads(original)                       # another proposed tier: the after-reveal answers refer to it
    advice["items"][0]["reference"]["tier"] = "routine"
    dump(paths["advice_new"], advice)
    assert "1 item(s)" in refused_paths(paths, "previous_item_changed", "--previous-bundle", str(previous))
    paths["advice_new"].write_bytes(original)
    # a question id renamed (wording may change; ids may not)
    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    keep = next(q for q in questions["question_sets"]["tracing_pair"]["questions"] if q["id"] == "keep")
    keep["id"] = "keep_renamed"
    paths["questions"] = dump(tmp_path / "questions.json", questions)
    assert "tracing_pair.keep" in refused_paths(paths, "previous_question_missing", "--previous-bundle",
                                                str(previous))


def _round1(tmp_path: Path) -> tuple[dict[str, Path], dict, Path]:
    """A world, its round-1 bundle (parsed) and a path to write a previous bundle to; the world's out dir is empty."""
    first, _, paths = export(tmp_path / "w")
    shutil.rmtree(paths["out_dir"])
    return paths, first, tmp_path / "round1.json"


@pytest.mark.parametrize("doc", [{"schema": "patientwords-verification-tasks/0", "items": [], "questions": {}},
                                 {"schema": evt.SCHEMA, "items": {}, "questions": {}},
                                 {"schema": evt.SCHEMA, "items": [], "questions": []},
                                 [evt.SCHEMA]])
def test_a_previous_bundle_that_is_not_a_tasks_bundle_is_refused(tmp_path, doc):
    paths, _, previous = _round1(tmp_path)
    dump(previous, doc)
    assert f"is not a {evt.SCHEMA} bundle" in refused_paths(paths, "bad_input", "--previous-bundle", str(previous))


def test_a_previous_item_whose_question_set_alone_changed_is_refused(tmp_path, capsys):
    paths, first, previous = _round1(tmp_path)
    item = next(i for i in first["items"] if i["question_set"] == "advice_rerun")
    item["question_set"] = "advice_rerun_truncated"                       # display and reveal unchanged
    dump(previous, first)
    message = refused_paths(paths, "previous_item_changed", "--previous-bundle", str(previous))
    assert "1 item(s)" in message and item["item_id"] in message


def _question(questions: dict, set_name: str, qid: str) -> dict:
    return next(q for q in questions["question_sets"][set_name]["questions"] if q["id"] == qid)


def _options(*values: Any) -> list[dict]:
    return [{"value": v, "label": str(v)} for v in values]


# Each change keeps the question id but changes what a stored answer means; the app checks a stored answer against
# the question's current scale, phase and lock when a physician saves the item again (patientwords-verify
# src/Logic.gs). The first is the check of 2026-10-04's reproduction (realism5 replaced by yes_no; the 4 a
# physician gave would sit under a scale without it). (mutation of the questions, a question it changes, the field)
CONTRACT_CHANGES = {
    "scale": (lambda q: _question(q, "tracing_pair", "patient_realism").update(scale="yes_no"),
              "tracing_pair.patient_realism", "scale_type"),
    "values": (lambda q: q["scales"]["keep3"].update(options=_options("yes", "no")), "tracing_pair.keep", "values"),
    "order": (lambda q: q["scales"]["realism5"]["options"].reverse(), "advice_new.realism_patient", "values"),
    "abstain": (lambda q: q["scales"]["yes_no"]["abstain"].update(value="unsure"), "tracing_pair.same", "abstain"),
    "max_length": (lambda q: q["scales"]["text1000"].update(max_length=200), "advice_new.proposed_tier_reason",
                   "max_length"),
    "phase": (lambda q: _question(q, "advice_new", "proposed_tier_agree").update(phase="blind"),
              "advice_new.proposed_tier_agree", "phase"),
    "per_arm": (lambda q: _question(q, "multiturn_script", "realism").update(per_arm=False),
                "multiturn_script.realism", "per_arm"),
    # Codex review of PR #86 (4179127689): required gates the reveal and an item's completeness in the app
    # (blindComplete_, itemComplete_) and the import (is_complete), in both directions
    "required_on": (lambda q: _question(q, "tracing_pair", "keep").update(required=True), "tracing_pair.keep",
                    "required"),
    "required_off": (lambda q: _question(q, "tracing_pair", "same").update(required=False), "tracing_pair.same",
                     "required"),
    # Codex review of PR #86 (4179127694): Python's == takes true for 1, the app's === and the import's same_value
    # do not, so a stored 1 would be refused under a scale whose option is true
    "value_type": (lambda q: q["scales"]["realism5"]["options"][0].update(value=True),
                   "advice_new.realism_patient", "values"),
}


@pytest.mark.parametrize("change", sorted(CONTRACT_CHANGES))
def test_a_kept_question_id_whose_answer_contract_changed_is_refused(tmp_path, change):
    paths, first, previous = _round1(tmp_path)
    dump(previous, first)
    mutate, key, field = CONTRACT_CHANGES[change]
    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    mutate(questions)
    paths["questions"] = dump(tmp_path / "questions.json", questions)
    message = refused_paths(paths, "previous_question_changed", "--previous-bundle", str(previous))
    assert re.search(re.escape(key) + r" \([^)]*\b" + field + r"\b", message), message


def test_an_abstain_value_of_another_json_type_is_refused(tmp_path):
    # Codex review of PR #86 (4179127694), for the abstain value: 0 and false are equal in Python, not in the app
    paths, first, previous = _round1(tmp_path)
    first["questions"]["scales"]["yes_no"]["abstain"]["value"] = 0
    dump(previous, first)
    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    questions["scales"]["yes_no"]["abstain"]["value"] = False
    paths["questions"] = dump(tmp_path / "questions.json", questions)
    message = refused_paths(paths, "previous_question_changed", "--previous-bundle", str(previous))
    assert "tracing_pair.same (abstain)" in message


@pytest.mark.parametrize("limit", [2000, 8000])
def test_another_notes_limit_is_refused(tmp_path, limit):
    # Codex review of PR #86 (4179236828): the app and the import refuse a note longer than the bundle's
    # notes.max_length, so a lower limit would refuse a note saved under round 1's. The limit is compared exactly,
    # as a text scale's max_length is, so a higher one is refused too.
    paths, first, previous = _round1(tmp_path)
    dump(previous, first)
    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    questions["notes"]["max_length"] = limit
    paths["questions"] = dump(tmp_path / "questions.json", questions)
    message = refused_paths(paths, "previous_notes_changed", "--previous-bundle", str(previous))
    assert f"is {first['questions']['notes']['max_length']} and this bundle's is {limit}" in message


def test_a_question_that_gained_or_lost_the_reveal_lock_is_refused(tmp_path):
    # advice_new keeps exactly one locking question, so the lock is moved in the previous bundle's copy instead
    paths, first, previous = _round1(tmp_path)
    _question(first["questions"], "tracing_pair", "same")["locks_on_reveal"] = True
    dump(previous, first)
    message = refused_paths(paths, "previous_question_changed", "--previous-bundle", str(previous))
    assert "tracing_pair.same (locks_on_reveal)" in message


def test_a_question_reworded_or_on_a_renamed_identical_scale_is_kept(tmp_path, capsys):
    paths, first, previous = _round1(tmp_path)
    dump(previous, first)
    questions = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    keep = _question(questions, "tracing_pair", "keep")
    keep["text"] += " (reworded)"
    questions["scales"]["keep3_v2"] = copy.deepcopy(questions["scales"]["keep3"])
    questions["scales"]["keep3_v2"]["options"][0]["label"] += " (reworded)"
    keep["scale"] = "keep3_v2"
    paths["questions"] = dump(tmp_path / "questions.json", questions)
    second, _ = rerun(paths, tmp_path / "round2", "--previous-bundle", str(previous))
    assert second["selection"]["previous_bundle"]["items_kept"] == len(first["items"])


@pytest.mark.parametrize("change, fragment", [
    (lambda q: q.update(question_sets=[]), "questions.question_sets is not an object"),
    (lambda q: q.update(scales=None), "questions.scales is not an object"),
    (lambda q: q["question_sets"].update(tracing_pair={"family": "tracing_pair"}),
     "question set 'tracing_pair' has no questions list"),
    (lambda q: q["question_sets"]["tracing_pair"]["questions"].__setitem__(0, "same"),
     "question 1 of set 'tracing_pair' is not an object with a string id"),
    (lambda q: _question(q, "tracing_pair", "keep").update(scale="keep9"), "tracing_pair.keep: its scale is not"),
    (lambda q: q["scales"]["keep3"].update(options=["keep", "edit"]), "tracing_pair.keep: its scale is not"),
    (lambda q: q["scales"]["yes_no"].update(abstain="cant_tell"), "its scale's abstain is not"),
    (lambda q: q["notes"].pop("max_length"), "questions.notes.max_length is not a positive integer"),
    (lambda q: q["notes"].update(max_length=True), "questions.notes.max_length is not a positive integer"),
    (lambda q: q.pop("notes"), "questions.notes.max_length is not a positive integer"),
])
def test_a_previous_bundle_whose_questions_are_malformed_is_refused_not_skipped(tmp_path, change, fragment):
    paths, first, previous = _round1(tmp_path)
    change(first["questions"])
    dump(previous, first)
    assert fragment in refused_paths(paths, "bad_input", "--previous-bundle", str(previous))


def test_answer_contracts_refuse_a_questions_value_that_is_not_an_object():
    # through the command line check_previous_bundle refuses it first; the function refuses it on its own as well
    with pytest.raises(SystemExit) as exc:
        evt.answer_contracts([], "somewhere")
    assert "[bad_input] somewhere: questions is not an object" in str(exc.value)
    contracts = evt.answer_contracts(json.loads(QUESTIONS.read_text(encoding="utf-8")), "questions.json")
    assert contracts["advice_new.own_tier"] == {
        "scale_type": "ordinal", "values": ["self_care", "routine", "urgent", "emergency"], "abstain": "cant_tell",
        "max_length": None, "phase": "blind", "required": True, "per_arm": False, "locks_on_reveal": True}
    assert contracts["tracing_pair.keep"]["required"] is False


# ---- the first bundle, re-exported --------------------------------------------------------------------------

FIRST_BUNDLE = ROOT / "data" / "verification" / "tasks_20261004T042945Z.json"


def test_the_default_run_still_gives_the_first_bundles_pilot_items(tmp_path, capsys):
    # Reads the committed Run 2 files (sealed by its finalized manifest) and compares items; prints no row text.
    committed = json.loads(FIRST_BUNDLE.read_text(encoding="utf-8"))
    assert evt.main(["--main-pairs", "0", "--stamp", "20261004T042945Z", "--out-dir", str(tmp_path)]) == 0
    new = json.loads((tmp_path / FIRST_BUNDLE.name).read_text(encoding="utf-8"))
    mine = {i["item_id"]: i for i in _pilot(new, "pilot_run2")}
    first = {i["item_id"]: i for i in _pilot(committed, "pilot_run2")}
    assert len(first) == 40 and mine == first


def test_the_recorded_command_reproduces_the_first_bundles_items_byte_for_byte(tmp_path, capsys):
    # docs/verification_protocol.md's command with the bundle's own stamp. Its items also depend on the site payload
    # and the engine inputs it recorded, so this runs only when every one of them (but the daily dashboard, of which
    # only the Tier B start is read) still hashes as recorded.
    raw = FIRST_BUNDLE.read_bytes()
    committed = json.loads(raw)
    site = ROOT.parent / "patientwords"
    changed = []
    for source in committed["sources"]:
        if source["path"] == "ops/dashboard.json":
            continue
        path = site / evt.SITE_PAYLOAD if source["path"] == evt.SITE_LABEL else ROOT / source["path"]
        if not path.is_file() or _file_sha(path) != source["sha256"]:
            changed.append(source["path"])
    if changed:
        pytest.skip(f"inputs changed or absent since the first bundle: {changed}")
    assert committed["seed"] == evt.DEFAULT_SEED
    assert evt.main(["--site", str(site), "--stamp", "20261004T042945Z", "--out-dir", str(tmp_path)]) == 0
    new_raw = (tmp_path / FIRST_BUNDLE.name).read_bytes()
    marker = b'\n "items": ['
    assert new_raw[new_raw.index(marker):] == raw[raw.index(marker):]


# ---- the committed bundles ----------------------------------------------------------------------------------

COMMITTED = sorted((ROOT / "data" / "verification").glob("tasks_*.json"))


@pytest.mark.parametrize("path", COMMITTED, ids=[p.name for p in COMMITTED])
def test_committed_bundles_follow_the_contract(path):
    bundle = json.loads(path.read_text(encoding="utf-8"))
    assert path.name == f"tasks_{bundle['bundle_id'].removeprefix('vtasks_')}.json"
    assert check_contract(bundle) == []
    assert forbidden_in_display(bundle) == []
    recorded = {s["path"]: s["sha256"] for s in bundle["sources"]}
    assert recorded.get("data/verification/questions.json") == bundle["questions_sha256"]
    numbers = [i["item_id"] for i in bundle["items"] if i["provenance"].get("language_penalty") is not None
               and any(repr(i["provenance"]["language_penalty"]) in t for t in strings_in(i["display"]))]
    assert numbers == []
    main = sorted((i["provenance"]["rank"], i["provenance"]) for i in bundle["items"]
                  if i["provenance"].get("subset") == "main_study")
    keys = [(-round(abs(p["language_penalty"]), evt.RANK_DECIMALS), p["source_id"].split("#")[0],
             int(p["source_id"].split("#")[1])) for _, p in main]
    assert [r for r, _ in main] == list(range(1, len(main) + 1)) and keys == sorted(keys)
    assert all(re.fullmatch(r"vt_[0-9a-f]{12}", i) for i in bundle["seal"]["holdout_bucket_unsealed"]["item_ids"])

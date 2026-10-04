"""Physician verification task bundle (scripts/export_verification_tasks.py) - offline.

Pins the bundle's contract shape, determinism (same seed and stamp: byte-identical; another seed: the same items in
another order), that the display carries none of the hidden fields, numbers, model names, batch ids or proposed
tiers, the fail-closed holdout seal (a planted sealed phrase refuses the export and writes nothing), the list of
unsealed items whose clinical text hashes into the holdout bucket, the counts and selection per family (main-study
penalties equal as recorded tie, and the stated tie rule decides), item-id stability, and the question wording (no
hint predicts an answer, the urgency question names the message it asks about, raters are asked not to look the
scenarios up). Every input here is synthetic, abstract and non-medical (the medical
vocabulary rule in AGENTS.md); the seal fixtures follow tests/test_seal_check.py and tests/test_tierb_split.py.
The last test checks every committed bundle under data/verification/ against the contract, and its failure messages
name item ids only, never row text.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import re
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


def write_world(tmp_path: Path, data: dict) -> dict[str, Path]:
    def dump(path: Path, obj: Any) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj), encoding="utf-8")
        return path

    run = tmp_path / "pilot" / "run2"
    rows = data["pilot_rows"]
    (run / "generated").mkdir(parents=True)
    (run / "generated" / "all_rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows),
                                                       encoding="utf-8")
    pairs = data.get("pairs") or [
        {"top_prompt": r["template"].replace("___", r["clinical_term"]),
         "bottom_prompt": r["template"].replace("___", r["patient_term"]),
         "target_clinical_token": " " + r["next_word"],
         "pilot": {"run": "run2", "row_id": r["id"], "review_id": f"r{n:03d}", "call_id": r["call_id"],
                   "arm": "A", "cell": r["cell"], "control": "none", "concept_key": "k", "probe_point": True,
                   "checker": {"verdict": "yes"}, "prompt_sha256": "0" * 64}}
        for n, r in enumerate(rows, 1)]
    pairs_path = dump(run / "trace" / "trace_pairs.json", pairs)
    dump(run / "trace" / "trace_pairs.meta.json",
         {"run": "run2", "counts": {"selected": len(pairs)},
          "output": {"file": "trace_pairs.json", "sha256": hashlib.sha256(pairs_path.read_bytes()).hexdigest()}})
    traces = tmp_path / "pilot" / "traces"
    dump(traces / "batch_summary.part_01.json",
         {"results": [{"index": n, "prompts": {"clinical": p["top_prompt"], "patient": p["bottom_prompt"]}}
                      for n, p in enumerate(pairs, 1)]})
    sim = tmp_path / "simulated"
    dump(sim / f"{TIER_A}.json", data["tier_a"])
    dump(sim / f"{TIER_B}.json", data["tier_b"])
    dump(sim / "advnat_20990101T000000Z.json", [{"top_prompt": "Is the drivetrain worth fixing?"}])
    paths = {
        "questions": QUESTIONS,
        "pilot_run": run,
        "pilot_traces": traces,
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


def rerun(paths: dict[str, Path], out_dir: Path, **kw: Any) -> tuple[dict, bytes]:
    """Export the same world again into another directory."""
    assert evt.main(argv(paths, **kw) + ["--out-dir", str(out_dir)]) == 0
    raw = (out_dir / f"tasks_{STAMP}.json").read_bytes()
    return json.loads(raw), raw


def refused(tmp_path: Path, data: dict, code: str, **kw: Any) -> str:
    """Run the export expecting the named refusal; assert nothing was written; return the message."""
    paths = write_world(tmp_path, data)
    if "questions" in data:
        paths["questions"] = tmp_path / "questions.json"
        paths["questions"].write_text(json.dumps(data["questions"]), encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        evt.main(argv(paths, **kw))
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


def test_an_untraced_pilot_pair_is_refused(tmp_path):
    paths = write_world(tmp_path, world_data())
    summary = paths["pilot_traces"] / "batch_summary.part_01.json"
    doc = json.loads(summary.read_text())
    doc["results"] = doc["results"][:1]
    summary.write_text(json.dumps(doc))
    with pytest.raises(SystemExit) as exc:
        evt.main(argv(paths))
    assert "[bad_input]" in str(exc.value) and not paths["out_dir"].exists()


def test_an_existing_bundle_is_never_overwritten(tmp_path, capsys):
    _, raw, paths = export(tmp_path)
    with pytest.raises(SystemExit) as exc:
        evt.main(argv(paths))
    assert "[output_exists]" in str(exc.value)
    assert (paths["out_dir"] / f"tasks_{STAMP}.json").read_bytes() == raw


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

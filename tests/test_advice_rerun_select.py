"""Tests for scripts/advice_rerun_select.py - the post-hoc rerun selection ranker.

Offline: each test writes a tiny hash-chained responses archive, its judgments
file and a stimuli file into tmp_path, then ranks it. Covers the modal tie rule,
the exporter-style dedupe, the excluded-model rule, determinism under the seed,
row accounting, and refusal (not skipping) of malformed rows.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # dataclasses resolve string annotations through sys.modules
    spec.loader.exec_module(mod)
    return mod


sel = _load("advice_rerun_select")
ae = sel.ae

TIERS = ["self_care", "routine", "urgent", "emergency"]
RANK = {t: i for i, t in enumerate(TIERS)}
RUBRIC = {"version": "t-draft", "tiers": [{"id": t, "label": t, "definition": "d"} for t in TIERS],
          "flags": [], "judge_instructions": "{tiers}{flags}{response}"}
STEM = "stimuli_20990101T000000Z"
PRIMARY = "claude-haiku-4-5"


def _cell(sid, model, clinical, patient):
    out = []
    for arm, tiers in (("clinical", clinical), ("patient", patient)):
        for k, tier in enumerate(tiers, 1):
            out.append({"sid": sid, "arm": arm, "model": model, "k": k, "tier": tier})
    return out


def _write_archive(adir, samples, extra_judgments=()):
    """samples: dicts with sid, arm, model, k and optionally tier (absent = unjudged),
    judge, sent and text. Returns the response sha256 of each sample, in order."""
    adir.mkdir(parents=True, exist_ok=True)
    ids = sorted({s["sid"] for s in samples})
    (adir / f"{STEM}.json").write_text(json.dumps({"items": [{"id": i} for i in ids]}), encoding="utf-8")
    prev, lines, judgments, shas = None, [], [], []
    for n, s in enumerate(samples):
        text = s.get("text", f"placeholder response {n}")
        rec = {"record_type": "advice", "stimulus_id": s["sid"], "arm": s["arm"],
               "model_requested": s["model"], "sample_k": s["k"], "response_text": text,
               "response_sha256": ae.sha256_text(text), "sent_utc": s.get("sent", f"2099-01-01T00:00:{n:02d}Z")}
        sealed = ae._seal_record(rec, prev)
        prev = sealed["record_sha256"]
        lines.append(json.dumps(sealed))
        shas.append(rec["response_sha256"])
        if "tier" in s:
            judgments.append({"response_sha256": rec["response_sha256"], "stimulus_id": s["sid"],
                              "arm": s["arm"], "model": s["model"], "sample_k": s["k"],
                              "judge_model": s.get("judge", PRIMARY), "tier": s["tier"]})
    judgments.extend(extra_judgments)
    (adir / f"responses_{STEM}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (adir / f"judgments_{STEM}.jsonl").write_text(
        "\n".join(json.dumps(j) for j in judgments) + "\n", encoding="utf-8")
    return shas


def _rubric(tmp_path):
    path = tmp_path / "rubric.json"
    path.write_text(json.dumps(RUBRIC), encoding="utf-8")
    return path


def _build(tmp_path, exclude=("gemini",), seed=11, permutations=200, top=15):
    return sel.build_selection(tmp_path / "advice", [STEM], _rubric(tmp_path), PRIMARY, list(exclude),
                               "test note", top, seed, permutations)


def _run(tmp_path, samples, extra=(), **kw):
    _write_archive(tmp_path / "advice", samples, extra)
    return _build(tmp_path, **kw)


# ------------------------------------------------------------------ statistics


def test_modal_tie_breaks_toward_more_urgent():
    assert sel.modal_tier(["routine", "urgent"], RANK) == "urgent"
    assert sel.modal_tier(["self_care", "self_care", "emergency"], RANK) == "self_care"


def test_tie_rule_decides_the_downgrade(tmp_path):
    # clinical [routine, urgent] ties -> urgent; patient routine -> a one-tier downgrade.
    # Had ties gone toward the less urgent tier there would be no downgrade at all.
    out = _run(tmp_path, _cell("s1", "a:m1", ["routine", "urgent"], ["routine", "routine"]))
    item = out["items"][0]
    assert item["per_model"][0]["clinical_modal"] == "urgent"
    assert (item["downgrades"], item["sum_drop"]) == (1, 1)


def test_poisson_binomial_tail():
    dist = sel.poisson_binomial([0.5, 0.5])
    assert dist == [0.25, 0.5, 0.25]
    assert sel.tail(dist, 2) == 0.25
    assert sel.tail(dist, 3) == 0.0


# ---------------------------------------------------------------------- dedupe


def test_dedupe_keeps_one_sample_per_k_the_exporter_way(tmp_path, monkeypatch):
    monkeypatch.setitem(sel.DISPLAY_ALIASES, "via:vendor/m1", "direct:m1")
    samples = [
        # rerouted path sent first, direct path later: the direct path wins k=1
        {"sid": "s1", "arm": "clinical", "model": "via:vendor/m1", "k": 1, "tier": "self_care",
         "sent": "2099-01-01T00:00:00Z"},
        {"sid": "s1", "arm": "clinical", "model": "direct:m1", "k": 1, "tier": "emergency",
         "sent": "2099-01-01T00:00:05Z"},
        # the same spec and k twice: the earlier-sent record wins
        {"sid": "s1", "arm": "patient", "model": "direct:m1", "k": 1, "tier": "self_care",
         "sent": "2099-01-01T00:00:01Z"},
        {"sid": "s1", "arm": "patient", "model": "direct:m1", "k": 1, "tier": "emergency",
         "sent": "2099-01-01T00:00:09Z"},
    ]
    out = _run(tmp_path, samples)
    per_model = out["items"][0]["per_model"]
    assert [p["model"] for p in per_model] == ["direct:m1"]
    assert (per_model[0]["clinical_modal"], per_model[0]["patient_modal"]) == ("emergency", "self_care")
    assert (per_model[0]["n_clinical"], per_model[0]["n_patient"]) == (1, 1)
    assert out["row_accounting"][STEM]["response_records"]["excluded:duplicate_sample"] == 2


# ------------------------------------------------------------- excluded models


def test_gemini_downgrades_do_not_count_toward_the_rank(tmp_path):
    samples = (_cell("s1", "openrouter:google/gemini-x", ["urgent"] * 3, ["self_care"] * 3)
               + _cell("s1", "a:m1", ["routine"] * 3, ["routine"] * 3)
               + _cell("s2", "a:m1", ["routine"] * 3, ["self_care"] * 3)
               + _cell("s3", "google:gemini-y", ["urgent"] * 3, ["self_care"] * 3))
    out = _run(tmp_path, samples)
    assert [it["id"] for it in out["items"]] == ["s2", "s1"]  # s3 has no counted model: not ranked
    s1 = out["items"][1]
    assert (s1["downgrades"], s1["models_counted"]) == (0, 1)
    assert (s1["downgrades_with_excluded_models"], s1["models_with_excluded_models"]) == (1, 2)
    assert out["per_model"]["openrouter:google/gemini-x"]["downgrades"] == 1
    assert out["selection"]["n_stimuli_ranked"] == 2


def test_ranking_ties_break_by_drop_then_share_below(tmp_path):
    samples = (_cell("s1", "a:m1", ["urgent"] * 3, ["routine"] * 3)          # 1 down, drop 1
               + _cell("s2", "a:m1", ["emergency"] * 3, ["routine"] * 3)     # 1 down, drop 2
               + _cell("s3", "a:m1", ["urgent"] * 3, ["routine", "routine", "urgent"]))  # drop 1, fewer below
    out = _run(tmp_path, samples)
    assert [it["id"] for it in out["items"]] == ["s2", "s1", "s3"]


# --------------------------------------------------------------- determinism


def test_null_is_deterministic_under_the_seed_and_recorded(tmp_path):
    samples = (_cell("s1", "a:m1", ["urgent", "routine", "urgent"], ["routine", "self_care", "routine"])
               + _cell("s1", "b:m2", ["emergency", "urgent", "routine"], ["urgent", "routine", "self_care"]))
    _write_archive(tmp_path / "advice", samples)
    first = _build(tmp_path, seed=11)
    again = _build(tmp_path, seed=11)
    other = _build(tmp_path, seed=12)
    assert first["items"] == again["items"]
    assert (first["seed"], first["permutations"]) == (11, 200)
    assert "seed 11" in first["rule"] and "200 permutations" in first["rule"]
    q = [p["q_null"] for p in first["items"][0]["per_model"]]
    assert q != [p["q_null"] for p in other["items"][0]["per_model"]]


def test_a_cells_null_does_not_depend_on_other_cells(tmp_path):
    base = _cell("s1", "a:m1", ["urgent", "routine", "urgent"], ["routine", "self_care", "routine"])
    alone = _run(tmp_path / "one", base)
    more = _run(tmp_path / "two", _cell("s0", "a:m1", ["urgent", "self_care"], ["routine", "urgent"]) + base)
    q_alone = next(it for it in alone["items"] if it["id"] == "s1")["per_model"][0]["q_null"]
    q_more = next(it for it in more["items"] if it["id"] == "s1")["per_model"][0]["q_null"]
    assert q_alone == q_more


# ---------------------------------------------------- accounting and refusals


def test_excluded_rows_are_counted_by_reason(tmp_path):
    samples = (_cell("s1", "a:m1", ["routine"], ["self_care"])
               + [{"sid": "s1", "arm": "patient", "model": "a:m1", "k": 2},  # never judged
                  {"sid": "s1", "arm": "translated", "model": "a:m1", "k": 1, "tier": "routine"}])
    shas = _write_archive(tmp_path / "advice", samples)
    row = {"response_sha256": shas[0], "stimulus_id": "s1", "arm": "clinical", "model": "a:m1",
           "sample_k": 1, "judge_model": PRIMARY, "tier": "routine"}
    extra = [
        {**row, "judge_model": "openrouter:vendor/second-judge", "tier": "emergency"},
        {**row, "judge_model": "some-other-bare-judge", "tier": "emergency"},
        {**row, "tier": None},
        {**row, "tier": "urgent"},  # a later primary judgment of the same response wins
    ]
    _write_archive(tmp_path / "advice", samples, extra)
    out = _build(tmp_path)
    acc = out["row_accounting"][STEM]
    assert acc["judgment_rows"] == {"excluded:secondary_judge": 1, "excluded:other_judge": 1,
                                    "excluded:null_tier": 1, "excluded:superseded_by_later_judgment": 1,
                                    "used": 3}
    assert acc["response_records"] == {"advice": 4, "excluded:no_primary_tier": 1,
                                       "excluded:translated_arm": 1, "used": 2}
    assert out["items"][0]["per_model"][0]["clinical_modal"] == "urgent"


def _good_row(sha):
    return {"response_sha256": sha, "stimulus_id": "s1", "arm": "clinical", "model": "a:m1",
            "sample_k": 1, "judge_model": PRIMARY, "tier": "routine"}


@pytest.mark.parametrize("mutate", [
    lambda j: j.pop("arm"),
    lambda j: j.update(arm="sideways"),
    lambda j: j.update(tier="not_a_tier"),
    lambda j: j.pop("tier"),
    lambda j: j.update(sample_k="1"),
    lambda j: j.update(sample_k=True),
    lambda j: j.update(sample_k=0),
    lambda j: j.update(response_sha256="not-a-digest"),
    lambda j: j.update(response_sha256="0" * 64),   # a response the archive does not hold
    lambda j: j.update(stimulus_id="s2"),           # key does not match the archived response
    lambda j: j.update(judge_model=""),
    lambda j: j.pop("model"),
], ids=["no-arm", "bad-arm", "unknown-tier", "no-tier", "k-string", "k-bool", "k-zero", "bad-sha",
        "orphan-sha", "key-mismatch", "empty-judge", "no-model"])
def test_malformed_judgment_rows_are_refused(tmp_path, mutate):
    samples = _cell("s1", "a:m1", ["routine"], ["routine"])
    shas = _write_archive(tmp_path / "advice", samples)
    bad = _good_row(shas[0])
    mutate(bad)
    _write_archive(tmp_path / "advice", samples, [bad])
    with pytest.raises(SystemExit, match=r"judgments_.*\.jsonl:\d+: .*refusing"):
        _build(tmp_path)


def test_non_object_and_corrupt_judgment_lines_are_refused(tmp_path):
    samples = _cell("s1", "a:m1", ["routine"], ["routine"])
    _write_archive(tmp_path / "advice", samples, [[1, 2]])
    with pytest.raises(SystemExit, match="not a JSON object"):
        _build(tmp_path)
    path = tmp_path / "advice" / f"judgments_{STEM}.jsonl"
    path.write_text(path.read_text(encoding="utf-8") + "{not json\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="corrupt JSONL line"):
        _build(tmp_path)


def test_malformed_advice_record_is_refused(tmp_path):
    samples = _cell("s1", "a:m1", ["routine"], ["routine"])
    samples[0]["k"] = "1"
    samples[0].pop("tier")
    _write_archive(tmp_path / "advice", samples)
    with pytest.raises(SystemExit, match="malformed advice record"):
        _build(tmp_path)


def test_broken_chain_is_refused(tmp_path):
    _write_archive(tmp_path / "advice", _cell("s1", "a:m1", ["routine"], ["routine"]))
    path = tmp_path / "advice" / f"responses_{STEM}.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    rows[0]["response_text"] = "edited after landing"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="refusing to rank"):
        _build(tmp_path)


# --------------------------------------------------------------------- CLI


def test_cli_writes_the_selection_shape_and_refuses_to_overwrite(tmp_path):
    _write_archive(tmp_path / "advice", _cell("s1", "a:m1", ["urgent"] * 3, ["self_care"] * 3))
    out = tmp_path / "advice" / "rerun_selection_test.json"
    args = ["--advice-dir", str(tmp_path / "advice"), "--rubric", str(_rubric(tmp_path)),
            "--permutations", "50", "--out", str(out)]
    sel.main(args)
    written = json.loads(out.read_text(encoding="utf-8"))
    assert isinstance(written["rule"], str) and "post hoc" in written["rule"].lower()
    assert written["items"][0]["file"].endswith(f"{STEM}.json")
    assert written["items"][0]["id"] == "s1"
    assert written["seed"] == sel.DEFAULT_SEED
    assert {i["path"].rsplit("/", 1)[-1] for i in written["inputs"]} >= {
        f"{STEM}.json", f"responses_{STEM}.jsonl", f"judgments_{STEM}.jsonl", "rubric.json"}
    assert all(len(i["sha256"]) == 64 for i in written["inputs"])
    with pytest.raises(SystemExit, match="append-only"):
        sel.main(args)

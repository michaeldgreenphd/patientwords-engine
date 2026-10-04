"""Tests for scripts/advice_rerun_select.py - the post-hoc rerun selection ranker.

Offline: each test writes a tiny hash-chained responses archive with its sidecar,
its judgments file and a stimuli file into tmp_path, then ranks it. Covers the modal tie rule,
the exporter-style dedupe, the excluded-model rule, determinism under the seed,
the noise-floor decision (expected count at the item's own downgrade count, over
every ranked stimulus, and the Bonferroni figures),
row accounting, refusal (not skipping) of malformed rows, the archive's binding to
its sidecar, its stimuli document and the rubric, duplicate stems, and the two files the
CLI writes: the ranking report, unchanged in content, and the selection in
exactly the shape build-stimuli --source selection reads, whose notes carry the
report's sha256.
"""

import hashlib
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
RUBRIC_SHA = ae.sha256_text(ae.canonical_json(RUBRIC))   # what advice_eval.py judge stamps on each row


def _cell(sid, model, clinical, patient):
    out = []
    for arm, tiers in (("clinical", clinical), ("patient", patient)):
        for k, tier in enumerate(tiers, 1):
            out.append({"sid": sid, "arm": arm, "model": model, "k": k, "tier": tier})
    return out


def _write_archive(adir, samples, extra_judgments=()):
    """samples: dicts with sid, arm, model, k and optionally tier (absent = unjudged),
    judge, rubric_sha (default the test rubric's), sent and text. Writes the stimuli
    file, the responses archive (each advice record stamped with the stimuli document's
    canonical sha256, as elicit stamps it), its sidecar (records_total and chain_head,
    as elicit writes them) and the judgments. Returns the response sha256 of each
    sample, in order."""
    adir.mkdir(parents=True, exist_ok=True)
    ids = sorted({s["sid"] for s in samples})
    # complete stimuli (bodies, messages, hashes), so build-stimuli's selection reader can load them too
    items = [ae._stimulus(i, f"placeholder clinical {i}", f"placeholder patient {i}", "placeholder ask?")
             for i in ids]
    stimuli_doc = {"ask_suffix": "placeholder ask?", "items": items}
    (adir / f"{STEM}.json").write_text(json.dumps(stimuli_doc), encoding="utf-8")
    stimuli_sha = ae.sha256_text(ae.canonical_json(stimuli_doc))
    prev, lines, judgments, shas = None, [], [], []
    for n, s in enumerate(samples):
        text = s.get("text", f"placeholder response {n}")
        rec = {"record_type": "advice", "stimulus_id": s["sid"], "arm": s["arm"],
               "model_requested": s["model"], "sample_k": s["k"], "response_text": text,
               "response_sha256": ae.sha256_text(text), "sent_utc": s.get("sent", f"2099-01-01T00:00:{n:02d}Z"),
               "stimuli_sha256": stimuli_sha}
        sealed = ae._seal_record(rec, prev)
        prev = sealed["record_sha256"]
        lines.append(json.dumps(sealed))
        shas.append(rec["response_sha256"])
        if "tier" in s:
            judgments.append({"response_sha256": rec["response_sha256"], "stimulus_id": s["sid"],
                              "arm": s["arm"], "model": s["model"], "sample_k": s["k"],
                              "judge_model": s.get("judge", PRIMARY), "tier": s["tier"],
                              "rubric_sha256": s.get("rubric_sha", RUBRIC_SHA)})
    judgments.extend(extra_judgments)
    (adir / f"responses_{STEM}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (adir / f"responses_{STEM}.report.json").write_text(
        json.dumps({"records_total": len(lines), "chain_head": prev}), encoding="utf-8")
    (adir / f"judgments_{STEM}.jsonl").write_text(
        "\n".join(json.dumps(j) for j in judgments) + "\n", encoding="utf-8")
    return shas


def _rubric(tmp_path):
    path = tmp_path / "rubric.json"
    path.write_text(json.dumps(RUBRIC), encoding="utf-8")
    return path


def _build(tmp_path, exclude=("gemini",), seed=11, permutations=200, top=15):
    return sel.build_report(tmp_path / "advice", [STEM], _rubric(tmp_path), PRIMARY, list(exclude),
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
           "sample_k": 1, "judge_model": PRIMARY, "tier": "routine", "rubric_sha256": RUBRIC_SHA}
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
            "sample_k": 1, "judge_model": PRIMARY, "tier": "routine", "rubric_sha256": RUBRIC_SHA}


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
    lambda j: j.pop("rubric_sha256"),               # every judgment names the rubric it was made under
    lambda j: j.update(rubric_sha256="draft-1"),
], ids=["no-arm", "bad-arm", "unknown-tier", "no-tier", "k-string", "k-bool", "k-zero", "bad-sha",
        "orphan-sha", "key-mismatch", "empty-judge", "no-model", "no-rubric-sha", "bad-rubric-sha"])
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


# ------------------------------------- binding to the sidecar, the stimuli and the rubric


def _rewrite_jsonl(path, keep):
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    path.write_text("".join(json.dumps(r) + "\n" for r in rows[:keep]), encoding="utf-8")


def test_an_archive_cut_back_to_an_earlier_prefix_is_refused(tmp_path):
    # Regression (Codex, PR #73 post-merge): a responses archive and its judgments cut back consistently to an
    # earlier prefix still pass verify_chain, and every remaining judgment resolves, so the ranking used to be
    # computed from the shorter archive. The sidecar's records_total and chain_head describe the full archive.
    samples = (_cell("s1", "a:m1", ["urgent"] * 2, ["self_care"] * 2)
               + _cell("s2", "a:m1", ["urgent"] * 2, ["self_care"] * 2))
    _write_archive(tmp_path / "advice", samples)
    _build(tmp_path)   # the full archive ranks
    adir = tmp_path / "advice"
    _rewrite_jsonl(adir / f"responses_{STEM}.jsonl", 4)
    _rewrite_jsonl(adir / f"judgments_{STEM}.jsonl", 4)
    assert ae.verify_chain(ae._read_jsonl(adir / f"responses_{STEM}.jsonl"))[0]   # the prefix is internally valid
    with pytest.raises(SystemExit, match=r"holds 4 record\(s\) but .*records_total 8; refusing"):
        _build(tmp_path)


@pytest.mark.parametrize("sidecar, message", [
    (None, "missing"),
    ({"chain_head": "0" * 64}, "records_total None is missing"),
    ({"records_total": "4"}, "records_total '4' is missing or not a non-negative integer"),
    ({"records_total": 4}, "chain_head None is missing"),
    ({"records_total": 4, "chain_head": "0" * 64}, "ends at record .* but .* records chain_head 000000000000"),
], ids=["no-sidecar", "no-total", "total-string", "no-head", "other-head"])
def test_a_sidecar_that_does_not_describe_the_archive_is_refused(tmp_path, sidecar, message):
    _write_archive(tmp_path / "advice", _cell("s1", "a:m1", ["urgent"] * 2, ["self_care"] * 2))
    path = tmp_path / "advice" / f"responses_{STEM}.report.json"
    if sidecar is None:
        path.unlink()
    else:
        path.write_text(json.dumps(sidecar), encoding="utf-8")
    with pytest.raises(SystemExit, match=message):
        _build(tmp_path)


def test_responses_elicited_from_another_stimuli_document_are_refused(tmp_path):
    # Regression (Codex, PR #73 post-merge): a stimuli file edited after elicitation, with the same ids, passed the
    # id-membership check, and the selection then copied messages the responses were never sent.
    _write_archive(tmp_path / "advice", _cell("s1", "a:m1", ["urgent"] * 2, ["self_care"] * 2))
    path = tmp_path / "advice" / f"{STEM}.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["items"][0]["patient_message"] = "placeholder patient s1, edited after elicitation"
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(SystemExit, match="elicited from a stimuli document with canonical sha256 .* refusing"):
        _build(tmp_path)


def test_an_advice_record_without_its_stimuli_hash_is_refused(tmp_path):
    adir = tmp_path / "advice"
    _write_archive(adir, _cell("s1", "a:m1", ["urgent"], ["self_care"]))
    path = adir / f"responses_{STEM}.jsonl"
    prev, lines = None, []
    for line in path.read_text(encoding="utf-8").splitlines():
        body = {k: v for k, v in json.loads(line).items() if k not in ("prev_sha256", "record_sha256",
                                                                      "stimuli_sha256")}
        sealed = ae._seal_record(body, prev)   # resealed, so only the missing hash is wrong
        prev = sealed["record_sha256"]
        lines.append(json.dumps(sealed))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (adir / f"responses_{STEM}.report.json").write_text(json.dumps({"records_total": 2, "chain_head": prev}),
                                                        encoding="utf-8")
    with pytest.raises(SystemExit, match="malformed advice record: stimuli_sha256 is not"):
        _build(tmp_path)


OTHER_RUBRIC_SHA = ae.sha256_text(ae.canonical_json({**RUBRIC, "version": "t-draft-2"}))   # same tier ids


def test_judgments_made_under_another_rubric_are_refused_when_none_match(tmp_path):
    # Regression (Codex, PR #73 post-merge): rows judged under another rubric revision with the same tier ids
    # passed validation, and the report attributed the ranking to the supplied rubric's version and hash.
    samples = _cell("s1", "a:m1", ["urgent"] * 2, ["self_care"] * 2)
    for s in samples:
        s["rubric_sha"] = OTHER_RUBRIC_SHA
    _write_archive(tmp_path / "advice", samples)
    with pytest.raises(SystemExit, match=f"made under another rubric \\({OTHER_RUBRIC_SHA[:12]} \\(4 rows\\)\\)"):
        _build(tmp_path)


def test_judgments_made_under_another_rubric_are_excluded_and_counted(tmp_path):
    # a later re-judge under another rubric does not displace the supplied rubric's tier, and is counted
    samples = _cell("s1", "a:m1", ["urgent"], ["urgent"])
    shas = _write_archive(tmp_path / "advice", samples)
    later = {"response_sha256": shas[1], "stimulus_id": "s1", "arm": "patient", "model": "a:m1", "sample_k": 1,
             "judge_model": PRIMARY, "tier": "self_care", "rubric_sha256": OTHER_RUBRIC_SHA}
    _write_archive(tmp_path / "advice", samples, [later])
    out = _build(tmp_path)
    assert out["items"][0]["per_model"][0]["patient_modal"] == "urgent"
    assert out["items"][0]["downgrades"] == 0
    assert out["row_accounting"][STEM]["judgment_rows"] == {"excluded:other_rubric": 1, "used": 2}
    assert out["rubric"]["canonical_sha256"] == RUBRIC_SHA


def test_a_judgment_under_another_rubric_with_a_tier_this_rubric_lacks_is_excluded_not_refused(tmp_path):
    # Regression (Gemini review of PR #82): the tier was checked against the supplied rubric before rows made under
    # another rubric were set aside, so a re-judge under a revised tier vocabulary stopped the run instead of being
    # excluded and counted.
    samples = _cell("s1", "a:m1", ["urgent"], ["urgent"])
    shas = _write_archive(tmp_path / "advice", samples)
    later = {"response_sha256": shas[1], "stimulus_id": "s1", "arm": "patient", "model": "a:m1", "sample_k": 1,
             "judge_model": PRIMARY, "tier": "legacy_tier", "rubric_sha256": OTHER_RUBRIC_SHA}
    _write_archive(tmp_path / "advice", samples, [later])
    out = _build(tmp_path)
    assert out["items"][0]["per_model"][0]["patient_modal"] == "urgent"
    assert out["row_accounting"][STEM]["judgment_rows"] == {"excluded:other_rubric": 1, "used": 2}


def test_a_judgment_under_the_supplied_rubric_with_an_unknown_tier_is_refused(tmp_path):
    samples = _cell("s1", "a:m1", ["urgent"], ["urgent"])
    shas = _write_archive(tmp_path / "advice", samples)
    bad = {"response_sha256": shas[1], "stimulus_id": "s1", "arm": "patient", "model": "a:m1", "sample_k": 1,
           "judge_model": PRIMARY, "tier": "legacy_tier", "rubric_sha256": RUBRIC_SHA}
    _write_archive(tmp_path / "advice", samples, [bad])
    with pytest.raises(SystemExit, match="'legacy_tier' is not a tier id of the rubric it was made under"):
        _build(tmp_path)


def test_a_stem_named_twice_is_refused(tmp_path):
    # Regression (Codex, PR #73 post-merge): a repeated --stem loaded the archive twice and counted every one of its
    # cells twice, in the downgrade counts and as independent draws in the null.
    _two_stimuli(tmp_path)
    with pytest.raises(SystemExit, match=f"named more than once: {STEM}"):
        sel.build_report(tmp_path / "advice", [STEM, STEM], _rubric(tmp_path), PRIMARY, ["gemini"], "test note",
                         15, 11, 50)
    report_path, selection_path, base, _ = _cli_args(tmp_path)
    with pytest.raises(SystemExit, match="named more than once"):
        sel.main(base + ["--stem", STEM, "--stem", STEM,
                         "--report-out", str(report_path), "--selection-out", str(selection_path)])
    assert not report_path.exists() and not selection_path.exists()


# --------------------------------------------------------------------- CLI


# Every key the report carried before the builder-ready selection was split out of it (2026-10-02): the split
# moved nothing out of the report.
REPORT_KEYS = {"rule", "items", "selection", "seed", "permutations", "judge_model", "excluded_models", "rubric",
               "display_aliases", "inputs", "row_accounting", "per_model", "generated_utc", "engine_sha", "script",
               "command"}
REPORT_ITEM_KEYS = {"file", "id", "rank", "downgrades", "models_counted", "sum_drop", "severe_downgrades", "upgrades",
                    "patient_samples_below_clinical_modal", "patient_samples",
                    "share_patient_samples_below_clinical_modal", "downgrades_with_excluded_models",
                    "models_with_excluded_models", "null_expected_downgrades", "p_tail", "p_tail_bonferroni",
                    "null_expected_stimuli_at_or_above", "observed_stimuli_at_or_above", "clears_noise_floor",
                    "per_model"}


def _two_stimuli(tmp_path):
    _write_archive(tmp_path / "advice", _cell("s1", "a:m1", ["urgent"] * 3, ["self_care"] * 3)
                   + _cell("s2", "a:m1", ["routine"] * 3, ["self_care"] * 3))


def _cli_args(tmp_path):
    """(report path, selection path, the arguments without outputs, the arguments with both outputs)."""
    report = tmp_path / "advice" / "rerun_ranking_test.json"
    selection = tmp_path / "advice" / "rerun_selection_test.json"
    base = ["--advice-dir", str(tmp_path / "advice"), "--rubric", str(_rubric(tmp_path)), "--permutations", "50"]
    return report, selection, base, base + ["--report-out", str(report), "--selection-out", str(selection)]


def test_cli_writes_the_ranking_report_unchanged_in_content(tmp_path):
    _two_stimuli(tmp_path)
    report_path, _, _, args = _cli_args(tmp_path)
    returned = sel.main(args)
    written = json.loads(report_path.read_text(encoding="utf-8"))
    assert written == json.loads(json.dumps(returned))   # the file holds what the run computed
    assert set(written) == REPORT_KEYS
    assert [it["id"] for it in written["items"]] == ["s1", "s2"]
    assert all(set(it) == REPORT_ITEM_KEYS for it in written["items"])
    assert written["items"][0]["file"].endswith(f"{STEM}.json")
    assert (written["seed"], written["permutations"]) == (sel.DEFAULT_SEED, 50)
    assert {i["path"].rsplit("/", 1)[-1] for i in written["inputs"]} >= {
        f"{STEM}.json", f"responses_{STEM}.jsonl", f"judgments_{STEM}.jsonl", "rubric.json"}
    assert all(len(i["sha256"]) == 64 for i in written["inputs"])
    # and it is what build_report computes from the same inputs: writing it adds and drops nothing
    direct = sel.build_report(tmp_path / "advice", [STEM], _rubric(tmp_path), PRIMARY, list(sel.DEFAULT_EXCLUDE),
                              sel.DEFAULT_EXCLUDE_NOTE, sel.DEFAULT_TOP, sel.DEFAULT_SEED, 50)
    for doc in (written, direct):
        doc.pop("generated_utc")
        doc.pop("command")
    assert written == json.loads(json.dumps(direct))


def test_cli_writes_the_selection_in_exactly_the_shape_build_stimuli_reads(tmp_path):
    _two_stimuli(tmp_path)
    report_path, selection_path, _, args = _cli_args(tmp_path)
    sel.main(args)
    report_bytes = report_path.read_bytes()
    report = json.loads(report_bytes)
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    # build-stimuli --source selection refuses any other key, at either level
    assert set(selection) == {"rule", "items", "notes"} == ae.SELECTION_KEYS
    assert all(set(entry) == {"file", "id"} == ae.SELECTION_ENTRY_KEYS for entry in selection["items"])
    assert selection["rule"] == report["rule"]
    ranked = sorted(report["items"], key=lambda it: it["rank"])
    assert selection["items"] == [{"file": it["file"], "id": it["id"]} for it in ranked]
    notes = selection["notes"]
    assert isinstance(notes, str)
    # the report by path and by the sha256 of the file as written
    assert f"{report_path} (sha256 {hashlib.sha256(report_bytes).hexdigest()})" in notes
    assert f"seed {sel.DEFAULT_SEED}" in notes and "50 permutations" in notes and "post hoc" in notes


def test_the_selection_is_accepted_by_build_stimulis_reader(tmp_path, monkeypatch):
    # The holdout seal is build-stimuli's own step (tested in test_advice_eval.py) and needs a dashboard and Tier B
    # batch files; it is stubbed so this test checks only that the reader accepts the file the ranker writes.
    monkeypatch.setattr(ae, "_selection_seal_check", lambda *a, **k: {"tierb": False, "accepted_prompt": False})
    _two_stimuli(tmp_path)
    _, selection_path, _, args = _cli_args(tmp_path)
    report = sel.main(args)
    items, source, ask = ae.select_stimuli(selection_path, tmp_path / "no_dashboard.json", tmp_path / "no_sim")
    assert [it["meta"]["rerun_of"]["id"] for it in items] == [it["id"] for it in report["items"]]
    assert source["rule"] == report["rule"]
    assert source["notes"] == json.loads(selection_path.read_text(encoding="utf-8"))["notes"]
    assert ask == "placeholder ask?"


def test_cli_refuses_to_overwrite_either_file(tmp_path):
    _two_stimuli(tmp_path)
    report_path, _, _, args = _cli_args(tmp_path)
    sel.main(args)
    with pytest.raises(SystemExit, match="append-only"):
        sel.main(args)
    # with only the selection left the run is refused before anything is written, so no report is written again
    report_path.unlink()
    with pytest.raises(SystemExit, match="append-only"):
        sel.main(args)
    assert not report_path.exists()


def test_cli_writes_the_two_files_together_or_not_at_all(tmp_path):
    _two_stimuli(tmp_path)
    report_path, selection_path, base, _ = _cli_args(tmp_path)
    with pytest.raises(SystemExit, match="written together"):
        sel.main(base + ["--report-out", str(report_path)])
    with pytest.raises(SystemExit, match="written together"):
        sel.main(base + ["--selection-out", str(selection_path)])
    with pytest.raises(SystemExit, match="same file"):
        sel.main(base + ["--report-out", str(report_path), "--selection-out", str(report_path)])
    assert not report_path.exists() and not selection_path.exists()


# ----------------------------------------------------------------- noise floor


def _fixed_q(clinical, patient, rank, permutations, rng):
    """Stand-in null with known q: 0 when every label in the cell agrees (as the real
    permutation null gives exactly), 0.1 for an emergency-vs-self_care cell, else 0.5."""
    if len(set(clinical) | set(patient)) == 1:
        return 0.0
    if clinical == ["emergency"] and patient == ["self_care"]:
        return 0.1
    return 0.5


def test_noise_floor_uses_the_expected_count_at_the_items_own_downgrade_count(tmp_path, monkeypatch):
    monkeypatch.setattr(sel, "downgrade_null_probability", _fixed_q)
    samples = []
    # s1: three models, each a downgrade with q = 0.1 -> count 3, tail(3) = 0.001
    for m in ("a:m1", "a:m2", "a:m3"):
        samples += _cell("s1", m, ["emergency"], ["self_care"])
    # s3: two models, each a downgrade with q = 0.5 -> count 2, dist [0.25, 0.5, 0.25]
    for m in ("a:m1", "a:m2"):
        samples += _cell("s3", m, ["urgent"], ["routine"])
    # s2: one model with an upgrade (q = 0.5, count 0) and one whose labels all agree (q = 0)
    samples += _cell("s2", "a:m1", ["routine"], ["urgent"])
    samples += _cell("s2", "a:m2", ["routine"], ["routine"])
    out = _run(tmp_path, samples)

    # E(k) = sum over all three ranked stimuli of P(count >= k):
    # s1 dist [0.729, 0.243, 0.027, 0.001]; s3 [0.25, 0.5, 0.25]; s2 [0.5, 0.5, 0].
    # (the list runs to k = 4, one past the largest count any stimulus could reach)
    assert out["selection"]["null_expected_stimuli_at_or_above"] == [3.0, 1.521, 0.278, 0.001, 0.0]
    assert out["selection"]["observed_stimuli_at_or_above"] == [3, 2, 2, 1, 0]
    by_id = {it["id"]: it for it in out["items"]}
    assert [it["id"] for it in out["items"]] == ["s1", "s3", "s2"]
    # s1 is read at its own count, 3: E(3) = 0.001 < 0.05 -> clears
    assert by_id["s1"]["null_expected_stimuli_at_or_above"] == 0.001
    assert by_id["s1"]["clears_noise_floor"] is True
    # s3 at count 2: E(2) = 0.028 + 0.25 = 0.278 -> does not clear
    assert by_id["s3"]["null_expected_stimuli_at_or_above"] == 0.278
    assert by_id["s3"]["clears_noise_floor"] is False
    # s2 has no downgrade, so it can never clear
    assert by_id["s2"]["clears_noise_floor"] is False
    assert out["selection"]["items_clearing_noise_floor"] == [1]
    # Bonferroni over the 3 ranked stimuli: s1 0.001 x 3 = 0.003; s3 0.25 x 3 = 0.75
    assert by_id["s1"]["p_tail"] == 0.001 and by_id["s1"]["p_tail_bonferroni"] == 0.003
    assert by_id["s3"]["p_tail_bonferroni"] == 0.75
    assert out["selection"]["items_clearing_bonferroni"] == [1]
    assert "Items clearing it: #1;" in out["rule"]
    assert "items clearing 0.05: #1 (adjusted p 0.0030)" in out["rule"]


def test_noise_floor_counts_every_ranked_stimulus_not_only_the_selected_ones(tmp_path, monkeypatch):
    # The same archive with --top 1: E(k) must still sum over all three ranked stimuli.
    monkeypatch.setattr(sel, "downgrade_null_probability", _fixed_q)
    samples = []
    for m in ("a:m1", "a:m2", "a:m3"):
        samples += _cell("s1", m, ["emergency"], ["self_care"])
    for m in ("a:m1", "a:m2"):
        samples += _cell("s3", m, ["urgent"], ["routine"])
    samples += _cell("s2", "a:m1", ["routine"], ["urgent"])
    out = _run(tmp_path, samples, top=1)
    assert len(out["items"]) == 1
    assert out["selection"]["n_stimuli_ranked"] == 3
    assert out["selection"]["null_expected_stimuli_at_or_above"][1] == 1.521


def test_bonferroni_phrase_names_the_smallest_adjusted_p_when_none_clears():
    items = [{"rank": 1, "downgrades": 4, "p_tail_bonferroni": 0.069},
             {"rank": 2, "downgrades": 2, "p_tail_bonferroni": 0.9}]
    assert sel._bonferroni_phrase(items) == "no item clears 0.05 (smallest adjusted p 0.0690, item #1)"
    # an item with no downgrade never counts as clearing, whatever its adjusted p
    assert sel._bonferroni_phrase([{"rank": 1, "downgrades": 0, "p_tail_bonferroni": 0.01}]).startswith(
        "no item clears")

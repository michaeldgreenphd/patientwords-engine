import json

import pytest
from conftest import TEST_KEYWORD_CONFIG, build_fetcher, make_graph

import medlang_circuits.batch_eval as batch_eval
from medlang_circuits.targets import (
    AttributionTargets,
    logit_spread,
    parse_logit_clerp,
    retarget_graph,
    select_logits,
    target_probability,
)


def _two_logit_graph():
    """Fixture graph plus a second, higher-probability article logit ('a')."""
    g = make_graph()
    g["nodes"].append({"node_id": "L_a", "feature": 1000, "layer": "26", "ctx_idx": 3,
                       "feature_type": "logit", "jsNodeId": "L_a-3", "clerp": "a (p=0.9)"})
    g["links"].append({"source": "7_00007_2", "target": "L_a", "weight": 3.0})
    return g


def test_parse_logit_clerp():
    assert parse_logit_clerp("therapist (p=0.62)") == ("therapist", 0.62)
    assert parse_logit_clerp("plain label") == ("plain label", None)
    assert parse_logit_clerp(None) == ("", None)


def test_retarget_graph_prunes_other_logits():
    g = _two_logit_graph()
    info = retarget_graph(g, AttributionTargets.of([" jumps"]))
    assert info["retargeted"] is True
    ids = {n["node_id"] for n in g["nodes"]}
    assert "L_999_3" in ids and "L_a" not in ids  # substantive target kept, article dropped
    assert all(link["target"] != "L_a" for link in g["links"])  # dangling edges pruned
    assert g["metadata"]["attribution_targets"]["dropped"] == ["a (p=0.9)"]


def test_retarget_no_match_leaves_graph_untouched():
    g = _two_logit_graph()
    n_nodes, n_links = len(g["nodes"]), len(g["links"])
    info = retarget_graph(g, AttributionTargets.of([" zebra"]))
    assert info["retargeted"] is False
    assert len(g["nodes"]) == n_nodes and len(g["links"]) == n_links


def test_target_probability_selection():
    g = _two_logit_graph()
    assert target_probability(g) == ("a", 0.9)  # top logit is the article
    assert target_probability(g, anchor=" jumps") == ("jumps", 0.81)
    assert target_probability(g, targets=AttributionTargets.of([" jumps"])) == ("jumps", 0.81)
    assert target_probability(g, anchor=" zebra") is None


def test_target_probability_hosted_labels_and_wordpieces():
    # Hosted logit labels arrive wrapped ('Output " anti"') and tokenizers
    # split intended targets into leading wordpieces - anchoring must see
    # through both, with a short-token guard.
    g = _two_logit_graph()
    for node in g["nodes"]:
        if node["node_id"] == "L_999_3":
            node["clerp"] = 'Output " anti" (p=0.30)'
        if node["node_id"] == "L_a":
            node["clerp"] = 'Output " tissues" (p=0.13)'
    assert target_probability(g, anchor=" antihistamines") == ('Output " anti"', 0.30)
    assert target_probability(g, anchor=" tissue") == ('Output " tissues"', 0.13)
    assert target_probability(g, anchor=" an") is None  # stub tokens can't match everything
    assert target_probability(g, anchor=" zebra") is None


def test_logit_spread_and_select_logits():
    g = _two_logit_graph()
    assert logit_spread(g) == [("a", 0.9), ("jumps", 0.81)]
    assert logit_spread(g, k=1) == [("a", 0.9)]

    # top-k pruning alone drops the weaker logit
    g1 = _two_logit_graph()
    info = select_logits(g1, keep_top_k=1)
    assert info["dropped"] == ["jumps (p=0.81)"]
    assert "L_999_3" not in {n["node_id"] for n in g1["nodes"]}

    # forced targets are kept in addition to the top-k spread
    g2 = _two_logit_graph()
    info = select_logits(g2, targets=AttributionTargets.of([" jumps"]), keep_top_k=1)
    assert info["dropped"] == []
    assert {n["node_id"] for n in g2["nodes"] if n["feature_type"] == "logit"} == {"L_999_3", "L_a"}
    assert g2["metadata"]["logit_selection"]["requested_targets"] == [" jumps"]


def test_run_batch_offline_with_mitigation(tmp_path, monkeypatch):
    # offline phrase table so the mitigation step restores the clinical phrasing
    config = tmp_path / "keyword_config.json"
    config.write_text(
        json.dumps({**TEST_KEYWORD_CONFIG, "translations": {"patient phrasing": "clinical phrasing"}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("MEDLANG_KEYWORD_CONFIG", str(config))

    calls = []

    def fake_generate(prompt, slug=None, backend="hosted", **params):
        calls.append({"prompt": prompt, "params": params})
        g = _two_logit_graph()
        p = 0.81 if "clinical" in prompt else 0.4  # patient phrasing degrades the target token
        for node in g["nodes"]:
            if node["node_id"] == "L_999_3":
                node["clerp"] = f"jumps (p={p})"
        g["metadata"]["prompt"] = prompt
        return g

    monkeypatch.setattr(batch_eval, "generate_graph", fake_generate)

    pairs = tmp_path / "pairs.json"
    pairs.write_text(
        json.dumps([{
            "top_prompt": "clinical phrasing about the fox",
            "bottom_prompt": "patient phrasing about the fox",
            "target_clinical_token": " jumps",
            "force_target_tokens": [" jumps"],
        }]),
        encoding="utf-8",
    )

    results = batch_eval.run_batch(
        str(pairs), out_dir=str(tmp_path / "out"),
        show_mitigation=True, use_llm_translation=False, dpi=60, fetcher=build_fetcher(),
    )

    assert len(results) == 1
    r = results[0]
    assert r["target_token"] == "jumps"
    assert r["probabilities"] == {"clinical": 0.81, "patient": 0.4, "translated": 0.81}
    assert r["language_penalty"] == pytest.approx(-0.41)
    assert r["mitigation_recovery"] == pytest.approx(0.41)
    assert r["translation_method"] == "phrase_table"
    # forced targets widen the salient-logit set and pass through to generation
    assert calls[0]["params"]["max_n_logits"] == 15
    assert calls[0]["params"]["force_target_tokens"] == [" jumps"]
    assert len(calls) == 3  # clinical, patient, translated

    out = tmp_path / "out"
    assert (out / "index_01.png").stat().st_size > 1000
    assert (out / "batch_summary.json").is_file()
    assert (out / "pair_01_translated.tagged.json").is_file()

    html = (out / "index_01.html").read_text(encoding="utf-8")
    # three stacked panels with both delta badges centered in the gaps
    assert html.count('<g transform="translate(0,') == 3
    assert "Language Penalty: -41% probability (0.81 → 0.40)" in html
    assert "Mitigation Recovery: +41% probability (0.40 → 0.81)" in html
    # the predictive spread keeps the article logit visible (prob notation, no p= syntax)
    assert "“a” · prob 0.90" in html
    assert "“jumps” · prob 0.81" in html
    assert r["predictive_spread"]["clinical"] == [("a", 0.9), ("jumps", 0.81)]
    assert r["predictive_spread"]["patient"] == [("a", 0.9), ("jumps", 0.4)]


def test_run_batch_checkpoints_and_start_index(tmp_path, monkeypatch):
    def fake_generate(prompt, slug=None, backend="hosted", **params):
        if "boom" in prompt:
            raise RuntimeError("hosted backend fell over")
        return _two_logit_graph()

    monkeypatch.setattr(batch_eval, "generate_graph", fake_generate)

    pairs = tmp_path / "pairs.json"
    pairs.write_text(
        json.dumps([
            {"top_prompt": "clinical one", "bottom_prompt": "patient one", "target_clinical_token": " jumps"},
            {"top_prompt": "clinical boom", "bottom_prompt": "patient boom", "target_clinical_token": " jumps"},
        ]),
        encoding="utf-8",
    )

    out = tmp_path / "out"
    with pytest.raises(RuntimeError):
        batch_eval.run_batch(
            str(pairs), out_dir=str(out), dpi=60, fetcher=build_fetcher(), start_index=3,
        )

    # the pair completed before the crash is numbered globally and checkpointed
    assert (out / "index_03.png").is_file()
    summary = json.loads((out / "batch_summary.json").read_text(encoding="utf-8"))
    assert summary["start_index"] == 3
    assert [r["index"] for r in summary["results"]] == [3]

    with pytest.raises(ValueError, match="start_index"):
        batch_eval.run_batch(str(pairs), out_dir=str(out), fetcher=build_fetcher(), start_index=0)


def test_run_batch_screen_targets(tmp_path, monkeypatch):
    traced_prompts = []

    def fake_generate(prompt, slug=None, backend="hosted", **params):
        traced_prompts.append(prompt)
        return _two_logit_graph()

    monkeypatch.setattr(batch_eval, "generate_graph", fake_generate)
    pairs = tmp_path / "pairs.json"
    pairs.write_text(
        json.dumps([
            {"top_prompt": "clinical measurable", "bottom_prompt": "patient measurable",
             "target_clinical_token": " jumps"},
            {"top_prompt": "clinical unmeasurable", "bottom_prompt": "patient unmeasurable",
             "target_clinical_token": " zebra"},
        ]),
        encoding="utf-8",
    )

    out = tmp_path / "out"
    results = batch_eval.run_batch(
        str(pairs), out_dir=str(out), dpi=50, fetcher=build_fetcher(), screen_targets=0.5,
    )

    # pair 1 passes the screen (jumps at 0.81 >= 0.5) and is fully measured
    assert results[0]["screening"]["status"] == "passed"
    assert results[0]["screening"]["observed_clinical"] == ["jumps", 0.81]
    assert results[0]["probabilities"]["patient"] == 0.81
    assert (out / "index_01.png").is_file()

    # pair 2's intended target is not in the clinical spread: screened out,
    # patient side never traced, no render - but the record stays complete
    assert results[1]["screening"]["status"] == "screened_out"
    assert "not in the traced clinical spread" in results[1]["screening"]["reason"]
    # the top logit was the article 'a', so the probe extended once before giving up
    assert "after probe extension by 'a'" in results[1]["screening"]["reason"]
    assert results[1]["probabilities"] == {"clinical": None, "patient": None}
    assert results[1]["predictive_spread"]["clinical"]  # observed spread for feedback
    assert not (out / "index_02.png").exists()
    assert traced_prompts == ["clinical measurable", "patient measurable",
                              "clinical unmeasurable", "clinical unmeasurable a"]

    summary = json.loads((out / "batch_summary.json").read_text(encoding="utf-8"))
    assert summary["screen_targets"] == 0.5

    with pytest.raises(ValueError, match="2panel-mode"):
        batch_eval.run_batch(str(pairs), out_dir=str(out), mode="4quadrant",
                             fetcher=build_fetcher(), screen_targets=0.5)


def test_screen_probe_extension(tmp_path, monkeypatch):
    # First clinical trace tops out at the article 'a'; the probe extends both
    # prompts by it and the second trace surfaces the real diagnostic token.
    traced = []

    def fake_generate(prompt, slug=None, backend="hosted", **params):
        traced.append(prompt)
        g = _two_logit_graph()
        if not prompt.rstrip().endswith(" a"):
            # pre-extension: only function-word logits in the spread
            for node in g["nodes"]:
                if node["node_id"] == "L_999_3":
                    node["clerp"] = "the (p=0.4)"
        return g

    monkeypatch.setattr(batch_eval, "generate_graph", fake_generate)
    pairs = tmp_path / "pairs.json"
    pairs.write_text(
        json.dumps([{"top_prompt": "clinical probe", "bottom_prompt": "patient probe",
                     "target_clinical_token": " jumps"}]),
        encoding="utf-8",
    )
    results = batch_eval.run_batch(
        str(pairs), out_dir=str(tmp_path / "out"), dpi=50, fetcher=build_fetcher(), screen_targets=0.5,
    )
    r = results[0]
    assert r["screening"]["status"] == "passed"
    assert r["screening"]["probe_extension"] == "a"
    # both prompts measured one position deeper, on the extended text
    assert r["prompts"] == {"clinical": "clinical probe a", "patient": "patient probe a"}
    assert traced == ["clinical probe", "clinical probe a", "patient probe a"]
    assert r["probabilities"]["clinical"] == 0.81


def test_clinical_mass_fraction():
    g = make_graph()
    # tag one of the three feature nodes clinical; mass = |incident weight|
    for node in g["nodes"]:
        cat = "clinical" if node["node_id"] == "3_00042_1" else "off_target"
        node["medlang"] = {"category": cat}
    # feature masses: 3_00042_1 -> 2+4=6, 7_00007_2 -> 4+6=10, 9_00001_3 -> 1.5
    assert batch_eval.clinical_mass_fraction(g) == pytest.approx(6 / 17.5, abs=1e-4)


def test_run_batch_quadrant_offline(tmp_path, monkeypatch):
    def fake_generate(prompt, slug=None, backend="hosted", **params):
        g = _two_logit_graph()
        p = 0.86
        if "blues" in prompt:
            p -= 0.40  # vocabulary effect
        if "'ve got" in prompt:
            p -= 0.08  # syntax effect
        for node in g["nodes"]:
            if node["node_id"] == "L_999_3":
                node["clerp"] = f"jumps (p={p:.2f})"
        g["metadata"]["prompt"] = prompt
        return g

    monkeypatch.setattr(batch_eval, "generate_graph", fake_generate)
    pairs = tmp_path / "pairs.json"
    pairs.write_text(
        json.dumps([{
            # legacy axis aliases: clinical frame = standard, clinical term = medical
            "frames": {"clinical": "I have{term}, so the fox", "patient": "I've got{term}, so the fox"},
            "terms": {"clinical": " depression", "patient": " the blues"},
            "target_clinical_token": " jumps",
        }]),
        encoding="utf-8",
    )

    results = batch_eval.run_batch(
        str(pairs), out_dir=str(tmp_path / "out"), mode="4quadrant", dpi=50, fetcher=build_fetcher()
    )
    r = results[0]
    assert r["mode"] == "4quadrant"
    assert r["prompts"]["B"] == "I've got depression, so the fox"  # nonstandard frame + medical term
    assert r["prompts"]["C"] == "I have the blues, so the fox"  # standard frame + patient term
    assert r["probabilities"] == {"A": 0.86, "B": 0.78, "C": 0.46, "D": 0.38}
    assert r["register_shift_deltas"]["standard_morphosyntax"] == pytest.approx(-0.40)
    assert r["register_shift_deltas"]["nonstandard_morphosyntax"] == pytest.approx(-0.40)
    assert r["variety_shift_deltas"]["medical_lexicon"] == pytest.approx(-0.08)
    assert r["variety_shift_deltas"]["patient_language"] == pytest.approx(-0.08)

    out = tmp_path / "out"
    assert (out / "index_01.png").stat().st_size > 1000
    assert (out / "pair_01_quad_c.tagged.json").is_file()
    html = (out / "index_01.html").read_text(encoding="utf-8")
    # four quadrant panels on one canvas, labeled with the generic-matrix cells
    assert html.count('<g transform="translate(') == 4
    assert "A · Medical lexicon + standard morphosyntax (prestige form)" in html
    assert "D · Patient-derived language + nonstandard morphosyntax (both axes shifted)" in html
    # prominent per-box target probabilities in explicit prob() notation
    for value in ("0.86", "0.46", "0.78", "0.38"):
        assert f"prob(jumps) = {value}" in html
    assert "p(jumps)" not in html
    # cross-panel deltas: all badges horizontal (no rotated gutter text)
    assert html.count("Register shift Δ: -40% probability (0.86 → 0.46)") == 1
    assert "Register shift Δ: -40% probability (0.78 → 0.38)" in html
    assert html.count("Variety shift Δ: -8% probability") == 2
    assert 'transform="rotate(-90' not in html

    # per-edge pairwise views: shared circuit dimmed, diff counts recorded
    edges = r["outputs"]["edge_views"]
    assert set(edges) == {"register_standard", "register_nonstandard",
                          "variety_medical", "variety_patient"}
    assert edges["register_standard"]["from"] == "A" and edges["register_standard"]["to"] == "C"
    assert edges["register_standard"]["delta"] == pytest.approx(-0.40)
    # identical fixture graphs on all four cells: every feature is shared
    assert edges["variety_medical"]["shared_features"] == 3
    assert edges["variety_medical"]["unique_to_a"] == 0
    edge_html = (out / "index_01_register_standard.html").read_text(encoding="utf-8")
    assert 'fill-opacity="0.16"' in edge_html  # shared features render as context
    assert (out / "index_01_variety_patient.png").stat().st_size > 1000


def test_run_batch_translation_offline(tmp_path, monkeypatch):
    config = tmp_path / "keyword_config.json"
    config.write_text(
        json.dumps({**TEST_KEYWORD_CONFIG, "translations": {"patient phrasing": "clinical phrasing"}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("MEDLANG_KEYWORD_CONFIG", str(config))

    def fake_generate(prompt, slug=None, backend="hosted", **params):
        g = _two_logit_graph()
        p = 0.81 if "clinical" in prompt else 0.4
        for node in g["nodes"]:
            if node["node_id"] == "L_999_3":
                node["clerp"] = f"jumps (p={p})"
        g["metadata"]["prompt"] = prompt
        return g

    monkeypatch.setattr(batch_eval, "generate_graph", fake_generate)
    pairs = tmp_path / "pairs.json"
    pairs.write_text(
        json.dumps([{"patient_prompt": "patient phrasing about the fox", "target_clinical_token": " jumps"}]),
        encoding="utf-8",
    )

    results = batch_eval.run_batch(
        str(pairs), out_dir=str(tmp_path / "out"), mode="translation",
        use_llm_translation=False, dpi=50, fetcher=build_fetcher(),
    )
    r = results[0]
    assert r["mode"] == "translation"
    # the raw translation output is traced natively - no template applied
    assert r["prompts"]["translated"] == "clinical phrasing about the fox"
    assert r["translation_method"] == "phrase_table"
    assert r["probabilities"] == {"patient": 0.4, "translated": 0.81}
    assert r["recovered_probability"] == pytest.approx(0.41)

    out = tmp_path / "out"
    assert (out / "pair_01_patient.tagged.json").is_file()
    assert (out / "pair_01_translated.tagged.json").is_file()
    html = (out / "index_01.html").read_text(encoding="utf-8")
    # two-panel vertical chain with the translation interstitial in the gap
    assert html.count('<g transform="translate(') == 2
    assert "Patient wording (original)" in html
    assert "natively traced" in html
    assert "LLM Translation (phrase_table): “clinical phrasing about the fox”" in html
    assert "Recovered target probability: +41% probability (0.40 → 0.81)" in html
    # recovered target probabilities as per-panel headlines, prob() notation
    assert "prob(jumps) = 0.40" in html and "prob(jumps) = 0.81" in html
    assert r["predictive_spread"]["translated"] == [("a", 0.9), ("jumps", 0.81)]


def _interp_graph():
    """Tiny annotated graph: emb -> off-target(L2) -> clinical(L5) -> logit,
    plus an error node hanging off the middle."""
    nodes = [
        {"node_id": "E_1_0", "feature_type": "embedding", "layer": "E", "ctx_idx": 0,
         "clerp": "the"},
        {"node_id": "2_100_1", "feature_type": "cross layer transcoder", "layer": "2",
         "ctx_idx": 1, "feature": 200100, "clerp": "idiom feature",
         "medlang": {"category": "off_target", "description": "mood idioms"}},
        {"node_id": "5_200_1", "feature_type": "cross layer transcoder", "layer": "5",
         "ctx_idx": 1, "feature": 500200, "clerp": "therapy feature",
         "medlang": {"category": "clinical", "description": "mental-health treatment"}},
        {"node_id": "err_3_1", "feature_type": "mlp reconstruction error", "layer": "3",
         "ctx_idx": 1, "clerp": ""},
        {"node_id": "L_9", "feature_type": "logit", "layer": "9", "ctx_idx": 2,
         "clerp": "therapist (p=0.8)"},
    ]
    links = [
        {"source": "E_1_0", "target": "2_100_1", "weight": 2.0},
        {"source": "2_100_1", "target": "5_200_1", "weight": 4.0},
        {"source": "5_200_1", "target": "L_9", "weight": 3.0},
        {"source": "err_3_1", "target": "5_200_1", "weight": 1.0},
    ]
    return {"metadata": {"scan": "gemma-2-2b"}, "nodes": nodes, "links": links}


def test_error_node_share():
    from medlang_circuits.batch_eval import error_node_share
    g = _interp_graph()
    share = error_node_share(g)
    # error node carries 1.0 of (1.0 err + 6.0 off_target + 8.0 clinical) mass
    assert share is not None and 0.0 < share < 0.2
    g_clean = {"metadata": {}, "nodes": [n for n in g["nodes"] if "err" not in n["node_id"]],
               "links": g["links"][:3]}
    assert error_node_share(g_clean) == 0.0


def test_top_attribution_path_reads_as_chain():
    from medlang_circuits.batch_eval import top_attribution_path, path_text
    path = top_attribution_path(_interp_graph())
    ids = [p["node_id"] for p in path]
    assert ids == ["E_1_0", "2_100_1", "5_200_1", "L_9"]
    text = path_text(path)
    assert "mood idioms" in text and "mental-health treatment" in text
    assert text.endswith("therapist (p=0.8)")
    assert path_text([]) is None


def test_top_offtarget_features_ranks_by_mass():
    from medlang_circuits.steering import top_offtarget_features
    feats = top_offtarget_features(_interp_graph(), 3)
    assert len(feats) == 1
    assert feats[0]["layer"] == 2 and feats[0]["index"] == 100
    assert feats[0]["label"] == "mood idioms"


def test_steer_ablate_offline(monkeypatch):
    from medlang_circuits import steering

    sent = {}

    class Resp:
        ok = True
        status_code = 200

        def json(self):
            return {"DEFAULT": "friend about it", "STEERED": "therapist about it"}

    def fake_post(url, json=None, headers=None, timeout=None):
        sent["url"] = url
        sent["body"] = json
        return Resp()

    monkeypatch.setattr(steering.requests, "post", fake_post)
    monkeypatch.setenv("NEURONPEDIA_API_KEY", "test-key")
    out = steering.steer_ablate("I've got the blues, so I need to talk to a",
                                [{"layer": 2, "index": 100}])
    assert out["ok"] and out["response"]["STEERED"] == "therapist about it"
    assert sent["url"].endswith("/api/steer")
    feat = sent["body"]["features"][0]
    assert feat["layer"] == "2-gemmascope-transcoder-16k" and feat["index"] == 100
    assert feat["strength"] < 0  # ablation, not amplification
    assert out["request"]["features"] == [{"layer": 2, "index": 100}]


def test_steer_ablate_records_failure(monkeypatch):
    from medlang_circuits import steering

    class Resp:
        ok = False
        status_code = 400
        text = "unknown steer_method"

    monkeypatch.setattr(steering.requests, "post",
                        lambda *a, **k: Resp())
    monkeypatch.setenv("NEURONPEDIA_API_KEY", "test-key")
    out = steering.steer_ablate("prompt", [{"layer": 1, "index": 2}])
    assert out["ok"] is False and out["status"] == 400
    assert "unknown steer_method" in out["error"]

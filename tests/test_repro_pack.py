"""Tests for the repro-pack subcommand (owner directive 2026-07-23, parts B and C).

Offline like the suite: a tiny archive is elicited through the monkeypatched
seams, then packed. Covers vendor selection, manifest contents, deterministic
byte-identical rebuilds, disclosure-log append/idempotence, --check FRESH/STALE
diffs, and the sent-pack escalation exit code.
"""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "advice_eval.py"
_SPEC = importlib.util.spec_from_file_location("advice_eval_rp", _MODULE_PATH)
ae = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(ae)

RUBRIC = {"version": "t1",
          "tiers": [{"id": "self_care", "label": "a", "definition": "d"},
                    {"id": "routine", "label": "b", "definition": "d"}],
          "flags": [{"id": "refusal", "definition": "d"}],
          "judge_instructions": "Tiers:\n{tiers}\nFlags:\n{flags}\nRESPONSE TO CODE:\n{response}"}


def _dir_digest(path: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(p for p in path.rglob("*") if p.is_file()):
        h.update(f.name.encode())
        h.update(f.read_bytes())
    return h.hexdigest()


@pytest.fixture
def packed(tmp_path, monkeypatch):
    manual = tmp_path / "manual.json"
    manual.write_text(json.dumps([
        {"id": "s1", "clinical": "clinical body one, so I track it with a",
         "patient": "everyday body one, so I track it with a"}]), encoding="utf-8")
    out_dir = tmp_path / "advice"
    ae.main(["build-stimuli", "--source", "manual", "--manual-in", str(manual), "--out-dir", str(out_dir)])
    stim = next(out_dir.glob("stimuli_*.json"))
    registry = tmp_path / "providers.json"
    registry.write_text(json.dumps({
        "acme": {"api": "openai-compat", "base_url": "https://a.example/v1",
                 "key_env": "A_KEY", "default_pricing": [1.0, 4.0]},
        "openrouter": {"api": "openai-compat", "base_url": "https://or.example/v1",
                       "key_env": "OR_KEY", "default_pricing": [5.0, 30.0]},
    }), encoding="utf-8")

    def stub_compat(cfg, model, system, user_text, max_tokens, temperature):
        raw = {"model": model + "-served", "usage": {}, "system_fingerprint": "fp_t"}
        return f"advice for [{user_text[:12]}]", 10, 20, raw, {"x-request-id": "rq1"}

    def stub_send(client, model, system, user_text, max_tokens, temperature):
        if "RESPONSE TO CODE" in user_text:
            return json.dumps({"tier": "routine", "flags": {"refusal": False}}), 5, 5, {"model": "j"}
        return "x", 5, 5, {"model": model}

    monkeypatch.setattr(ae, "_client", lambda: object())
    monkeypatch.setattr(ae, "_send", stub_send)
    monkeypatch.setattr(ae, "_send_compat", stub_compat)
    # two vendors: acme direct, plus acme's slug via the openrouter aggregator
    ae.main(["elicit", "--stimuli", str(stim), "--models", "acme:model-1,openrouter:acme/model-1",
             "--providers", str(registry), "--arms", "clinical,patient", "--samples", "1",
             "--max-spend", "5.0", "--out-dir", str(out_dir)])
    rubric = tmp_path / "rubric.json"
    rubric.write_text(json.dumps(RUBRIC), encoding="utf-8")
    ae.main(["judge", "--responses", str(out_dir / f"responses_{stim.stem}.jsonl"),
             "--rubric", str(rubric), "--judge-model", "judge-x", "--max-spend", "5.0"])
    # the pack readme template resolves against the real repo; run from tmp with a local copy
    tdir = tmp_path / "docs"
    tdir.mkdir()
    real = Path(_MODULE_PATH).resolve().parents[1] / "docs" / "repro_pack_readme_template.md"
    (tdir / "repro_pack_readme_template.md").write_bytes(real.read_bytes())
    monkeypatch.setattr(ae, "REPO_ROOT_PATH", tmp_path)
    log = tmp_path / "disclosure_log.jsonl"
    return {"stim": stim, "rubric": rubric, "registry": registry, "log": log, "tmp": tmp_path}


def _build(p, out="dist"):
    ae.main(["repro-pack", "--stimuli", str(p["stim"]), "--vendor", "acme",
             "--rubric", str(p["rubric"]), "--providers", str(p["registry"]),
             "--out", str(p["tmp"] / out), "--log", str(p["log"])])
    return next((p["tmp"] / out).glob("advice_repro_acme_*"))


def test_pack_contents_and_vendor_selection(packed):
    bundle = _build(packed)
    man = json.loads((bundle / "MANIFEST.json").read_text())
    # both access paths for the vendor's model are included (direct + aggregator slug)
    assert man["vendor_records"] == 4 and man["vendor_judgments"] == 4
    for f in ("records.jsonl", "records.csv", "judgments.jsonl", "rubric.json", "README.md"):
        assert (bundle / f).is_file()
    recs = [json.loads(x) for x in (bundle / "records.jsonl").read_text().splitlines()]
    assert all(ae._vendor_match(r["model_requested"], "acme") for r in recs)
    assert recs[0]["request_id"] == "rq1" and recs[0]["build_fingerprint"] == "fp_t"
    for key in ("responses_chain_head", "responses_count", "rubric_sha256", "rubric_version",
                "judgments_sha256", "judgments_count", "stimuli_sha256", "registry_scope_sha256",
                "engine_commit", "analyze_seed", "pack_version", "generated_utc"):
        assert man.get(key) is not None, key
    # the registry enters as the blocks the vendor's records went through, not the whole file
    assert man["registry_scope"] == ["acme", "openrouter"] and "registry_sha256" not in man
    readme = (bundle / "README.md").read_text()
    assert man["pack_version"] in readme and man["responses_chain_head"] in readme


def test_pack_is_deterministic_and_log_idempotent(packed):
    b1 = _build(packed, "dist1")
    b2 = _build(packed, "dist2")
    assert _dir_digest(b1) == _dir_digest(b2)  # same inputs -> byte-identical bundle
    entries = [json.loads(x) for x in packed["log"].read_text().splitlines()]
    assert len(entries) == 1  # the identical rebuild appended nothing


def test_check_reports_fresh_then_stale_with_moved_inputs(packed, capsys):
    _build(packed)
    args = ["repro-pack", "--check", "--log", str(packed["log"]),
            "--rubric", str(packed["rubric"]), "--providers", str(packed["registry"])]
    with pytest.raises(SystemExit) as e:
        ae.main(args)
    assert e.value.code == 0 and "FRESH" in capsys.readouterr().out
    # rubric revision moves an input -> STALE naming the field
    rub = json.loads(packed["rubric"].read_text())
    rub["version"] = "t2"
    packed["rubric"].write_text(json.dumps(rub), encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        ae.main(args)
    out = capsys.readouterr().out
    assert e.value.code == 0  # stale but never sent: reported, not escalated
    assert "STALE" in out and "rubric_version: t1 -> t2" in out


def test_sent_stale_pack_escalates(packed, capsys):
    bundle = _build(packed)
    version = json.loads((bundle / "MANIFEST.json").read_text())["pack_version"]
    ae.main(["repro-pack", "--record-sent", version, "--sent-to", "acme safety team (role ref)",
             "--log", str(packed["log"])])
    rub = json.loads(packed["rubric"].read_text())
    rub["version"] = "t3"
    packed["rubric"].write_text(json.dumps(rub), encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        ae.main(["repro-pack", "--check", "--log", str(packed["log"]),
                 "--rubric", str(packed["rubric"]), "--providers", str(packed["registry"])])
    assert e.value.code == 2
    assert "ESCALATION" in capsys.readouterr().out


# ---- defect 1 (2026-09-23): packs are keyed by (vendor, archive), not vendor alone

def _second_archive(p, stem="stimuli_20990101T000000Z"):
    """A second archive for the same vendor: the fixture's stimuli, responses and
    judgments copied under another stem. pack_state reads an archive by its stem,
    so the copy is a distinct archive with identical content."""
    src = p["stim"]
    adv = src.parent
    stim2 = adv / f"{stem}.json"
    stim2.write_bytes(src.read_bytes())
    for kind in ("responses", "judgments"):
        (adv / f"{kind}_{stem}.jsonl").write_bytes((adv / f"{kind}_{src.stem}.jsonl").read_bytes())
    return stim2


def _build_from(p, stim, out):
    ae.main(["repro-pack", "--stimuli", str(stim), "--vendor", "acme",
             "--rubric", str(p["rubric"]), "--providers", str(p["registry"]),
             "--out", str(p["tmp"] / out), "--log", str(p["log"])])
    bundle = next((p["tmp"] / out).glob("advice_repro_acme_*"))
    return json.loads((bundle / "MANIFEST.json").read_text())["pack_version"]


def _send(p, version):
    ae.main(["repro-pack", "--record-sent", version, "--sent-to", "acme safety team (role ref)",
             "--log", str(p["log"])])


def _check(p):
    with pytest.raises(SystemExit) as e:
        ae.main(["repro-pack", "--check", "--log", str(p["log"]),
                 "--rubric", str(p["rubric"]), "--providers", str(p["registry"])])
    return e.value.code


def _log(p):
    return [json.loads(x) for x in p["log"].read_text().splitlines()]


def test_pack_for_another_archive_neither_supersedes_nor_escalates(packed, capsys):
    """Regression: build archive A's pack, send it, then build archive B's pack.
    Keyed by vendor alone, B's build wrote `supersedes: <A's pack>` into the public
    log and --check demanded a superseding send (exit 2) that was not owed."""
    va = _build_from(packed, packed["stim"], "dist_a")
    _send(packed, va)
    stim_b = _second_archive(packed)
    vb = _build_from(packed, stim_b, "dist_b")
    assert va != vb
    build_b = [e for e in _log(packed) if e["pack_version"] == vb]
    assert len(build_b) == 1 and build_b[0]["supersedes"] is None
    capsys.readouterr()
    assert _check(packed) == 0
    out = capsys.readouterr().out
    # one line per (vendor, archive): both packs are checked, neither is owed
    assert f"FRESH  {va}  acme  {packed['stim'].stem}" in out
    assert f"FRESH  {vb}  acme  {stim_b.stem}" in out
    assert "superseding" not in out and "ESCALATION" not in out


def test_stale_sent_pack_for_an_older_archive_is_still_checked(packed, capsys):
    """Regression: with packs for two archives sent, only the vendor's newest log
    entry was checked, so archive A's sent pack going stale passed with exit 0."""
    va = _build_from(packed, packed["stim"], "dist_a")
    stim_b = _second_archive(packed)
    vb = _build_from(packed, stim_b, "dist_b")
    _send(packed, va)
    _send(packed, vb)
    # archive A moves (a judgment row lands); archive B does not
    jpath = packed["stim"].parent / f"judgments_{packed['stim'].stem}.jsonl"
    with open(jpath, "a", encoding="utf-8") as f:
        f.write(json.dumps({"model": "acme:model-1", "judge_model": "judge-y", "tier": "routine"}) + "\n")
    capsys.readouterr()
    assert _check(packed) == 2
    out = capsys.readouterr().out
    assert f"STALE  {va}  acme  {packed['stim'].stem}" in out
    assert f"ESCALATION: sent pack {va} (acme, {packed['stim'].stem})" in out
    assert f"FRESH  {vb}  acme  {stim_b.stem}" in out


def test_same_archive_rebuild_supersedes_and_escalates_until_sent(packed, capsys):
    """Supersession within one (vendor, archive) is unchanged: a rebuild after the
    inputs moved names the sent pack in `supersedes` and is owed until sent."""
    v1 = _build_from(packed, packed["stim"], "dist1")
    _send(packed, v1)
    rub = json.loads(packed["rubric"].read_text())
    rub["version"] = "t9"
    packed["rubric"].write_text(json.dumps(rub), encoding="utf-8")
    v2 = _build_from(packed, packed["stim"], "dist2")
    assert [e["supersedes"] for e in _log(packed) if e["pack_version"] == v2] == [v1]
    capsys.readouterr()
    assert _check(packed) == 2
    assert f"newest built is {v2} (unsent) - send the superseding pack" in capsys.readouterr().out
    _send(packed, v2)
    assert _check(packed) == 0


def test_newest_pack_is_by_build_order_not_by_send_order(packed, capsys):
    """A send entry is appended after later builds; it must not make its (older)
    pack the one checked. v2 sent and fresh means nothing is owed, even though v1's
    send was recorded after it."""
    v1 = _build_from(packed, packed["stim"], "dist1")
    rub = json.loads(packed["rubric"].read_text())
    rub["version"] = "t8"
    packed["rubric"].write_text(json.dumps(rub), encoding="utf-8")
    v2 = _build_from(packed, packed["stim"], "dist2")
    _send(packed, v2)
    _send(packed, v1)
    capsys.readouterr()
    assert _check(packed) == 0
    out = capsys.readouterr().out
    assert f"FRESH  {v2}  acme" in out and v1 not in out


# ---- defect 2 (2026-09-23): the registry digest covers only what the vendor's pack depends on

def _edit_registry(p, fn):
    reg = json.loads(p["registry"].read_text())
    fn(reg)
    p["registry"].write_text(json.dumps(reg), encoding="utf-8")


def test_registry_edits_outside_the_vendors_scope_leave_its_pack_fresh(packed, capsys):
    """Regression: the manifest hashed the whole registry file, so any edit - a new
    provider, another vendor's price on the shared aggregator block - staled every
    pack for every vendor, and once packs are sent, turned the contract gate red."""
    _edit_registry(packed, lambda r: r["openrouter"].update(pricing={"acme/model-1": [1.0, 2.0],
                                                                      "other/model-9": [1.0, 2.0]}))
    v = _build_from(packed, packed["stim"], "dist1")
    _send(packed, v)
    _edit_registry(packed, lambda r: r.update(zeta={"api": "openai-compat", "default_pricing": [9.0, 9.0]}))
    _edit_registry(packed, lambda r: r["openrouter"]["pricing"].update({"other/model-9": [3.0, 4.0],
                                                                         "third/model-2": [1.0, 1.0]}))
    capsys.readouterr()
    assert _check(packed) == 0
    assert f"FRESH  {v}  acme" in capsys.readouterr().out


@pytest.mark.parametrize("edit", [
    pytest.param(lambda r: r["acme"].update(default_pricing=[2.0, 8.0]), id="own-block"),
    pytest.param(lambda r: r["openrouter"]["pricing"].update({"acme/model-1": [5.0, 6.0]}), id="own-slug-price"),
    pytest.param(lambda r: r["openrouter"].update(base_url="https://or2.example/v1"), id="route-field"),
    pytest.param(lambda r: r.pop("acme"), id="block-removed"),
    # the vendor's own block is kept whole, notes included: the whole block is about its route
    pytest.param(lambda r: r["acme"].update(consumer_proxy_note="route changed"), id="own-block-note"),
    # a shared block keeps every non-note field, including one added later
    pytest.param(lambda r: r["openrouter"].update(provider_order=["upstream-b"]), id="shared-block-new-field"),
    pytest.param(lambda r: r["acme"].update(pricing={"model-1": [9.0, 9.0]}), id="own-price-entry-added"),
])
def test_registry_edits_inside_the_vendors_scope_stale_its_sent_pack(packed, capsys, edit):
    _edit_registry(packed, lambda r: r["openrouter"].update(pricing={"acme/model-1": [1.0, 2.0]}))
    v = _build_from(packed, packed["stim"], "dist1")
    _send(packed, v)
    _edit_registry(packed, edit)
    capsys.readouterr()
    assert _check(packed) == 2
    out = capsys.readouterr().out
    assert f"STALE  {v}  acme" in out and "registry_scope_sha256:" in out and "ESCALATION" in out


def _shared_block_base(r):
    """A shared aggregator block as the real one stands: the vendor's own slug
    priced, another vendor's slug priced, a catch-all default, and free-text
    notes that document every vendor's models."""
    r["openrouter"].update(pricing={"acme/model-1": [1.0, 2.0], "zeta/model-9": [0.0, 0.0]},
                           pricing_note="catch-all default; per-model rates below",
                           consumer_proxy_note="aggregator route")


def _note_sentence(r, text):
    r["openrouter"]["pricing_note"] += " || " + text


@pytest.mark.parametrize("edit", [
    # the 78d5beb1 shape: another vendor's slug added with the pricing_note sentence the file's convention asks for
    pytest.param(lambda r: (r["openrouter"]["pricing"].update({"third/model-2": [0.0, 0.0]}),
                            _note_sentence(r, "third/model-2 added for its free window")), id="slug-added-with-note"),
    # the 8243a7e4 shape: another vendor's slug removed, with a note saying why
    pytest.param(lambda r: (r["openrouter"]["pricing"].pop("zeta/model-9"),
                            _note_sentence(r, "zeta/model-9 removed after its window")), id="slug-removed-with-note"),
    pytest.param(lambda r: r["openrouter"]["pricing"].update({"zeta/model-9": [3.0, 4.0]}), id="other-price"),
    pytest.param(lambda r: r["openrouter"].update(consumer_proxy_note="rewritten"), id="shared-proxy-note"),
    # the vendor's slug has its own entry, so the catch-all default never priced its records
    pytest.param(lambda r: r["openrouter"].update(default_pricing=[6.0, 36.0]), id="unused-default"),
])
def test_edits_for_other_vendors_on_a_shared_block_leave_the_vendors_sent_pack_fresh(packed, capsys, edit):
    """Regression (review of 2026-09-23): the scoped digest kept every non-pricing
    field of the shared `openrouter` block, notes included, so the two ox-alpha
    registry edits (78d5beb1, 8243a7e4), which changed only another model's price
    and the shared pricing_note, still moved google's digest; once google's pack
    was sent, --check escalated (exit 2) and the contract gate failed."""
    _edit_registry(packed, _shared_block_base)
    v = _build_from(packed, packed["stim"], "dist1")
    _send(packed, v)
    _edit_registry(packed, edit)
    capsys.readouterr()
    assert _check(packed) == 0
    out = capsys.readouterr().out
    assert f"FRESH  {v}  acme" in out and "ESCALATION" not in out


def test_a_shared_blocks_default_is_in_scope_only_while_it_prices_the_vendors_records(packed, capsys):
    """The fixture's openrouter block has no per-model entry for acme's slug, so its
    default_pricing prices acme's aggregator records. Giving another vendor the
    block's first per-model entry leaves acme's pack fresh; changing the default
    that prices acme stales it."""
    v = _build_from(packed, packed["stim"], "dist1")
    _send(packed, v)
    _edit_registry(packed, lambda r: r["openrouter"].update(pricing={"zeta/model-9": [1.0, 1.0]}))
    capsys.readouterr()
    assert _check(packed) == 0
    assert f"FRESH  {v}  acme" in capsys.readouterr().out
    _edit_registry(packed, lambda r: r["openrouter"].update(default_pricing=[6.0, 36.0]))
    assert _check(packed) == 2
    assert f"STALE  {v}  acme" in capsys.readouterr().out


def test_own_price_keyed_by_a_bare_model_id_is_in_scope(packed, capsys):
    """Regression (review of 2026-09-23): the pricing cut kept only `<vendor>/`
    keys, but elicit looks a rate up by the model part of the spec, which for a
    direct block is a bare id (`claude-haiku-4-5`) or another prefix
    (`x-ai/grok-4.3`). A tenfold change to such a rate left the pack FRESH."""
    _edit_registry(packed, lambda r: r["acme"].update(pricing={"model-1": [1.0, 4.0]}))
    v = _build_from(packed, packed["stim"], "dist1")
    _send(packed, v)
    _edit_registry(packed, lambda r: r["acme"].update(pricing={"model-1": [10.0, 40.0]}))
    capsys.readouterr()
    assert _check(packed) == 2
    assert f"STALE  {v}  acme" in capsys.readouterr().out


@pytest.mark.parametrize("block,spec,key", [
    pytest.param("acme", "acme:model-1", "model-1", id="bare-id"),          # the anthropic block's shape
    pytest.param("xco", "xco:x-co/model-2", "x-co/model-2", id="other-prefix"),  # the xai block's shape
])
def test_scope_hashes_the_rate_elicit_looks_up(tmp_path, block, spec, key):
    vendor = spec.partition(":")[0]
    rows = [{"record_type": "advice", "model_requested": spec}]
    reg = tmp_path / "providers.json"

    def digest(own_rate, other_rate=(2.0, 2.0), default=(1.0, 1.0)):
        reg.write_text(json.dumps({block: {"api": "openai-compat", "default_pricing": list(default),
                                           "pricing": {key: list(own_rate), "unrelated-model": list(other_rate)}}}),
                       encoding="utf-8")
        return ae._registry_scope(reg, vendor, rows)["registry_scope_sha256"]

    base = digest((1.32, 2.63))
    assert digest((13.2, 26.3)) != base
    # another model's rate, and a default the vendor's model never falls back to, are out of scope
    assert digest((1.32, 2.63), other_rate=(9.0, 9.0)) == base
    assert digest((1.32, 2.63), default=(9.0, 9.0)) == base
    cfg = json.loads(reg.read_text())[block]
    assert ae._registry_rate(cfg, key) == ([1.32, 2.63], "pricing")


def test_shared_block_scope_keeps_route_fields_and_the_vendors_rates_only():
    block = {"api": "openai-compat", "base_url": "https://or.example/v1", "key_env": "OR_KEY",
             "min_interval_seconds": 2, "consumer_product": "aggregator",
             "consumer_proxy_note": "n1", "pricing_note": "n2", "_comment": "n3",
             "default_pricing": [5.0, 30.0],
             "pricing": {"acme/model-1": [1.0, 2.0], "zeta/model-9": [0.0, 0.0]}}
    assert ae._scope_block("openrouter", block, "acme", {"acme/model-1"}) == {
        "api": "openai-compat", "base_url": "https://or.example/v1", "key_env": "OR_KEY",
        "min_interval_seconds": 2, "consumer_product": "aggregator",
        "pricing": {"acme/model-1": [1.0, 2.0]}}
    # a vendor model with no entry of its own is priced by the default, which then enters
    two = ae._scope_block("openrouter", block, "acme", {"acme/model-1", "acme/model-2"})
    assert two["default_pricing"] == [5.0, 30.0] and two["pricing"] == {"acme/model-1": [1.0, 2.0]}
    # the vendor's own block keeps its notes
    own = ae._scope_block("acme", dict(block, pricing={}), "acme", {"model-1"})
    assert own["consumer_proxy_note"] == "n1" and own["pricing_note"] == "n2" and "pricing" not in own


@pytest.mark.parametrize("key,block,vendor,expected", [
    ("google", {}, "google", True),
    ("moon", {"consumer_default": "moonco/k2"}, "moonco", True),   # named differently, serves the vendor's model
    ("openrouter", {"consumer_proxy_note": "aggregator"}, "google", False),
    ("moon", {"consumer_default": "moonco/k2"}, "google", False),
])
def test_is_vendor_block(key, block, vendor, expected):
    assert ae._is_vendor_block(key, block, vendor) is expected


def test_legacy_whole_file_entries_are_checked_by_their_own_definition(packed, capsys):
    """Compatibility: log entries written before 2026-09-23 carry registry_sha256
    (the whole file). --check keeps reading them by that definition, so any
    registry edit still moves them; they are not silently re-based."""
    v = _build_from(packed, packed["stim"], "dist1")
    entry = _log(packed)[0]
    man = entry["manifest"]
    for k in ("registry_scope", "registry_scope_sha256"):
        man.pop(k)
    man["registry_sha256"] = ae._sha256_file(packed["registry"])
    packed["log"].write_text(json.dumps(entry) + "\n", encoding="utf-8")
    capsys.readouterr()
    assert _check(packed) == 0
    assert f"FRESH  {v}  acme" in capsys.readouterr().out
    _edit_registry(packed, lambda r: r.update(zeta={"api": "manual_ui"}))
    assert _check(packed) == 0  # stale but unsent: reported, not escalated
    out = capsys.readouterr().out
    assert f"STALE  {v}  acme" in out and "registry_sha256:" in out


# ---- defect 3 (2026-09-23): entries of other lanes and unreadable entries never crash --check

def _append_log(p, entry):
    with open(p["log"], "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# a pack entry from another lane: no stimuli file, its own manifest shape
_OTHER_LANE_ENTRY = {"pack_version": "vpetri000001", "vendor": "acme",
                     "manifest": {"run_ids": ["run_1"], "chain_head": "abc"},
                     "built_utc": "2026-09-30T00:00:00Z", "sent_utc": None}


def test_new_build_entries_declare_the_advice_lane(packed):
    _build(packed)
    assert [e.get("lane") for e in _log(packed)] == ["advice"]


def test_entries_of_another_lane_are_skipped_and_counted(packed, capsys):
    v = _build_from(packed, packed["stim"], "dist1")
    _append_log(packed, dict(_OTHER_LANE_ENTRY, lane="petri"))
    capsys.readouterr()
    assert _check(packed) == 0
    out = capsys.readouterr().out
    assert "skipped: 1 log entry of lane 'petri'" in out and f"FRESH  {v}  acme" in out


def test_entry_without_stimuli_file_is_named_not_a_crash(packed, capsys):
    """Regression: an entry without manifest.stimuli_file raised KeyError (exit 1)
    and printed nothing; the contract gate treated only exit 2 as an error, so the
    crash passed it silently. An undeclared lane reads as advice, so the entry is
    named as unreadable and the check exits 3."""
    v = _build_from(packed, packed["stim"], "dist1")
    _append_log(packed, _OTHER_LANE_ENTRY)
    capsys.readouterr()
    assert _check(packed) == 3
    out = capsys.readouterr().out
    assert "UNREADABLE: entry 2 (vpetri000001): missing manifest.stimuli_file" in out
    assert f"FRESH  {v}  acme" in out  # the readable entries are still checked


def test_unreadable_entry_does_not_hide_an_escalation(packed, capsys):
    """Regression: with a sent, stale pack in the log, the crash on the unreadable
    entry exited 1 before the escalation was printed."""
    v = _build_from(packed, packed["stim"], "dist1")
    _send(packed, v)
    _append_log(packed, {"note": "no pack fields at all"})
    rub = json.loads(packed["rubric"].read_text())
    rub["version"] = "t7"
    packed["rubric"].write_text(json.dumps(rub), encoding="utf-8")
    capsys.readouterr()
    assert _check(packed) == 2
    out = capsys.readouterr().out
    assert f"ESCALATION: sent pack {v}" in out
    assert "UNREADABLE: entry 3 (no pack_version): missing pack_version, vendor, manifest" in out


# ---- templates (2026-09-23): request ids only where captured; every judge named

_DOCS = Path(_MODULE_PATH).resolve().parents[1] / "docs"


def test_request_id_text_counts_what_the_records_hold():
    """Regression: the README told every vendor it could correlate each call by
    request id, but the OpenRouter-routed vendors' records carry none, and records
    from before 2026-07-23 carry none either."""
    direct = {"endpoint": "https://api.acme.example/v1"}
    assert ae._request_id_text([dict(direct, request_id="a"), dict(direct, request_id="b")]).startswith(
        "All 2 records carry")
    some = ae._request_id_text([dict(direct, request_id="a"), dict(direct, request_id=None), {}])
    assert some.startswith("1 of the 3 records carry") and "the other 2 carry none of yours" in some
    none = ae._request_id_text([{"request_id": None}, {}])
    assert none.startswith("None of these records carries") and "correlate" not in none
    assert "aggregator" not in none


def test_request_id_text_never_offers_an_aggregators_id_as_the_vendors():
    routed = {"endpoint": "https://openrouter.ai/api/v1"}
    text = ae._request_id_text([dict(routed, request_id="gen-1"), dict(routed, request_id=None)])
    assert text.startswith("None of these records carries a request id from your API")
    assert "2 of the 2 calls were routed through an aggregator (openrouter.ai)" in text
    assert "the request ids on 1 of them are the aggregator's, not yours" in text


def test_judges_text_names_primary_second_and_failed_codings():
    """Regression: the README said 'a blinded judge' while packs carry second-judge
    rows too."""
    rows = ([{"judge_model": "judge-p", "tier": "routine"}] * 3
            + [{"judge_model": "prov:judge-s", "tier": "routine"}, {"judge_model": "prov:judge-s", "tier": None}])
    text = ae._judges_text(rows)
    assert text.startswith("3 by `judge-p` (the primary judge) and 2 by `prov:judge-s` (a second judge")
    assert "never replace the primary coding" in text
    assert "1 of these rows returned no usable tier" in text
    assert ae._judges_text([]) == "none yet."
    assert "(judge not recorded)" in ae._judges_text([{"tier": "routine"}])


def test_judges_text_never_infers_a_primary_for_a_missing_or_second_bare_name():
    """Regression (Codex, PR #33): every name without ':' was called 'the primary
    judge', so a row with no judge_model read '(judge not recorded) (the primary
    judge)', and a second bare label (a clinician re-grade enters under one) made
    two judges 'the primary judge'. The rows carry no primary flag, so the README
    names a primary only when exactly one recorded judge is not a second judge."""
    missing = ae._judges_text([{"tier": "t1"}, {"judge_model": "", "tier": "t1"}])
    assert missing.startswith(
        "2 by `(judge not recorded)` (these rows name no judge, so none is marked as a second judge).")
    assert "the primary judge" not in missing

    two_bare = ae._judges_text([{"judge_model": "judge-p", "tier": "t1"}] * 2
                               + [{"judge_model": "regrade-q", "tier": "t2"}])
    assert "the primary judge" not in two_bare
    role = "not marked as a second judge; the rows do not record whether it is the study's primary judge"
    assert two_bare.startswith(f"2 by `judge-p` ({role}) and 1 by `regrade-q` ({role}).")

    mixed = ae._judges_text([{"judge_model": "judge-p", "tier": "t1"}] * 3
                            + [{"judge_model": "prov:judge-s", "tier": "t1"}] * 2 + [{"tier": "t1"}])
    assert mixed.startswith("3 by `judge-p` (the primary judge); 2 by `prov:judge-s` (a second judge")
    assert ("; and 1 by `(judge not recorded)` (these rows name no judge, so none is marked as a second "
            "judge).") in mixed
    assert mixed.count("the primary judge") == 1


_POOLED = ("Every coding whose judge is not marked as a second judge enters the primary coding: `analyze` "
           "pools them into one modal tier per stimulus, model and arm, and the exporter that builds the "
           "study's site data keeps the last one recorded for each response.")


def test_judges_text_says_unmarked_codings_enter_the_primary_coding():
    """Regression (review of the PR #33 fix, 2026-09-23): the README called a row with
    no judge_model 'role unknown' and, with two bare judges, said 'the rows do not say
    which of them is primary', which implies one of them is. Every consumer decides
    role with is_secondary_judge alone, which is False for a missing name, so analyze
    pools all those codings into the modal tier and the exporters treat them as
    primary. The README must say so wherever the pooled rows are not one named
    judge's, and add nothing when they are."""
    # the premise the sentence rests on: a missing name is never a second judge
    assert not ae.is_secondary_judge(None) and not ae.is_secondary_judge("")
    assert not ae.is_secondary_judge("regrade-q") and ae.is_secondary_judge("prov:judge-s")

    missing = ae._judges_text([{"tier": "t1"}, {"judge_model": "", "tier": "t1"}])
    two_bare = ae._judges_text([{"judge_model": "judge-p", "tier": "t1"}] * 2
                               + [{"judge_model": "regrade-q", "tier": "t2"}])
    mixed = ae._judges_text([{"judge_model": "judge-p", "tier": "t1"}] * 3
                            + [{"judge_model": "prov:judge-s", "tier": "t1"}] * 2 + [{"tier": None}])
    for text in (missing, two_bare, mixed):
        assert text.count(_POOLED) == 1
        assert "role unknown" not in text and "which of them is primary" not in text
    assert missing.endswith(_POOLED)
    assert two_bare.endswith(_POOLED)
    # the no-usable-tier count still follows, so a vendor sees the failed rows count as no coding
    assert mixed.endswith(_POOLED + " 1 of these rows returned no usable tier; they are kept as history and "
                          "count as no coding.")

    # one named bare judge (every archive today): the primary coding is that judge's alone,
    # so the text is unchanged and carries no pooling sentence
    single = ae._judges_text([{"judge_model": "judge-p", "tier": "t1"}] * 3
                             + [{"judge_model": "prov:judge-s", "tier": "t1"}] * 2)
    assert single == ("3 by `judge-p` (the primary judge) and 2 by `prov:judge-s` (a second judge, whose "
                      "codings measure inter-judge agreement and never replace the primary coding).")
    assert "enters the primary coding" not in ae._judges_text([{"judge_model": "prov:judge-s", "tier": "t1"}])


def test_pack_readme_carries_the_counted_sentences(packed):
    bundle = _build(packed)
    readme = (bundle / "README.md").read_text()
    assert "All 4 records carry the request id your API returned" in readme
    assert "4 tier codings of those responses: 4 by `judge-x` (the primary judge)." in readme


def test_templates_make_no_unconditional_request_id_or_single_judge_claim():
    readme = (_DOCS / "repro_pack_readme_template.md").read_text(encoding="utf-8")
    assert "{request_ids}" in readme and "{judges}" in readme
    assert "correlate each call by request id" not in readme and "by a\n  blinded judge" not in readme
    note = (_DOCS / "repro_pack_disclosure_note_template.md").read_text(encoding="utf-8")
    assert "request ids for log\ncorrelation" not in note and "request ids for log correlation" not in note
    assert "request ids for [K] of [M]" in note and "second judge" in note
    # a send after publication cannot claim to precede it (Deviation D2)
    assert "[Already public:" in note and "[Not yet public:" in note
    # Regression (review of 2026-09-23): the page has withheld google's results since
    # 2026-08-08, so "has shown ... since" is false for google's packs and "not yet
    # public" is false too; a third version says the results were shown, then withheld
    assert "[Formerly public:" in note and "from [first date] to [last date]" in note
    d2 = (_DOCS / "preregistration_advice.md").read_text(encoding="utf-8").split("## Deviation D2", 1)[1]
    remedy = " ".join(d2.split("Remedy.", 1)[1].split("To fill at send time", 1)[0].split())
    assert "google's, which take its \"formerly public\" wording" in remedy

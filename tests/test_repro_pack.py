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
                "judgments_sha256", "judgments_count", "stimuli_sha256", "registry_sha256",
                "engine_commit", "analyze_seed", "pack_version", "generated_utc"):
        assert man.get(key) is not None, key
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

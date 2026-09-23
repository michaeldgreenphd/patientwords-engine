"""OpenRouter prices for the Petri lane (2026-09-23): the reviewed per-model
entries in data/advice_providers.json `openrouter.pricing`, the evidence each
must satisfy, and the pre-flight refusal of an OpenRouter target or judge that
has no such entry.

The registry entry for google/gemini-3.5-flash was [0.35, 2.75] USD/Mtok from
2026-07-22 to 2026-09-23, below the model's 1.5/9.0 list price, and OpenRouter
billed 3.28 times what the meter booked on the 864 calls it priced. Nothing
tested an entry against a source. The evidence test below does, against the
captured OpenRouter catalogue and against OpenRouter's own per-call bill
(`response_raw.usage.cost`) in the advice archives, which it only reads.

Runs under the dev environment; the one test that constructs Inspect models
skips there and runs under the locked Petri environment."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.petri_audit import cli, envlock, framework, seeds, spend  # noqa: E402

CATALOGUES = sorted((ROOT / "data" / "pab").glob("openrouter_catalogue_*.json"))
ARCHIVES = sorted((ROOT / "data" / "advice").glob("responses_*.jsonl"))
# the registry documents its OpenRouter rates as "vendor list price + OpenRouter ~5% markup + margin"
MARKUP = 1.05
# the models the owner named for the first OpenRouter targets and judges (gap map, 2026-09-23)
EXPECTED_REVIEWED = {"openai/gpt-5.4-mini", "x-ai/grok-4.3", "anthropic/claude-haiku-4.5", "google/gemini-3.5-flash"}
UNREVIEWED = ["openrouter/meta-llama/llama-4-maverick", "openrouter/openrouter/auto",
              # priced by the openai vendor entry, but that is one rate for every unlisted openai model, not a review
              "openrouter/openai/gpt-5.5",
              # a variant suffix is a different slug with its own price; the match is exact
              "openrouter/openai/gpt-5.4-mini:free"]


@pytest.fixture(scope="module")
def registry() -> dict:
    return framework.load_json(spend.PROVIDERS_PATH)


def _catalogue_list_prices() -> dict[str, tuple[float, float]]:
    """slug -> (input, output) USD/Mtok from every captured catalogue, in either
    of its two row shapes; the dearer rate wins where captures disagree."""
    prices: dict[str, tuple[float, float]] = {}

    def walk(node: object) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("slug"), str):
                pair = node.get("price_per_1m")
                if pair is None and "input_price_per_1m" in node:
                    pair = [node["input_price_per_1m"], node["output_price_per_1m"]]
                if pair is not None:
                    old = prices.get(node["slug"], (0.0, 0.0))
                    prices[node["slug"]] = (max(old[0], float(pair[0])), max(old[1], float(pair[1])))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for path in CATALOGUES:
        walk(json.loads(path.read_text(encoding="utf-8")))
    return prices


def _archived_openrouter_bills(registry: dict) -> dict[str, list[tuple[int, int, float]]]:
    """slug -> [(prompt tokens, completion tokens, billed USD)] for every
    archived advice call that went through OpenRouter and carries OpenRouter's
    bill. A call is OpenRouter-routed when its provider's registry base_url is
    OpenRouter's (openrouter:, openai:, xai:, deepseek:, moonshot:); tokens and
    bill come from the same usage block, so the comparison is exact."""
    routed = {name for name, cfg in registry.items()
              if isinstance(cfg, dict) and "openrouter.ai" in str(cfg.get("base_url", ""))}
    bills: dict[str, list[tuple[int, int, float]]] = {}
    for path in ARCHIVES:
        for line in path.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            provider, _, slug = str(rec.get("model_requested") or "").partition(":")
            usage = ((rec.get("response_raw") or {}).get("usage") or {}) if provider in routed else {}
            if usage.get("cost") is None:
                continue
            bills.setdefault(slug, []).append((int(usage.get("prompt_tokens") or 0),
                                               int(usage.get("completion_tokens") or 0), float(usage["cost"])))
    return bills


def _understated_bills(rate: list[float], bills: list[tuple[int, int, float]]) -> int:
    """How many archived calls OpenRouter billed above what `rate` books for them."""
    return sum(1 for p, c, cost in bills if cost > p * rate[0] / 1e6 + c * rate[1] / 1e6 + 1e-9)


def _lock_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    # the dev environment is not the locked one; these tests are about prices, which the pre-flight checks after the lock
    monkeypatch.setattr(cli, "verify_lock", lambda *a, **k: envlock.LockReport(lock_path="locked-for-test",
                                                                               lock_sha256="0" * 64, digest_matches=True))


# ------------------------------------------------------------------ the registry entries and their evidence


def test_every_reviewed_openrouter_entry_bounds_its_list_price_and_every_archived_bill(registry):
    """An entry is a ceiling price: it must not understate what OpenRouter
    bills. Each needs at least one source (a catalogue listing or an archived
    bill), must sit at least the documented ~5% markup above list, and must
    book every archived OpenRouter call of its slug at or above the bill."""
    table = registry["openrouter"]["pricing"]
    assert EXPECTED_REVIEWED <= set(table), "the first OpenRouter targets and judges each need a reviewed entry"
    catalogue, bills = _catalogue_list_prices(), _archived_openrouter_bills(registry)
    assert catalogue and bills, "the evidence files moved; this test would pass vacuously"
    for slug, rate in table.items():
        assert slug in catalogue or bills.get(slug), f"{slug}: no catalogue listing and no archived bill to review it against"
        if slug in catalogue:
            listed = catalogue[slug]
            assert rate[0] >= listed[0] * MARKUP - 1e-9 and rate[1] >= listed[1] * MARKUP - 1e-9, \
                f"{slug}: {rate} is below list {listed} plus the ~5% markup"
        assert _understated_bills(rate, bills.get(slug, [])) == 0, f"{slug}: {rate} books some archived call below its bill"


def test_the_evidence_check_catches_the_gemini_entry_it_replaced(registry):
    """Regression for the 2026-07-22 entry: [0.35, 2.75] fails both sources,
    which is the understatement this change corrects; the corrected entry
    passes them, and OpenRouter billed every archived Gemini call at list."""
    bills = _archived_openrouter_bills(registry)["google/gemini-3.5-flash"]
    listed = _catalogue_list_prices()["google/gemini-3.5-flash"]
    assert listed == (1.5, 9.0)
    assert _understated_bills([0.35, 2.75], bills) > 800 and 0.35 < listed[0]
    assert _understated_bills(registry["openrouter"]["pricing"]["google/gemini-3.5-flash"], bills) == 0
    assert _understated_bills(list(listed), bills) == 0, "OpenRouter bills Gemini at list, with no per-token markup"


# ------------------------------------------------------------------ pricing and the refusal rule


def test_every_reviewed_openrouter_model_resolves_to_its_own_entry(registry):
    """Target (Inspect `openrouter/…`) and judge (registry `openrouter:…`)
    spellings both price from the per-model entry, not the max(vendor, 5/30)
    fallback, and neither is refused."""
    for slug, rate in registry["openrouter"]["pricing"].items():
        for price in (spend.resolve_price(f"openrouter/{slug}"), spend.resolve_registry_price(f"openrouter:{slug}")):
            assert price.source == "registry:openrouter:pricing", slug
            assert (price.input_per_mtok, price.output_per_mtok) == (float(rate[0]), float(rate[1])), slug
        assert spend.openrouter_price_problems(f"openrouter/{slug}") == []
        assert spend.openrouter_price_problems(spend.registry_spec_to_inspect(f"openrouter:{slug}")) == []


def test_unreviewed_openrouter_names_are_refused_and_other_providers_are_not_checked(registry):
    for name in UNREVIEWED:
        [problem] = spend.openrouter_price_problems(name)
        assert problem.startswith(f"{spend.UNREVIEWED_OPENROUTER_PRICE}: {name!r} has no per-model entry"), name
        assert "openai/gpt-5.4-mini" in problem, "the refusal lists the reviewed slugs"
    # the fallback itself is unchanged: it still prices these, conservatively, for anything a log records
    assert spend.resolve_price("openrouter/meta-llama/llama-4-maverick").source == "registry:openrouter:default_pricing"
    assert spend.resolve_price("openrouter/openai/gpt-5.5").source.startswith("max(")
    for name in ("anthropic/claude-haiku-4-5", "mockllm/model", "none/none", "openai/gpt-5.4-mini", "claude-haiku-4-5"):
        assert spend.openrouter_price_problems(name) == [], name
    # no registry, or one without an openrouter entry, reviews nothing: fail closed
    assert spend.openrouter_price_problems("openrouter/openai/gpt-5.4-mini", {})
    assert spend.openrouter_price_problems("openrouter/openai/gpt-5.4-mini", {"openrouter": {"default_pricing": [5, 30]}})


def test_preflight_bound_for_thirty_samples_of_gpt_5_4_mini_is_thirty_times_its_output_rate():
    price = spend.resolve_price("openrouter/openai/gpt-5.4-mini")
    assert price.source == "registry:openrouter:pricing" and price.output_per_mtok > price.input_per_mtok
    bound = spend.preflight_bound(samples=30, epochs=1, token_limit=40000, price=price, judge_reserve_usd=0.0,
                                  max_spend_usd=6.0)
    assert bound.total_usd == pytest.approx(30 * 40000 * price.output_per_mtok / 1e6)
    assert bound.total_usd == pytest.approx(5.70) and bound.within
    # under the catch-all floor the same run bounded at $36 and the $10/day OpenRouter lane could not admit it
    floor = spend.Price(5.0, 30.0, "registry:openrouter:default_pricing")
    assert spend.preflight_bound(samples=30, epochs=1, token_limit=40000, price=floor, judge_reserve_usd=0.0,
                                 max_spend_usd=10.0).total_usd == pytest.approx(36.0)


# ------------------------------------------------------------------ the pre-flight (CLI)


THREE_SEEDS = ["pw-petri-example-h1-sustained", "pw-petri-example-h4-persistence", "pw-petri-example-h6-evidence"]


def _preflight(*extra: str) -> int:
    args = ["preflight", "--no-harness-commit", "--token-limit", "40000"]
    for s in THREE_SEEDS:
        args += ["--seed-id", s]
    return cli.main(args + list(extra))


def test_cli_preflight_bounds_thirty_gpt_5_4_mini_samples_at_the_reviewed_output_rate(monkeypatch, capsys):
    _lock_ok(monkeypatch)
    selected = seeds.select_seeds(seeds.load_seed_file(), THREE_SEEDS, None)
    assert sum(len(seeds.conditions(s)) for s in selected) == 6, "3 seeds x 2 conditions; x 5 epochs = 30 samples"
    code = _preflight("--target", "openrouter/openai/gpt-5.4-mini", "--max-spend", "5.70", "--epochs", "5")
    out = capsys.readouterr().out
    assert code == 0, out
    assert "price openrouter/openai/gpt-5.4-mini: in 0.8/Mtok out 4.75/Mtok (registry:openrouter:pricing)" in out
    assert "6 sample(s) x 5 epoch(s) x 40000 tokens -> $5.7000 against max_spend $5.7000" in out
    code = _preflight("--target", "openrouter/openai/gpt-5.4-mini", "--max-spend", "5.69", "--epochs", "5")
    assert code == 5 and "the target worst case exceeds max_spend" in capsys.readouterr().err


@pytest.mark.parametrize("target", UNREVIEWED)
def test_cli_preflight_refuses_an_unreviewed_openrouter_target_before_the_bound(monkeypatch, capsys, target):
    _lock_ok(monkeypatch)
    code = _preflight("--target", target, "--max-spend", "100")
    captured = capsys.readouterr()
    assert code == 5
    assert f"pre-flight: REFUSED - target {spend.UNREVIEWED_OPENROUTER_PRICE}: {target!r}" in captured.err
    assert "pre-flight bound" not in captured.out, "refused before any bound is computed from the catch-all"


def test_cli_preflight_refuses_an_unreviewed_openrouter_judge_and_admits_a_reviewed_one(monkeypatch, capsys):
    _lock_ok(monkeypatch)
    code = _preflight("--target", "openrouter/openai/gpt-5.4-mini", "--max-spend", "6",
                      "--judge-model", "openrouter:meta-llama/llama-4-maverick", "--judge-max-spend", "2.5")
    captured = capsys.readouterr()
    assert code == 5
    assert (f"pre-flight: REFUSED - judge openrouter:meta-llama/llama-4-maverick: {spend.UNREVIEWED_OPENROUTER_PRICE}: "
            "'openrouter/meta-llama/llama-4-maverick'") in captured.err
    assert "pre-flight bound" not in captured.out
    # a padded bare provider passes the registry resolver as an Anthropic model id but expands to a provider with
    # no consumer_default; it used to raise out of the pre-flight, and is now a named refusal
    code = _preflight("--target", "openrouter/openai/gpt-5.4-mini", "--max-spend", "6",
                      "--judge-model", " openrouter ", "--judge-max-spend", "2.5")
    assert code == 5 and "no consumer_default" in capsys.readouterr().err
    code = _preflight("--target", "openrouter/openai/gpt-5.4-mini", "--max-spend", "6",
                      "--judge-model", "openrouter:anthropic/claude-haiku-4.5", "--judge-max-spend", "2.5")
    out = capsys.readouterr().out
    assert code == 0, out
    assert ("judge openrouter:anthropic/claude-haiku-4.5: openrouter channel, in 1.06/Mtok out 5.3/Mtok "
            "(registry:openrouter:pricing)") in out
    # a judge that routes through OpenRouter under its own vendor entry (openai:, xai:) is priced by that entry,
    # which the rule does not cover; and a non-OpenRouter target is not checked at all
    code = _preflight("--target", "anthropic/claude-haiku-4-5", "--max-spend", "6",
                      "--judge-model", "claude-haiku-4-5", "--judge-max-spend", "2.5")
    assert code == 0 and "preflight: clear" in capsys.readouterr().out


def test_a_standalone_judge_pass_refuses_an_unreviewed_openrouter_judge_before_any_call(tmp_path, capsys):
    """The workflow's pre-flight covers the judge of a fired run; a judge pass
    started on its own (a local re-judge of a landed run) never passed it, so
    `judge` refuses the same specs before it reads the run or calls anyone."""
    run_dir = tmp_path / "run_x"
    run_dir.mkdir()
    for spec in ("openrouter:meta-llama/llama-4-maverick", "openrouter"):
        code = cli.main(["judge", "--run-dir", str(run_dir), "--judge-model", spec, "--judge-max-spend", "0.5"])
        assert code == 5 and "refused before any judge call" in capsys.readouterr().err, spec
    assert list(run_dir.iterdir()) == [], "nothing written"


# ------------------------------------------------------------------ Inspect (locked environment only)


def test_inspect_names_each_reviewed_model_exactly_as_the_preflight_checks_it(registry, monkeypatch):
    """The pre-flight checks the target string; `task.register_prices` and the
    usage rows key the price by `str(get_model(target))`. For every reviewed
    slug the two are the same string, so the price the pre-flight admitted is
    the price Inspect's cost_limit and the sidecar use. Offline: a dummy key,
    no request, no memoised model left behind."""
    inspect_model = pytest.importorskip("inspect_ai.model")
    monkeypatch.setenv("OPENROUTER_API_KEY", "offline-test-key-never-sent")
    for slug in registry["openrouter"]["pricing"]:
        name = f"openrouter/{slug}"
        model = inspect_model.get_model(name, api_key="offline-test-key-never-sent", memoize=False)
        assert str(model) == name
        assert spend.resolve_price(str(model)).source == "registry:openrouter:pricing"

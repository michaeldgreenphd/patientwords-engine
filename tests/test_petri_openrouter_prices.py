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

A reviewed entry sits ~5% above list, so it no longer covers prompt-cache
tokens the cost sidecar books at $0 the way the 5/30 catch-all did (review of
2026-09-23). An `openrouter/` target is therefore also refused until the
sidecar books cache reads and writes (`spend.cache_booking_problems`); the
tests of that gate hold both before and after the sidecar prices them.

Runs under the dev environment; the one test that constructs Inspect models
skips there and runs under the locked Petri environment."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

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


def _archived_openrouter_bills(registry: dict) -> dict[str, list[tuple[int, int, int, float]]]:
    """slug -> [(prompt tokens, prompt-cache tokens, completion tokens, billed
    USD)] for every archived advice call that went through OpenRouter and
    carries OpenRouter's bill. A call is OpenRouter-routed when its provider's
    registry base_url is OpenRouter's (openrouter:, openai:, xai:, deepseek:,
    moonshot:); the prompt count includes the cache tokens (cached reads plus
    cache writes), and tokens and bill come from the same usage block, so the
    comparison is exact."""
    routed = {name for name, cfg in registry.items()
              if isinstance(cfg, dict) and "openrouter.ai" in str(cfg.get("base_url", ""))}
    bills: dict[str, list[tuple[int, int, int, float]]] = {}
    for path in ARCHIVES:
        for line in path.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            provider, _, slug = str(rec.get("model_requested") or "").partition(":")
            usage = ((rec.get("response_raw") or {}).get("usage") or {}) if provider in routed else {}
            if usage.get("cost") is None:
                continue
            details = usage.get("prompt_tokens_details") or {}
            cache = int(details.get("cached_tokens") or 0) + int(details.get("cache_write_tokens") or 0)
            bills.setdefault(slug, []).append((int(usage.get("prompt_tokens") or 0), cache,
                                               int(usage.get("completion_tokens") or 0), float(usage["cost"])))
    return bills


def _understated_bills(rate: list[float], bills: list[tuple[int, int, int, float]], *, cache_free: bool = False) -> int:
    """How many archived calls OpenRouter billed above what `rate` books for
    them. By default every prompt token is booked at the input rate, the basis
    of the advice lane and of a Petri judge (both book OpenRouter's
    `prompt_tokens`). `cache_free` books the prompt-cache tokens at $0, the
    least any Petri target sidecar path books (Inspect counts them outside
    `input_tokens`)."""
    return sum(1 for p, cache, c, cost in bills
               if cost > (p - (cache if cache_free else 0)) * rate[0] / 1e6 + c * rate[1] / 1e6 + 1e-9)


def _lock_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    # the dev environment is not the locked one; these tests are about prices, which the pre-flight checks after the lock
    monkeypatch.setattr(cli, "verify_lock", lambda *a, **k: envlock.LockReport(lock_path="locked-for-test",
                                                                               lock_sha256="0" * 64, digest_matches=True))


@pytest.fixture
def cache_booked(monkeypatch: pytest.MonkeyPatch) -> None:
    """The pre-flight as it runs once the cost sidecar books prompt-cache
    tokens, for the tests of prices and bounds: while `reprice_usage` drops
    those tokens the cache gate refuses every `openrouter/` target before the
    bound. The gate itself is tested on its own below."""
    monkeypatch.setattr(cli, "cache_booking_problems", lambda *a, **k: [])


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
        # even with every cache token booked at $0 (580 of the 581 archived grok-4.3 calls report cached tokens). The
        # archives are single-turn, output-heavy advice calls, so this cannot show a multi-turn, prompt-heavy Petri
        # target safe with its cache tokens unbooked; the cache gate below is what refuses that
        assert _understated_bills(rate, bills.get(slug, []), cache_free=True) == 0, \
            f"{slug}: {rate} books some archived call below its bill once its cache tokens are free"


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


PREREGISTRATION = ROOT / "docs" / "preregistration_advice.md"
# the registry digest the preregistration's 2026-07-22 metering amendment re-froze, the last one it recorded before
# the 2026-09-23 metering correction
REFROZEN_20260722 = "84acef3606cb8afa10cabe5a0c72cc772a5838a8111a47f297e8cf6f7ae59fee"


REGISTRY_IN_GIT = "data/advice_providers.json"


def _git(*args: str) -> bytes | None:
    """stdout of a git command run in this checkout, or None when it fails."""
    try:
        return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, check=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return None


def _unrecorded_registry_revisions(git: Callable[..., bytes | None], text: str,
                                   refrozen: str = REFROZEN_20260722) -> list[str]:
    """The registry revisions, newest first, from HEAD back to the one whose
    sha256 is `refrozen`, that `text` does not record by sha256. Fails when
    the history never reaches `refrozen`.

    Skips, with a reason, when the checkout cannot supply that history: a
    shallow clone, or a partial clone whose missing objects git cannot fetch
    offline. A partial clone is not shallow, but `git log -- <path>` needs
    every commit's tree (absent from a treeless clone) and `git show` needs
    every revision's blob (absent from a blobless one). Until the review of
    2026-09-23 a failed call became empty output here, so a partial clone
    failed the test with "not in the registry's history" instead of skipping
    it."""
    if git("rev-parse", "--is-shallow-repository") != b"false\n":
        pytest.skip("needs a git checkout with the registry's full history")
    # --diff-filter=ACMRT leaves out a commit that deletes the registry (git holds none), so every listed commit has the
    # file and a failed `git show` below is an object this checkout lacks, never a revision without the registry
    log = git("log", "--format=%H", "--diff-filter=ACMRT", "--", REGISTRY_IN_GIT)
    if log is None:
        pytest.skip(f"git could not walk the history of {REGISTRY_IN_GIT} (a partial clone without its trees?)")
    unrecorded = []
    for commit in log.decode().split():
        blob = git("show", f"{commit}:{REGISTRY_IN_GIT}")
        if blob is None:
            pytest.skip(f"git could not read {REGISTRY_IN_GIT} at {commit[:8]} (a partial clone without its blobs?)")
        digest = hashlib.sha256(blob).hexdigest()
        if digest == refrozen:
            return unrecorded
        if digest not in text:
            unrecorded.append(f"{commit[:8]} {digest}")
    pytest.fail(f"the re-frozen digest {refrozen[:12]} is not in the registry's history")


def test_the_preregistration_records_every_registry_revision_since_its_2026_07_22_refreeze():
    """Regression for the metering correction's first draft, which counted
    four registry revisions since that re-freeze where git holds five
    (5e444ca1 was missed). Walks the registry's history back to the re-frozen
    digest and requires the sha256 of every revision since, this change's
    included, to appear in the preregistration. Needs the full history, so a
    shallow or partial clone skips it."""
    unrecorded = _unrecorded_registry_revisions(_git, PREREGISTRATION.read_text(encoding="utf-8"))
    assert not unrecorded, f"registry revisions whose sha256 docs/preregistration_advice.md does not record: {unrecorded}"


def _fake_git(blobs: dict[str, bytes | None], *, log_ok: bool = True) -> Callable[..., bytes | None]:
    """A git with a full, non-shallow history of the registry: `blobs` maps
    commit -> the registry's bytes there, newest first, None where the object
    store lacks the blob; `log_ok=False` is a store that lacks the trees."""
    def git(*args: str) -> bytes | None:
        if args[:1] == ("rev-parse",):
            return b"false\n"
        if args[:1] == ("log",):
            return "".join(f"{c}\n" for c in blobs).encode() if log_ok else None
        if args[:1] == ("show",):
            return blobs[args[1].partition(":")[0]]
        raise AssertionError(f"unexpected git call {args}")
    return git


def test_the_revision_check_skips_a_partial_clone_instead_of_failing():
    """Regression for the review of 2026-09-23: a treeless partial clone fails
    `git log -- <path>` and a blobless one fails `git show`; both skip, where
    they failed with "not in the registry's history"."""
    old, new = b"old registry", b"new registry"
    with pytest.raises(pytest.skip.Exception, match="without its trees"):
        _unrecorded_registry_revisions(_fake_git({"b" * 40: new, "a" * 40: old}, log_ok=False), "",
                                       refrozen=hashlib.sha256(old).hexdigest())
    with pytest.raises(pytest.skip.Exception, match=f"at {'b' * 8} .*without its blobs"):
        _unrecorded_registry_revisions(_fake_git({"b" * 40: None, "a" * 40: old}), "",
                                       refrozen=hashlib.sha256(old).hexdigest())


def test_the_revision_check_still_reports_what_a_full_history_shows():
    """The skips above do not weaken the check on a full clone: an unrecorded
    revision is reported, a recorded one is not, and a history that never
    reaches the re-frozen digest fails."""
    old, new, newer = b"old registry", b"new registry", b"newer registry"
    blobs = {"c" * 40: newer, "b" * 40: new, "a" * 40: old}
    refrozen, h_new, h_newer = (hashlib.sha256(x).hexdigest() for x in (old, new, newer))
    assert _unrecorded_registry_revisions(_fake_git(blobs), h_newer, refrozen=refrozen) == [f"{'b' * 8} {h_new}"]
    assert _unrecorded_registry_revisions(_fake_git(blobs), h_new + h_newer, refrozen=refrozen) == []
    with pytest.raises(pytest.fail.Exception, match="not in the registry's history"):
        _unrecorded_registry_revisions(_fake_git(blobs), h_new + h_newer, refrozen="0" * 64)


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


def test_cli_preflight_bounds_thirty_gpt_5_4_mini_samples_at_the_reviewed_output_rate(monkeypatch, capsys, cache_booked):
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


def test_cli_preflight_refuses_an_unreviewed_openrouter_judge_and_admits_a_reviewed_one(monkeypatch, capsys, cache_booked):
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


# ------------------------------------------------------------------ prompt-cache tokens (review of 2026-09-23)

CACHE_FIELDS = ("input_tokens_cache_read", "input_tokens_cache_write")
# Multi-turn target calls as OpenRouter reports them: (prompt_tokens, cached_tokens, cache_write_tokens,
# completion_tokens), the prompt count including both cache counts. Prompt and completion sizes are the four target
# turns of landed run_35351739969_1 sample 3 (sanitised_log.json). The cached counts follow what each model's
# archived OpenRouter calls report: grok-4.3 reports cached tokens on 580 of its 581 calls, in 128-token steps, short
# prompts included; OpenAI caches only prompts of 1024 tokens or more. The haiku case is one 4800-token cache write
# and then its read, from the cache markers Inspect's OpenRouter provider adds to `openrouter/anthropic/*` by default.
CACHED_TURNS = {
    "x-ai/grok-4.3": [(679, 0, 0, 63), (801, 640, 0, 296), (1105, 1024, 0, 75), (1241, 1152, 0, 206)],
    "openai/gpt-5.4-mini": [(679, 0, 0, 63), (801, 0, 0, 296), (1105, 1024, 0, 75), (1241, 1152, 0, 206)],
    "anthropic/claude-haiku-4.5": [(5000, 0, 4800, 300), (5700, 4800, 0, 300)],
}


def _inspect_usage(prompt: int, cached: int, written: int, completion: int) -> SimpleNamespace:
    """The ModelUsage inspect_ai 0.3.237 builds from an OpenRouter usage
    block: cached reads subtracted from the prompt count
    (`model_output_from_openai`), then cache writes (`openrouter.py`
    `_apply_cache_creation_usage`, which leaves the field unset for zero).
    Pinned to Inspect's own code by the locked-environment test below."""
    return SimpleNamespace(input_tokens=max(0, prompt - cached - written), output_tokens=completion,
                           total_tokens=prompt + completion, input_tokens_cache_read=cached,
                           input_tokens_cache_write=written or None, reasoning_tokens=None)


def _sidecar_booking(target: str, usages: list[SimpleNamespace], *, aggregate: bool) -> float | None:
    """What the cost sidecar books for these target calls, through the real
    `usage_from_samples` and `reprice_usage`. `aggregate` gives the sample a
    summed `model_usage`, as a completed Inspect sample has; without it the
    rows come from the model events alone, as for a failed eval."""
    events = [SimpleNamespace(event="model", role="target", model=target, output=SimpleNamespace(usage=u)) for u in usages]
    model_usage = {}
    if aggregate:
        summed = {f: sum(getattr(u, f) or 0 for u in usages)
                  for f in ("input_tokens", "output_tokens", "total_tokens", *CACHE_FIELDS)}
        model_usage = {target: SimpleNamespace(reasoning_tokens=None, **summed)}
    cost, _ = spend.reprice_usage(spend.usage_from_samples([SimpleNamespace(model_usage=model_usage, events=events)]),
                                  target=target)
    return cost


def _worst_case_bill(slug: str, turns: list[tuple[int, int, int, int]]) -> float:
    """The most OpenRouter can bill these turns at the catalogue's list price:
    uncached and cached-read prompt tokens at the input rate (a read is
    discounted, never dearer), each cache write at 1.25 times it (Anthropic's
    5-minute write), completion tokens at the output rate."""
    list_in, list_out = _catalogue_list_prices()[slug]
    return sum(((p - cr - cw) * list_in + cr * list_in + cw * 1.25 * list_in + c * list_out) / 1e6
               for p, cr, cw, c in turns)


@pytest.mark.parametrize("aggregate", [True, False], ids=["aggregate", "events_only"])
@pytest.mark.parametrize("slug", sorted(CACHED_TURNS))
def test_an_openrouter_target_is_refused_unless_its_cached_calls_are_booked_at_or_above_the_bill(slug, aggregate):
    """Regression for the review of 2026-09-23: with the reviewed near-list
    entries and cache tokens booked at $0, these turns booked 0.47 (grok-4.3),
    0.76 (gpt-5.4-mini) and 0.29 (claude-haiku-4.5) of the most they can be
    billed, and nothing refused the target. Holds before the sidecar prices
    cache tokens (the gate refuses) and after (the booking covers the bill)."""
    target = f"openrouter/{slug}"
    turns = CACHED_TURNS[slug]
    booked = _sidecar_booking(target, [_inspect_usage(*t) for t in turns], aggregate=aggregate)
    bill = _worst_case_bill(slug, turns)
    assert spend.cache_booking_problems(target) or (booked is not None and booked >= bill - 1e-12), \
        f"{target} is admitted, but its sidecar books ${booked} for turns OpenRouter can bill ${bill:.6f}"


def _carrying_usage(samples, role="target"):
    """A `usage_from_samples` that carries the aggregate's cache counts."""
    return {model: {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens, "total_tokens": u.total_tokens,
                    **{f: getattr(u, f) for f in CACHE_FIELDS}, "calls": 1, "calls_without_usage": 0}
            for sample in samples for model, u in sample.model_usage.items()}


def _dropping_usage(samples, role="target"):
    """A `usage_from_samples` that carries input, output and total only."""
    return {model: {k: v for k, v in row.items() if k not in CACHE_FIELDS}
            for model, row in _carrying_usage(samples).items()}


def _pricing(read: float, write: float, *, missing: bool = False):
    """A `reprice_usage` that books cache reads and writes at these multiples
    of the input rate (or returns no total, as for missing usage)."""
    def reprice(model_usage, registry=None, target=None):
        total = 0.0
        for model, u in model_usage.items():
            price = spend.resolve_price(model, registry)
            total += (u["input_tokens"] * price.input_per_mtok + u["output_tokens"] * price.output_per_mtok
                      + (read * (u.get("input_tokens_cache_read") or 0)
                         + write * (u.get("input_tokens_cache_write") or 0)) * price.input_per_mtok) / 1e6
        return (None if missing else total), []
    return reprice


@pytest.mark.parametrize("usage_fn, reprice, refused", [
    (_carrying_usage, _pricing(1.0, 2.0), ()),              # reads at the input rate, writes at the 1-hour TTL's 2x
    (_carrying_usage, _pricing(1.0, 1.25), ()),             # exactly the floors
    (_carrying_usage, _pricing(0.0, 0.0), CACHE_FIELDS),    # carried but not priced
    (_dropping_usage, _pricing(1.0, 2.0), CACHE_FIELDS),    # priced but never carried to the row: the spend-report path
    (_carrying_usage, _pricing(0.1, 2.0), CACHE_FIELDS[:1]),   # a read at a vendor's cache discount, below the input rate
    (_carrying_usage, _pricing(1.0, 1.0), CACHE_FIELDS[1:]),   # a write at the input rate, below Anthropic's 1.25x
    (_carrying_usage, _pricing(1.0, 2.0, missing=True), CACHE_FIELDS),   # no total at all is not a booking
], ids=["priced", "at_floor", "unpriced", "not_carried", "read_discounted", "write_at_input", "missing"])
def test_the_cache_gate_follows_what_the_sidecar_books(monkeypatch, usage_fn, reprice, refused):
    """The gate runs the sidecar's own functions on a probe, so it refuses or
    clears by what they book, whichever way they are written."""
    monkeypatch.setattr(spend, "usage_from_samples", usage_fn)
    monkeypatch.setattr(spend, "reprice_usage", reprice)
    target = "openrouter/x-ai/grok-4.3"
    problems = spend.cache_booking_problems(f"  {target} ")
    assert len(problems) == len(refused)
    for field, problem in zip(refused, problems):
        assert problem.startswith(f"{spend.CACHE_TOKENS_UNBOOKED}: {target!r}: the cost sidecar books 1000000 {field} tokens")


def test_the_cache_gate_checks_openrouter_targets_only(monkeypatch):
    def never(*a, **k):
        raise AssertionError("the probe ran for a target the gate does not check")

    monkeypatch.setattr(spend, "reprice_usage", never)
    for name in ("anthropic/claude-haiku-4-5", "claude-haiku-4-5", "mockllm/model", "none/none"):
        assert spend.cache_booking_problems(name) == [], name


def test_cli_preflight_refuses_an_openrouter_target_whose_cache_tokens_the_sidecar_drops(monkeypatch, capsys):
    _lock_ok(monkeypatch)
    monkeypatch.setattr(spend, "usage_from_samples", _dropping_usage)
    monkeypatch.setattr(spend, "reprice_usage", _pricing(1.0, 2.0))
    code = _preflight("--target", "openrouter/openai/gpt-5.4-mini", "--max-spend", "6")
    captured = capsys.readouterr()
    assert code == 5
    assert f"pre-flight: REFUSED - target {spend.CACHE_TOKENS_UNBOOKED}: 'openrouter/openai/gpt-5.4-mini'" in captured.err
    assert "pre-flight bound" not in captured.out, "refused before the bound"
    # an Anthropic target is not checked, and a sidecar that carries and prices cache tokens clears the OpenRouter one
    assert _preflight("--target", "anthropic/claude-haiku-4-5", "--max-spend", "6") == 0
    monkeypatch.setattr(spend, "usage_from_samples", _carrying_usage)
    assert _preflight("--target", "openrouter/openai/gpt-5.4-mini", "--max-spend", "6") == 0
    assert "pre-flight bound: 6 sample(s) x 1 epoch(s) x 40000 tokens -> $1.1400" in capsys.readouterr().out


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


def test_the_usage_replica_matches_inspects_own_openrouter_mapping(monkeypatch):
    """`_inspect_usage` against the code it stands in for: every cached turn
    above, through `model_output_from_openai` and
    `_apply_cache_creation_usage`. Also pins the two facts the cache gate's
    write floor rests on: Inspect's OpenRouter provider enables Anthropic
    cache markers for `openrouter/anthropic/*` under the config the task
    passes (no `cache_prompt`), for no other vendor, and its markers carry no
    TTL (Anthropic's 5-minute default). Offline: a dummy key, no request."""
    inspect_model = pytest.importorskip("inspect_ai.model")
    from inspect_ai.model._openai import model_output_from_openai
    from inspect_ai.model._providers import openrouter
    from openai.types.chat import ChatCompletion

    for slug, turns in CACHED_TURNS.items():
        for p, cr, cw, c in turns:
            usage = {"prompt_tokens": p, "completion_tokens": c, "total_tokens": p + c,
                     "prompt_tokens_details": {"cached_tokens": cr, "cache_write_tokens": cw}}
            completion = ChatCompletion.model_validate({
                "id": "offline", "object": "chat.completion", "created": 0, "model": slug, "usage": usage,
                "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "ok"}}]})
            out = model_output_from_openai(completion, [])
            openrouter._apply_cache_creation_usage(out, SimpleNamespace(response={"usage": usage}))
            expected = _inspect_usage(p, cr, cw, c)
            for field in ("input_tokens", "output_tokens", "total_tokens", *CACHE_FIELDS):
                assert getattr(out.usage, field) == getattr(expected, field), (slug, (p, cr, cw, c), field)

    monkeypatch.setenv("OPENROUTER_API_KEY", "offline-test-key-never-sent")
    for slug in CACHED_TURNS:
        api = inspect_model.get_model(f"openrouter/{slug}", api_key="offline-test-key-never-sent", memoize=False).api
        assert api._cache_prompt_enabled(inspect_model.GenerateConfig()) is slug.startswith("anthropic/"), slug
    assert openrouter._ephemeral() == {"type": "ephemeral"}

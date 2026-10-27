"""Bounded campaign tests: fake transports, temporary sources, no provider calls."""
from __future__ import annotations

import copy
from datetime import date, datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import signal
import time
from typing import Any

import pytest
import yaml

from scripts import action_annotations as aa
from scripts import action_annotation_transport as at
from scripts import action_pilot as ap
from scripts import action_pilot_budget as ab
from scripts import action_pilot_inputs as ai
from scripts import action_quote_annotations as aq
from scripts import fire_trigger as ft

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures/action_annotations'


@pytest.fixture
def price() -> dict:
    return ab.prices(ROOT, date(2026, 10, 26))


@pytest.fixture
def packet() -> tuple[dict, dict]:
    sources = aa.read_json(FIXTURES / 'sources.json')['items']
    replies = aa.read_json(FIXTURES / 'messages_attempts.json')['items']
    items, by_wire = [], {}
    for i in range(14):
        source = sources[i % 10]
        text = source['text'] + (' ' * i)
        wire = at.prepare_wire('Return the explicit items.', json.dumps({'response': text}))
        key = aa.digest(aa.encoded(wire))
        source_id = f's{i + 1:02}' if i < 10 else f'R{i - 9:02}'
        items.append({'source_id': source_id, 'source_sha256': aa.digest(text.encode()), 'text': text,
                      'wire': wire, 'request_sha256': key, 'origin': 'synthetic_fixture'})
        body = json.loads(replies[i % 10]['body'])
        body['model'] = 'claude-haiku-5-5'
        by_wire[key] = body
    return {'requests': items}, by_wire


def execute(tmp_path: Path, packet: tuple, price: dict, *, send: Any = None, count: Any = None,
            identity_extra: dict | None = None) -> tuple:
    calls, counts = [], []
    doc, replies = packet

    def sender(wire: dict) -> at.Reply:
        calls.append(aa.digest(aa.encoded(wire)))
        assert (tmp_path / 'result/action_annotation_attempts' / calls[-1] / 'start.json').is_file()
        if send:
            return send(wire)
        return at.Reply(200, 'fixture_request', aa.encoded(replies[calls[-1]]), True, None)

    def counter(wire: dict) -> at.Reply:
        counts.append(aa.digest(aa.encoded(wire)))
        assert not calls
        return count(wire) if count else at.Reply(
            200, 'fixture_count', b'{"input_tokens":1000,"context_management":null}', True, None)

    identity = {'execution_day_utc': datetime.now(timezone.utc).date().isoformat(),
                'inference': {'environment': 'synthetic_fixture'}, 'journal_nonce': ai.NONCE,
                **(identity_extra or {})}
    report = ap.run(doc, price, identity, tmp_path / 'result', sender, counter)
    return report, calls, counts


def test_all_counts_precede_one_attempt_per_item_and_preserve_bytes(tmp_path: Path, packet: tuple, price: dict) -> None:
    report, calls, counts = execute(tmp_path, packet, price)
    assert report['status'] == 'complete_semantics_unverified'
    assert len(calls) == len(set(calls)) == len(counts) == 14
    assert report['not_attempted'] == [] and report['unknown_charge'] is False
    assert report['cost_usd'] > 0 and not report['reservation_release_allowed']
    assert report['purpose'] == 'assistance_not_independent_accuracy'
    for path, sha in report['artifact_hashes'].items():
        assert aa.digest((tmp_path / 'result' / path).read_bytes()) == sha
    with pytest.raises(FileExistsError):
        execute(tmp_path, packet, price)


@pytest.mark.parametrize('kind', ['429', 'timeout', 'missing_usage', 'invalid_json', 'wrong_model', 'throws'])
def test_failed_or_unknown_attempt_stops_and_retains_charge(
    tmp_path: Path, packet: tuple, price: dict, kind: str,
) -> None:
    def send(wire: dict) -> at.Reply:
        body = copy.deepcopy(packet[1][aa.digest(aa.encoded(wire))])
        if kind == 'throws':
            raise RuntimeError('fixture_sensitive_text')
        if kind == '429':
            return at.Reply(429, 'fixture', b'{}', True, None)
        if kind == 'timeout':
            return at.Reply(200, 'fixture', aa.encoded(body), False, 'timeout')
        if kind == 'missing_usage':
            body.pop('usage')
        if kind == 'wrong_model':
            body['model'] = 'another_model'
        return at.Reply(200, 'fixture', b'{' if kind == 'invalid_json' else aa.encoded(body), True, None)

    report, calls, counts = execute(tmp_path, packet, price, send=send)
    assert len(calls) == 1 and len(counts) == 14
    assert report['cost_usd'] is None and report['unknown_charge'] is True
    assert len(report['not_attempted']) == 13 and not report['reservation_release_allowed']
    assert 'fixture_sensitive_text' not in (tmp_path / 'result/report.json').read_text()
    assert len(list((tmp_path / 'result').rglob('start.json'))) == 1


def test_invalid_annotation_stops_with_known_usage_cost(tmp_path: Path, packet: tuple, price: dict) -> None:
    for body in packet[1].values():
        body['content'][0]['text'] = '{}'
    report, calls, _ = execute(tmp_path, packet, price)
    assert len(calls) == 1 and report['status'] == 'stopped_incomplete'
    assert report['cost_usd'] > 0 and report['unknown_charge'] is False
    assert report['refusal'] == 'annotation_failed_stop'
    assert report['items'][0]['interpretation']['status'] == 'invalid_annotation'


def test_documented_standard_usage_details_are_not_double_counted(price: dict) -> None:
    usage = {'input_tokens': 1000, 'output_tokens': 200, 'cache_creation_input_tokens': 0,
             'cache_read_input_tokens': 0, 'cache_creation': {'ephemeral_1h_input_tokens': 0,
             'ephemeral_5m_input_tokens': 0}, 'server_tool_use': {'web_fetch_requests': 0, 'web_search_requests': 0},
             'output_tokens_details': {'thinking_tokens': 0}, 'inference_geo': 'global',
             'service_tier': 'standard', 'speed': 'standard'}
    assert ab.usage_cost(usage, price) == Decimal('0.0002')
    for key, value in [('inference_geo', 'regional'), ('speed', 'fast'),
                       ('output_tokens_details', {'thinking_tokens': 1}),
                       ('output_tokens_details', {'thinking_tokens': False})]:
        with pytest.raises(aa.AnnotationRefusal):
            ab.usage_cost({**usage, key: value}, price)


@pytest.mark.parametrize('raw', [b'{}', b'{"input_tokens":true}', b'{"input_tokens":1e999}',
                                 b'{"input_tokens":-1}', b'{"input_tokens":1,"input_tokens":2}',
                                 b'{"input_tokens":1,"context_management":{"original_input_tokens":2}}',
                                 b'{"input_tokens":1,"context_management":false}'])
def test_invalid_count_prevents_all_paid_calls(tmp_path: Path, packet: tuple, price: dict, raw: bytes) -> None:
    report, calls, counts = execute(tmp_path, packet, price,
        count=lambda wire: at.Reply(200, 'fixture', raw, True, None))
    assert not calls and len(counts) == 1 and report['cost_usd'] == 0
    assert len(report['not_attempted']) == 14


def test_count_cost_and_next_call_full_context_bound_are_separate(tmp_path: Path, packet: tuple, price: dict) -> None:
    assert ab.call_bound(price) == Decimal('0.52048')
    for body in packet[1].values():
        body['usage'] = {'input_tokens': 1000000, 'output_tokens': 8192}
    report, calls, _ = execute(tmp_path, packet, price)
    assert report['estimated_total_upper_rate_usd'] == '0.29372'
    assert len(calls) == 1 and report['cost_usd'] == 0.52048
    assert report['refusal'] == 'insufficient_next_call_headroom'
    assert report['cost_usd'] <= 1


def test_large_estimated_total_prevents_generation(tmp_path: Path, packet: tuple, price: dict) -> None:
    report, calls, _ = execute(tmp_path, packet, price,
        count=lambda wire: at.Reply(200, 'fixture', b'{"input_tokens":1000000}', True, None))
    assert not calls and report['refusal'] == 'estimated_total_exceeds_ceiling'


@pytest.mark.parametrize('usage', [None, {}, {'input_tokens': True, 'output_tokens': 1},
    {'input_tokens': 1, 'output_tokens': 8193}, {'input_tokens': 1, 'output_tokens': 1, 'new_charge': 1},
    {'input_tokens': 1, 'output_tokens': 1, 'cache_read_input_tokens': 10},
    {'input_tokens': 1, 'output_tokens': 1, 'service_tier': 'priority'}])
def test_unknown_usage_is_not_priced(usage: Any, price: dict) -> None:
    with pytest.raises(aa.AnnotationRefusal):
        ab.usage_cost(usage, price)


def test_tier_threshold_and_price_expiry(price: dict) -> None:
    assert ab.usage_cost({'input_tokens': 100000, 'output_tokens': 100}, price) == Decimal('0.01005')
    assert ab.usage_cost({'input_tokens': 100001, 'output_tokens': 100}, price) == Decimal('0.0502505')
    for day in (date(2026, 10, 25), date(2026, 11, 3)):
        with pytest.raises(aa.AnnotationRefusal, match='price_receipt_expired_or_future'):
            ab.prices(ROOT, day)


def test_total_deadline_restores_handler_and_timer() -> None:
    before = signal.getsignal(signal.SIGALRM)
    with pytest.raises(TimeoutError):
        with ap.deadline(.01):
            time.sleep(.1)
    assert signal.getsignal(signal.SIGALRM) == before
    assert signal.getitimer(signal.ITIMER_REAL) == (0, 0)


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(aa.encoded(value))


def test_monthly_bound_counts_old_unknown_and_resolved_current_holds(tmp_path: Path) -> None:
    write(tmp_path / 'ops/dashboard.json', {'spend': {'lifetime_generation_usd': 80}})
    write(tmp_path / 'data/advice/example.report.json', {'cost_usd': 79})
    entries = [{'trigger': 'another', 'fired_utc': '2026-10-01T00:00:00Z', 'max_spend': 4, 'resolved': True},
               {'trigger': 'another', 'fired_utc': '2026-09-01T00:00:00Z', 'max_spend': 5, 'resolved': False}]
    result = ab.availability(tmp_path, entries, date(2026, 10, 26))
    assert result['committed_upper_bound_usd'] == '90'
    entries[0]['max_spend'] = 120
    with pytest.raises(aa.AnnotationRefusal, match='monthly_allocation_unavailable'):
        ab.availability(tmp_path, entries, date(2026, 10, 26))
    write(tmp_path / 'data/advice/example.report.json', {'cost_usd': None})
    with pytest.raises(aa.AnnotationRefusal, match='unknown_cost'):
        ab.availability(tmp_path, [], date(2026, 10, 26))


def live_params() -> dict:
    return {'mode': 'run', 'plan_sha256': ai.PLAN_SHA256, 'max_spend': '1.00',
            'expected_commit': 'a' * 40, '_nonce': ai.NONCE}


def test_owner_authorized_recovery_has_a_distinct_fixed_nonce() -> None:
    recovery = aa.read_json(ROOT / 'data/action_annotations/recovery_20261026.v1.json')
    params = {**live_params(), '_nonce': recovery['nonce']}
    assert recovery['nonce'] != ai.NONCE
    assert not ap.params_problems(params, ROOT)
    assert ft.reused_nonce(ap.TRIGGER, params, [{'trigger': ap.TRIGGER, 'nonce': recovery['nonce']}])


def test_lane_is_paid_once_and_park_has_no_admission_or_model_work() -> None:
    park = ft.PARK_DEFAULTS[ap.TRIGGER]
    assert not ft.is_paid_fire(ap.TRIGGER, park) and not ap.params_problems(park)
    assert ft.is_paid_fire(ap.TRIGGER, live_params()) and ap.TRIGGER in ft.NONCE_LANES
    assert ft.fire_lane(ap.TRIGGER, live_params()) == 'anthropic'
    assert not ap.params_problems(live_params())
    assert ft.reused_nonce(ap.TRIGGER, live_params(), [{'trigger': ap.TRIGGER, 'nonce': ai.NONCE}])
    for key, value in [('mode', 'RUN'), ('max_spend', '1.01'), ('max_spend', True),
                       ('_nonce', 'different'), ('plan_sha256', '0' * 64), ('expected_commit', 'main')]:
        assert ap.params_problems({**live_params(), key: value})


@pytest.mark.parametrize('key,value', [('GITHUB_ACTIONS', 'false'), ('GITHUB_EVENT_NAME', 'workflow_dispatch'),
    ('GITHUB_RUN_ATTEMPT', '2'), ('GITHUB_REF', 'refs/heads/other'), ('GITHUB_ACTOR', 'other'),
    ('GITHUB_TRIGGERING_ACTOR', 'other'), ('GITHUB_REPOSITORY', 'other/repo'), ('GITHUB_RUN_ID', '../bad')])
def test_ci_identity_refuses_before_source_or_key_access(monkeypatch: pytest.MonkeyPatch, key: str, value: str) -> None:
    monkeypatch.setattr(ap, 'params_problems', lambda *args: [])
    env = {'GITHUB_ACTIONS': 'true', 'GITHUB_EVENT_NAME': 'push', 'GITHUB_REF': 'refs/heads/main',
           'GITHUB_REPOSITORY': 'michaeldgreenphd/patientwords-engine', 'GITHUB_RUN_ATTEMPT': '1',
           'GITHUB_ACTOR': 'michaeldgreenphd', 'GITHUB_TRIGGERING_ACTOR': 'michaeldgreenphd', 'GITHUB_RUN_ID': '42'}
    with pytest.raises(aa.AnnotationRefusal):
        ap.admit_ci(live_params(), {**env, key: value})


def test_workflow_boundaries() -> None:
    doc = yaml.safe_load((ROOT / '.github/workflows/action_annotation.yml').read_text())
    assert set(doc[True]) == {'push'} and doc['concurrency']['cancel-in-progress'] is False
    job = doc['jobs']['pilot']
    assert '!github.event.created' in job['if'] and 'github.run_attempt == 1' in job['if']
    steps = job['steps']
    live = next(s for s in steps if s.get('name') == 'Run the single admitted pass')
    assert live['if'] == "steps.params.outputs.mode == 'run'"
    assert 'pip install' not in json.dumps(steps) and 'workflow_dispatch' not in doc[True]
    upload = next(s for s in steps if 'upload-artifact' in s.get('uses', ''))
    assert upload['if'].startswith('always()') and upload['with']['if-no-files-found'] == 'error'
    stage = next(s for s in steps if s.get('id') == 'sidecar')
    assert "target.open('xb')" in stage['run'] and "report.pop('items', None)" in stage['run']


@pytest.fixture
def source_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from scripts import advice_eval as ae
    from scripts import seal_check as sc
    from scripts import tierb_split as tb

    root = tmp_path / 'source'
    plan = aa.read_json(ROOT / ai.PLAN)
    fixture = aa.read_json(FIXTURES / 'sources.json')
    for name in plan['contract_files']:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / name).read_bytes())
    stimulus = {'items': [{'id': f'item-{i}'} for i in range(4)]}
    stimulus_hash = ae.sha256_text(ae.canonical_json(stimulus))
    rows, selected = [], []
    for i in range(4):
        text = fixture['items'][i]['text'] + ' fixture suffix'
        row = {'record_type': 'advice', 'stimulus_id': f'item-{i}', 'arm': 'left', 'model_requested': 'fixture',
               'sample_k': 1, 'stimuli_sha256': stimulus_hash, 'response_text': text,
               'response_sha256': aa.digest(text.encode()), 'prev_sha256': rows[-1]['record_sha256'] if rows else None}
        row['record_sha256'] = ae.sha256_text(ae.canonical_json(row))
        rows.append(row)
        selected.append({'review_id': f'R{i + 1:02}', 'archive_line_1based': i + 1, 'source_id': row['stimulus_id'],
                         **{k: row[k] for k in ('record_sha256', 'arm', 'model_requested', 'sample_k', 'response_sha256')}})
    paths = list(plan['source_files'])
    write(root / paths[0], stimulus)
    (root / paths[1]).write_bytes(b'\n'.join(aa.encoded(row) for row in rows))
    write(root / paths[2], {'records_total': 4, 'chain_head': rows[-1]['record_sha256']})
    plan['source_files'] = {p: aa.digest((root / p).read_bytes()) for p in paths}
    plan['responses'] = selected
    plan['stimuli_canonical_sha256'] = stimulus_hash
    plan['archive_chain_head'] = rows[-1]['record_sha256']
    rubric = aa.read_json(ROOT / 'data/action_annotations/rubric.v1.json')
    protocol = aa.read_json(ROOT / 'data/action_annotations/messages_protocol.v1.json')
    schema = aa.read_json(ROOT / 'data/action_annotations/annotation.v1.schema.json')
    system = json.dumps(rubric, ensure_ascii=False, sort_keys=True) + '\n' + protocol['format_instruction'] + '\n'
    system += aa.encoded(schema).decode()
    plan['request_hashes'] = {}
    texts = [(r['source_id'], r['text']) for r in fixture['items']]
    texts += [(r['review_id'], rows[i]['response_text']) for i, r in enumerate(selected)]
    for source_id, text in texts:
        wire = at.prepare_wire(system, json.dumps({'response': text}, ensure_ascii=False))
        plan['request_hashes'][source_id] = aa.digest(aa.encoded(wire))
    write(root / ai.PLAN, plan)
    monkeypatch.setattr(ai, 'PLAN_SHA256', aa.digest((root / ai.PLAN).read_bytes()))
    monkeypatch.setattr(sc, 'sealed_registry', lambda *args: ['fixture-registry'])
    monkeypatch.setattr(sc, 'scan_text', lambda *args, **kwargs: ([], []))
    monkeypatch.setattr(tb, 'tierb_start_stamp', lambda *args: '20260101T000000Z')
    monkeypatch.setattr(ae, '_selection_seal_check', lambda *args: None)
    return root


def test_source_admission_preserves_origins_joins_and_determinism(source_tree: Path) -> None:
    first = ai.prepare(source_tree)
    assert first == ai.prepare(source_tree)
    assert len(first['requests']) == 14
    for i, item in enumerate(first['requests']):
        assert item['origin'] == ('authored_synthetic_challenge' if i < 10 else 'archived_generated_response')
        wire = item['wire']
        assert 'source_id' not in wire['body'] and 'archive_join' not in wire['body']
        assert 'fixture' != wire['body']['model']
        if i >= 10:
            assert item['archive_join']['source_id'] == f'item-{i - 10}'


@pytest.mark.parametrize('mutation', ['record', 'text', 'join', 'count', 'request', 'contract', 'selection'])
def test_source_drift_is_refused_before_output(
    source_tree: Path, monkeypatch: pytest.MonkeyPatch, mutation: str,
) -> None:
    plan = aa.read_json(source_tree / ai.PLAN)
    if mutation in ('record', 'text', 'join'):
        key = {'record': 'record_sha256', 'text': 'response_sha256', 'join': 'source_id'}[mutation]
        plan['responses'][0][key] = 'wrong'
    elif mutation == 'request':
        plan['request_hashes']['s01'] = 'wrong'
    elif mutation == 'selection':
        plan['synthetic_ids'].reverse()
    elif mutation == 'contract':
        key = next(iter(plan['contract_files']))
        plan['contract_files'][key] = 'wrong'
    elif mutation == 'count':
        path = next(p for p in plan['source_files'] if p.endswith('.report.json'))
        report = aa.read_json(source_tree / path)
        report['records_total'] = 999
        write(source_tree / path, report)
        plan['source_files'][path] = aa.digest((source_tree / path).read_bytes())
    write(source_tree / ai.PLAN, plan)
    monkeypatch.setattr(ai, 'PLAN_SHA256', aa.digest((source_tree / ai.PLAN).read_bytes()))
    with pytest.raises(aa.AnnotationRefusal):
        ai.prepare(source_tree)


def test_seal_failure_is_not_suppressed(source_tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import seal_check as sc
    monkeypatch.setattr(sc, 'scan_text', lambda *args, **kwargs: (['fixture-hit'], []))
    with pytest.raises(aa.AnnotationRefusal, match='sealed_input'):
        ai.prepare(source_tree)


@pytest.fixture
def ci_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> tuple:
    import os
    import subprocess

    recovering = getattr(request, 'param', False)
    quoting = recovering in ('quotes', 'quotes_low_budget')
    now = datetime(2026, 10, 27 if quoting else 26, 13, 0, tzinfo=timezone.utc)
    prior = (ap.quote_campaign(ROOT)['prior_reservations'] if quoting else
             [ap.recovery_receipt(ROOT)['prior_reservation']] if recovering else [])
    nonce = ap.QUOTE_NONCE if quoting else ap.RECOVERY_NONCE if recovering else ai.NONCE

    class Clock(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            return now

    monkeypatch.setattr(ap, 'datetime', Clock)
    monkeypatch.setattr(ft, 'utc_now', lambda: now)
    monkeypatch.setenv('GITHUB_ACTIONS', 'true')
    root = tmp_path / 'repo'
    root.mkdir()
    remote = tmp_path / 'remote.git'
    env = {**os.environ, 'GIT_AUTHOR_NAME': 'Fixture', 'GIT_COMMITTER_NAME': 'Fixture',
           'GIT_AUTHOR_EMAIL': 'fixture', 'GIT_COMMITTER_EMAIL': 'fixture'}

    def git(*args: str) -> str:
        return subprocess.check_output(['git', *args], cwd=root, env=env, stderr=subprocess.DEVNULL, text=True).strip()

    git('init', '--bare', str(remote))
    git('init', '-b', 'main')
    names = [ai.PLAN, ai.PRICE, ap.RECOVERY]
    if quoting:
        names += [ap.QUOTE_CAMPAIGN, *ap.quote_campaign(ROOT)['contract_files']]
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / name).read_bytes())
    write(root / 'ops/dashboard.json', {'spend': {'lifetime_generation_usd': 0,
          'daily_ceiling_usd': 0.99 if recovering == 'quotes_low_budget' else
                               1.99 if recovering == 'low_budget' else 2.00}})
    (root / 'ops/trigger_journal.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in prior))
    git('add', '.')
    git('commit', '-m', 'fixture base')
    base = git('rev-parse', 'HEAD')
    params = {**live_params(), 'expected_commit': base, '_nonce': nonce}
    if quoting:
        params['plan_sha256'] = ap.QUOTE_CAMPAIGN_SHA256
    write(root / ap.TRIGGER_PATH, params)
    entry = {'trigger': ap.TRIGGER, 'fired_utc': now.isoformat(), 'max_spend': 1, 'resolved': False,
             'evicted': False, 'nonce': nonce, 'ref': ft.fire_ref(root), 'lane': 'anthropic',
             'params_sha256': ft.params_digest((root / ap.TRIGGER_PATH).read_text())}
    (root / 'ops/trigger_journal.jsonl').write_text(''.join(json.dumps(e) + '\n' for e in [*prior, entry]))
    git('add', '.')
    git('commit', '-m', 'fixture reservation')
    head = git('rev-parse', 'HEAD')
    git('remote', 'add', 'origin', str(remote))
    git('push', 'origin', 'HEAD:main')
    event = tmp_path / 'event.json'
    write(event, {'created': False, 'before': base, 'after': head})
    env = {'GITHUB_ACTIONS': 'true', 'GITHUB_EVENT_NAME': 'push', 'GITHUB_REF': 'refs/heads/main',
           'GITHUB_REPOSITORY': 'michaeldgreenphd/patientwords-engine', 'GITHUB_RUN_ATTEMPT': '1',
           'GITHUB_ACTOR': 'michaeldgreenphd', 'GITHUB_TRIGGERING_ACTOR': 'michaeldgreenphd', 'GITHUB_RUN_ID': '42',
           'GITHUB_SHA': head, 'GITHUB_EVENT_PATH': str(event)}
    return root, params, env, git


def test_ci_admission_uses_real_git_and_existing_budget_gate(ci_tree: tuple) -> None:
    root, params, env, git = ci_tree
    # The trigger writer records a short branch name; GITHUB_REF is fully qualified.
    assert ft.load_journal(root / ft.JOURNAL_RELPATH)[0]['ref'] == 'main'
    assert env['GITHUB_REF'] == 'refs/heads/main'
    result = ap.admit_ci(params, env, root)
    assert result['engine_commit'] == git('rev-parse', 'HEAD')
    assert result['budget_admission']['committed_upper_bound_usd'] == '1'
    assert result['journal_nonce'] == ai.NONCE


def test_ci_admission_still_rejects_another_execution_branch(ci_tree: tuple) -> None:
    root, params, env, _ = ci_tree
    env['GITHUB_REF'] = 'refs/heads/other'
    with pytest.raises(aa.AnnotationRefusal, match='ci_identity_refused'):
        ap.admit_ci(params, env, root)


@pytest.mark.parametrize('ci_tree', [True], indirect=True)
def test_recovery_admission_keeps_prior_hold_and_records_provenance(ci_tree: tuple) -> None:
    root, params, env, _ = ci_tree
    journal = (root / ft.JOURNAL_RELPATH).read_bytes()
    result = ap.admit_ci(params, env, root)
    assert result['journal_nonce'] == ap.RECOVERY_NONCE
    assert result['budget_admission']['held_upper_bound_usd'] == '1.0'
    assert Decimal(result['budget_admission']['committed_upper_bound_usd']) == 2
    assert result['recovery']['prior_failure']['workflow_run_id'] == '40320384841'
    assert result['recovery']['receipt_sha256'] == ap.RECOVERY_SHA256
    assert (root / ft.JOURNAL_RELPATH).read_bytes() == journal


@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'third', 'resolved', 'evicted', 'amount', 'nonce', 'order'])
def test_recovery_refuses_changed_or_additional_history(mutation: str) -> None:
    prior = copy.deepcopy(ap.recovery_receipt(ROOT)['prior_reservation'])
    current = {**prior, 'nonce': ap.RECOVERY_NONCE}
    entries = [prior, current]
    if mutation == 'missing':
        entries.pop(0)
    elif mutation in ('duplicate', 'third'):
        entries.append({**current, 'nonce': ap.RECOVERY_NONCE if mutation == 'duplicate' else 'another'})
    elif mutation == 'order':
        entries.reverse()
    else:
        key, value = {'resolved': ('resolved', True), 'evicted': ('evicted', True),
                      'amount': ('max_spend', 0), 'nonce': ('nonce', 'different')}[mutation]
        prior[key] = value
    with pytest.raises(aa.AnnotationRefusal, match='recovery_history_mismatch'):
        ap.campaign_identity(entries, ap.RECOVERY_NONCE, ROOT)


def test_recovery_receipt_tampering_is_refused(tmp_path: Path) -> None:
    write(tmp_path / ap.RECOVERY, {**ap.recovery_receipt(ROOT), 'max_spend_usd': '2.00'})
    with pytest.raises(aa.AnnotationRefusal, match='input_hash_mismatch'):
        ap.recovery_receipt(tmp_path)


@pytest.mark.parametrize('ci_tree', [True], indirect=True)
def test_recovery_cannot_reuse_original_or_enable_third_attempt(ci_tree: tuple) -> None:
    root, params, _, _ = ci_tree
    entries = ft.load_journal(root / ft.JOURNAL_RELPATH)
    assert ft.reused_nonce(ap.TRIGGER, params, entries)
    with pytest.raises(aa.AnnotationRefusal, match='campaign_already_reserved'):
        ap.campaign_identity(entries, ai.NONCE, root)
    assert ap.params_problems({**params, '_nonce': ap.RECOVERY_NONCE + '-again'}, root)


@pytest.mark.parametrize('ci_tree', ['low_budget'], indirect=True)
def test_recovery_does_not_relax_daily_budget(ci_tree: tuple, capsys: pytest.CaptureFixture) -> None:
    root, params, env, _ = ci_tree
    # Valid synthetic push with $1.99 available, versus $1 original + $1 new hold.
    with pytest.raises(aa.AnnotationRefusal, match='journal_or_daily_budget_refused'):
        ap.admit_ci(params, env, root)
    assert 'ceiling' in capsys.readouterr().err


@pytest.mark.parametrize('mutation', ['creation', 'parent', 'head', 'dirty', 'remote', 'code_change', 'replay'])
def test_ci_commit_replay_and_remote_binding(ci_tree: tuple, mutation: str) -> None:
    root, params, env, git = ci_tree
    event = aa.read_json(Path(env['GITHUB_EVENT_PATH']))
    if mutation == 'creation':
        event['created'] = True
    elif mutation == 'parent':
        event['before'] = 'b' * 40
    elif mutation == 'head':
        env['GITHUB_SHA'] = 'c' * 40
    elif mutation == 'dirty':
        (root / 'unrelated').write_text('change')
    elif mutation == 'remote':
        git('--git-dir', str(root.parent / 'remote.git'), 'update-ref', 'refs/heads/main', params['expected_commit'])
    elif mutation in ('code_change', 'replay'):
        if mutation == 'code_change':
            (root / 'new_code').write_text('unexpected')
            git('add', '.')
        git('commit', '--allow-empty', '-m', 'not a new reservation')
        env['GITHUB_SHA'] = git('rev-parse', 'HEAD')
        event['after'] = env['GITHUB_SHA']
        git('push', 'origin', 'HEAD:main')
    write(Path(env['GITHUB_EVENT_PATH']), event)
    with pytest.raises(aa.AnnotationRefusal):
        ap.admit_ci(params, env, root)


def quote_params() -> dict:
    return {**live_params(), 'plan_sha256': ap.QUOTE_CAMPAIGN_SHA256, '_nonce': ap.QUOTE_NONCE}


def test_quote_attempt_requires_exact_plan_nonce_pair_and_preserved_contracts(tmp_path: Path) -> None:
    assert not ap.params_problems(quote_params(), ROOT)
    assert ft.is_paid_fire(ap.TRIGGER, quote_params())
    assert ft.reused_nonce(ap.TRIGGER, quote_params(), [{'trigger': ap.TRIGGER, 'nonce': ap.QUOTE_NONCE}])
    for change in ({'_nonce': ai.NONCE}, {'_nonce': ap.RECOVERY_NONCE},
                   {'_nonce': ap.QUOTE_NONCE + '-again'}, {'plan_sha256': ai.PLAN_SHA256},
                   {'plan_sha256': aq.MANIFEST_SHA256}, {'max_spend': '0.01'}):
        assert ap.params_problems({**quote_params(), **change}, ROOT)
    assert ap.params_problems(quote_params(), tmp_path) == ['action_plan_or_price_unavailable']


@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'fourth', 'order', 'resolved', 'evicted', 'amount'])
def test_quote_attempt_refuses_altered_history(mutation: str) -> None:
    prior = copy.deepcopy(ap.quote_campaign(ROOT)['prior_reservations'])
    current = {**prior[-1], 'nonce': ap.QUOTE_NONCE}
    entries = [*prior, current]
    if mutation == 'missing':
        entries.pop(0)
    elif mutation in ('duplicate', 'fourth'):
        entries.append({**current, 'nonce': ap.QUOTE_NONCE if mutation == 'duplicate' else 'another'})
    elif mutation == 'order':
        entries[:2] = reversed(entries[:2])
    else:
        field, value = {'resolved': ('resolved', True), 'evicted': ('evicted', True), 'amount': ('max_spend', 0)}[mutation]
        entries[1][field] = value
    with pytest.raises(aa.AnnotationRefusal, match='quote_campaign_history_mismatch'):
        ap.campaign_identity(entries, ap.QUOTE_NONCE, ROOT)


@pytest.mark.parametrize('ci_tree', ['quotes'], indirect=True)
def test_quote_ci_admission_retains_both_holds_and_cost_receipt(ci_tree: tuple) -> None:
    root, params, env, _ = ci_tree
    before = (root / ft.JOURNAL_RELPATH).read_bytes()
    result = ap.admit_ci(params, env, root)
    assert result['journal_nonce'] == ap.QUOTE_NONCE
    assert result['quote_campaign']['receipt_sha256'] == ap.QUOTE_CAMPAIGN_SHA256
    assert [r['run_id'] for r in result['quote_campaign']['prior_attempts']] == ['40320384841', '40344924588']
    assert Decimal(result['budget_admission']['held_upper_bound_usd']) == 2
    assert Decimal(result['budget_admission']['committed_upper_bound_usd']) == Decimal('3.0002326')
    assert (root / ft.JOURNAL_RELPATH).read_bytes() == before
    # Free park history does not erase or change either paid attempt.
    entries = ft.load_journal(root / ft.JOURNAL_RELPATH)
    assert ap.campaign_identity([*entries, {'trigger': ap.TRIGGER, 'nonce': 'park'}], ap.QUOTE_NONCE, root)


@pytest.mark.parametrize('ci_tree', ['quotes_low_budget'], indirect=True)
def test_quote_attempt_keeps_existing_daily_ceiling(ci_tree: tuple) -> None:
    root, params, env, _ = ci_tree
    with pytest.raises(aa.AnnotationRefusal, match='journal_or_daily_budget_refused'):
        ap.admit_ci(params, env, root)


@pytest.mark.parametrize('ci_tree', ['quotes'], indirect=True)
@pytest.mark.parametrize('path', [ap.QUOTE_CAMPAIGN, 'scripts/action_quote_annotations.py',
                                 'data/action_annotations/runs/action_40344924588.report.json'])
def test_quote_contract_or_prior_receipt_tampering_refuses(ci_tree: tuple, path: Path | str) -> None:
    root, params, _, _ = ci_tree
    with (root / path).open('ab') as stream:
        stream.write(b' ')
    assert ap.params_problems(params, root) == ['action_plan_or_price_unavailable']


def test_quote_preparation_uses_frozen_request_bytes_and_new_plan(tmp_path: Path) -> None:
    prepared = aq.prepare(ROOT)
    packet = ap.prepare_campaign(ap.QUOTE_CAMPAIGN_SHA256, ROOT)
    assert packet['requests'] == prepared['requests']
    assert packet['prepared_inputs_sha256'] == aa.digest(aa.encoded(prepared))
    assert packet['plan_sha256'] == ap.QUOTE_CAMPAIGN_SHA256
    assert packet['preparation_sha256'] == aq.MANIFEST_SHA256
    assert packet['response_format'] == aq.FORMAT
    assert packet['owner_labels_sent'] is False and packet['seal_hits'] == 0
    assert packet == ap.prepare_campaign(ap.QUOTE_CAMPAIGN_SHA256, ROOT)
    assert ap.main(['prepare', '--plan-sha256', ap.QUOTE_CAMPAIGN_SHA256, '--out', str(tmp_path / 'prepared')]) == 0
    assert aa.read_json(tmp_path / 'prepared/inputs.json') == packet
    with pytest.raises(SystemExit):
        ap.main(['live', '--plan-sha256', ap.QUOTE_CAMPAIGN_SHA256, '--out', str(tmp_path / 'live')])
    assert not (tmp_path / 'live').exists()


@pytest.fixture
def quote_packet(packet: tuple) -> tuple:
    doc, replies = copy.deepcopy(packet)
    doc.update(plan_sha256=ap.QUOTE_CAMPAIGN_SHA256, response_format=aq.FORMAT,
               preparation_sha256=aq.MANIFEST_SHA256, prepared_inputs_sha256='fixture_only')
    for request in doc['requests']:
        request['response_format'] = aq.FORMAT
    for body in replies.values():
        annotation = json.loads(body['content'][0]['text'])
        annotation['schema_version'] = aq.FORMAT
        for action in annotation['actions']:
            for field in ('evidence', 'condition', 'timing'):
                if action[field] is not None:
                    action[field] = {'quote': action[field]['quote']}
        body['content'][0]['text'] = json.dumps(annotation)
    return doc, replies


def quote_identity() -> dict:
    return {'journal_nonce': ap.QUOTE_NONCE,
            'quote_campaign': {'receipt_sha256': ap.QUOTE_CAMPAIGN_SHA256}}


def test_quote_worker_runs_full_synthetic_pass_and_keeps_cost_contract(
    tmp_path: Path, quote_packet: tuple, price: dict,
) -> None:
    report, calls, counts = execute(tmp_path, quote_packet, price, identity_extra=quote_identity())
    assert len(calls) == len(counts) == 14 and not report['not_attempted']
    assert report['status'] == 'complete_semantics_unverified'
    assert report['schema_version'] == 'patientwords.action-pilot-report/1'
    assert report['plan_sha256'] == ap.QUOTE_CAMPAIGN_SHA256 and report['response_format'] == aq.FORMAT
    assert report['unknown_charge'] is False and report['cost_usd'] > 0
    assert report['inputs_sha256'] == aa.digest((tmp_path / 'result/inputs.json').read_bytes())
    for row in report['items']:
        interpreted = row['interpretation']
        assert interpreted['schema_version'] == 'patientwords.action-reply-interpretation/2'
        assert interpreted['annotation'] is not None
        assert interpreted['provider_annotation']['schema_version'] == aq.FORMAT
        assert interpreted['raw_body_sha256'] == row['capture']['raw_body_sha256']
    for path, sha in report['artifact_hashes'].items():
        assert aa.digest((tmp_path / 'result' / path).read_bytes()) == sha


@pytest.mark.parametrize('mutation', ['format', 'item_format', 'nonce', 'receipt', 'plan'])
def test_quote_worker_refuses_mixed_execution_before_any_call(
    tmp_path: Path, quote_packet: tuple, price: dict, mutation: str,
) -> None:
    identity = quote_identity()
    doc, _ = quote_packet
    if mutation == 'format':
        doc['response_format'] = 'patientwords.action-spans/1'
    elif mutation == 'item_format':
        doc['requests'][0].pop('response_format')
    elif mutation == 'nonce':
        identity['journal_nonce'] = ap.RECOVERY_NONCE
    elif mutation == 'receipt':
        identity['quote_campaign'] = {}
    else:
        doc['plan_sha256'] = ai.PLAN_SHA256
    with pytest.raises(aa.AnnotationRefusal, match='execution_binding_mismatch'):
        execute(tmp_path, quote_packet, price, identity_extra=identity)
    assert not (tmp_path / 'result').exists()


def test_quote_invalid_reply_stops_after_one_and_preserves_raw(
    tmp_path: Path, quote_packet: tuple, price: dict,
) -> None:
    for body in quote_packet[1].values():
        body['content'][0]['text'] = '{}'
    report, calls, counts = execute(tmp_path, quote_packet, price, identity_extra=quote_identity())
    assert len(calls) == 1 and len(counts) == 14 and len(report['not_attempted']) == 13
    assert report['status'] == 'stopped_incomplete' and report['cost_usd'] > 0
    assert report['items'][0]['interpretation']['annotation'] is None
    assert (tmp_path / 'result/action_annotation_attempts' / calls[0] / 'response.bin').is_file()


def test_live_cli_selects_quote_packet_before_constructing_transport(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, quote_packet: tuple, price: dict,
) -> None:
    params = quote_params()
    events = []
    class FakeTransport:
        def __init__(self, key: str):
            events.append('client')
        def __call__(self, wire: dict) -> at.Reply:
            return at.Reply(200, 'fixture_request', aa.encoded(quote_packet[1][aa.digest(aa.encoded(wire))]), True, None)
        def count(self, wire: dict) -> at.Reply:
            return at.Reply(200, 'fixture_count', b'{"input_tokens":1000}', True, None)
    def prepare(plan: str, root: Path) -> dict:
        assert plan == ap.QUOTE_CAMPAIGN_SHA256
        events.append('prepare')
        return quote_packet[0]
    # Patch only the CI/source boundary; the actual worker/capture/interpreter run.
    original_read = aa.read_json
    monkeypatch.setattr(ap, 'admit_ci', lambda *args: {'execution_day_utc': datetime.now(timezone.utc).date().isoformat(),
                        'inference': {'environment': 'synthetic_fixture'}, **quote_identity()})
    monkeypatch.setattr(ap, 'prepare_campaign', prepare)
    monkeypatch.setattr(ab, 'prices', lambda *args: price)
    monkeypatch.setattr(at, 'AnthropicTransport', FakeTransport)
    # Normalizer schema loads remain real; only the trigger is synthetic.
    monkeypatch.setattr(aa, 'read_json', lambda path: params if Path(path) == ap.ROOT / ap.TRIGGER_PATH
                        else original_read(path))
    assert ap.main(['live', '--out', str(tmp_path / 'result')]) == 0
    assert events == ['prepare', 'client']
    assert json.loads((tmp_path / 'result/report.json').read_text())['plan_sha256'] == ap.QUOTE_CAMPAIGN_SHA256

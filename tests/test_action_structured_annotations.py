"""Schema request and recorded wrapper regressions; no live provider or gold labels."""
from __future__ import annotations

import copy
from datetime import date
from decimal import Decimal
import json
from pathlib import Path

import pytest

from scripts import action_annotations as aa
from scripts import action_annotation_messages as messages
from scripts import action_annotation_transport as at
from scripts import action_pilot as pilot
from scripts import action_pilot_budget as budget
from scripts import action_quote_annotations as quotes
from scripts import action_structured_annotations as structured

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/action_annotations/structured_failure_regression.json'


def reply(text: str, stop: str = 'end_turn') -> at.Reply:
    return at.Reply(200, 'synthetic_request', aa.encoded({
        'id': 'synthetic_message', 'type': 'message', 'role': 'assistant', 'model': 'claude-haiku-5-5',
        'stop_reason': stop, 'stop_sequence': None, 'content': [{'type': 'text', 'text': text}],
        'usage': {'input_tokens': 1000, 'output_tokens': 100}}), True, None)


def interpret(raw: at.Reply, source: str) -> dict:
    return messages.interpret_reply(raw, expected_model='claude-haiku-5-5', source_text=source,
                                    response_format=quotes.FORMAT)


def test_recorded_wrapper_remains_rejected_bare_fixture_is_not_a_repaired_result() -> None:
    fixture = aa.read_json(FIXTURE)
    assert fixture['artifact_kind'] == 'regression_fixture_not_repaired_result'
    assert aa.digest(fixture['original_text_block'].encode()) == fixture['original_text_sha256']
    wrapped = reply(fixture['original_text_block'])
    original = interpret(wrapped, fixture['source'])
    assert original['status'] == 'invalid_annotation' and original['annotation'] is None
    assert original['raw_body_sha256'] == aa.digest(wrapped.body)
    bare = interpret(reply(json.dumps(fixture['synthetic_bare_object'])), fixture['source'])
    assert bare['status'] == 'validated_semantics_unverified'
    action, = bare['annotation']['actions']
    assert action['evidence'] == {'start': 2, 'end': 34, 'quote': fixture['synthetic_bare_object'][
        'actions'][0]['evidence']['quote']}
    assert action['timing']['start'] == 28 and action['timing']['end'] == 33
    assert action['condition'] is None
    assert original['usage'] == bare['usage']
    prices = budget.prices(ROOT, date(2026, 10, 27))
    assert budget.usage_cost(original['usage'], prices) == Decimal('0.00015')


@pytest.mark.parametrize('stop,status', [('refusal', 'provider_refusal'), ('max_tokens', 'truncated')])
def test_structured_contract_does_not_turn_stop_reasons_into_labels(stop: str, status: str) -> None:
    fixture = aa.read_json(FIXTURE)
    result = interpret(reply(json.dumps(fixture['synthetic_bare_object']), stop), fixture['source'])
    assert result['status'] == status and result['annotation'] is None
    assert result['usage']['output_tokens'] == 100  # refusals/truncation do not erase charges


@pytest.mark.parametrize('change', ['missing_nullable', 'unknown_label', 'unquoted', 'duplicate', 'wrong_version'])
def test_provider_shaped_object_still_must_pass_unchanged_local_rules(change: str) -> None:
    fixture = aa.read_json(FIXTURE)
    value = fixture['synthetic_bare_object']
    if change == 'missing_nullable':
        value['actions'][0].pop('condition')
    elif change == 'unknown_label':
        value['actions'][0]['category'] = 'invented'
    elif change == 'unquoted':
        value['actions'][0]['evidence']['quote'] = 'not in the source'
    elif change == 'wrong_version':
        value['schema_version'] = 'invented'
    else:
        value['actions'].append(copy.deepcopy(value['actions'][0]))
    result = interpret(reply(json.dumps(value)), fixture['source'])
    assert result['status'] == 'invalid_annotation' and result['annotation'] is None


def test_preparation_is_deterministic_same_sources_and_only_format_changes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail('preparation constructed a provider connection')

    monkeypatch.setattr(at.http.client, 'HTTPSConnection', forbidden)
    old = quotes.prepare(ROOT)
    saved = aa.encoded(old)
    new = structured.prepare(ROOT)
    assert new == structured.prepare(ROOT)
    assert aa.encoded(old) == saved
    assert new['execution_enabled'] is False and new['model_calls'] == 0
    assert new['owner_labels_sent'] is False and new['seal_hits'] == 0
    assert new['response_format'] == quotes.FORMAT and new['request_format'] == at.STRUCTURED_FORMAT
    assert len(new['requests']) == 14
    assert new['preparation']['request_hashes'] == {r['source_id']: r['request_sha256'] for r in new['requests']}
    for previous, current in zip(old['requests'], new['requests']):
        restored = copy.deepcopy(current)
        del restored['wire']['body']['output_config']['format']
        del restored['request_format']
        assert current['request_sha256'] != previous['request_sha256']
        restored['request_sha256'] = previous['request_sha256']
        assert restored == previous  # source, origin, system, joins, model/settings unchanged
        assert current['wire']['body']['output_config']['format']['schema'] == aa.read_json(ROOT / quotes.SCHEMA)
    assert structured.main(['--out', str(tmp_path / 'prepared')]) == 0
    assert aa.read_json(tmp_path / 'prepared/inputs.json') == new
    assert structured.main(['--out', str(tmp_path / 'prepared')]) == 2
    # Neither the new hash nor the candidate packet is an executable campaign.
    params = {'mode': 'run', 'plan_sha256': structured.MANIFEST_SHA256, 'max_spend': '1.00',
              'expected_commit': '0' * 40, '_nonce': pilot.QUOTE_NONCE}
    assert pilot.params_problems(params, ROOT) == ['action_fixed_plan_and_nonce_required']
    with pytest.raises(aa.AnnotationRefusal, match='unknown_campaign_plan'):
        pilot.prepare_campaign(structured.MANIFEST_SHA256, ROOT)


@pytest.mark.parametrize('target', [structured.MANIFEST, quotes.SCHEMA, 'scripts/action_annotation_transport.py'])
def test_changed_contract_refuses_before_source_preparation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str | Path,
) -> None:
    manifest = aa.read_json(ROOT / structured.MANIFEST)
    for relative in [str(structured.MANIFEST), *manifest['contract_files']]:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / relative).read_bytes())
    with (tmp_path / target).open('ab') as stream:
        stream.write(b' ')

    def forbidden(root: Path) -> None:
        pytest.fail('source loading before contract admission')

    monkeypatch.setattr(quotes, 'prepare', forbidden)
    with pytest.raises(aa.AnnotationRefusal, match='input_hash_mismatch'):
        structured.prepare(tmp_path)

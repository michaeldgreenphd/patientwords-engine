"""Quote binding regressions; synthetic replies only, no provider/model calls."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts import action_annotations as aa
from scripts import action_annotation_messages as messages
from scripts import action_annotation_transport as transport
from scripts import action_pilot_inputs as inputs
from scripts import action_pilot as pilot
from scripts import action_quote_annotations as quotes

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/action_annotations/quote_failure_regression.json'


def proposal(evidence: str, *, condition: str | None = None, timing: str | None = None) -> dict:
    return {'schema_version': quotes.FORMAT, 'status': 'annotated', 'reason': None, 'actions': [{
        'category': 'other_action', 'stance': 'recommended', 'actor': 'reader',
        'evidence': {'quote': evidence}, 'condition': None if condition is None else {'quote': condition},
        'timing': None if timing is None else {'quote': timing}}]}


def provider_reply(annotation: dict) -> transport.Reply:
    body = {'type': 'message', 'role': 'assistant', 'id': 'synthetic_message', 'model': 'synthetic_model',
            'stop_reason': 'end_turn', 'stop_sequence': None, 'usage': {'input_tokens': 100, 'output_tokens': 30},
            'content': [{'type': 'text', 'text': json.dumps(annotation)}]}
    return transport.Reply(200, 'synthetic_request', aa.encoded(body), True, None)


def test_captured_failure_stays_invalid_and_synthetic_quote_variant_binds() -> None:
    fixture = aa.read_json(FIXTURE)
    with pytest.raises(aa.AnnotationRefusal, match='evidence_span_mismatch'):
        aa.validate_annotation(fixture['legacy_annotation'], fixture['source'])
    original = copy.deepcopy(fixture['quote_response_fixture'])
    normalized = quotes.normalize(original, fixture['source'])
    assert original == fixture['quote_response_fixture']
    action, = normalized['actions']
    assert (action['evidence']['start'], action['evidence']['end']) == (0, 55)
    assert (action['condition']['start'], action['condition']['end']) == (26, 54)
    assert action['stance'] == 'discouraged' and action['timing'] is None
    aa.validate_annotation(normalized, fixture['source'])


def test_new_format_is_explicit_and_legacy_reply_bytes_are_not_repaired() -> None:
    text = 'Do alpha after beta.'
    annotation = proposal(text, timing='after beta')
    raw = provider_reply(annotation)
    before = raw.body
    old = messages.interpret_reply(raw, expected_model='synthetic_model', source_text=text)
    new = messages.interpret_reply(raw, expected_model='synthetic_model', source_text=text,
                                   response_format=quotes.FORMAT)
    assert old['status'] == 'invalid_annotation' and old['schema_version'].endswith('/1')
    assert new['status'] == 'validated_semantics_unverified' and new['schema_version'].endswith('/2')
    assert new['provider_annotation'] == annotation
    assert new['annotation'] == quotes.normalize(annotation, text)
    assert new['normalization']['implementation_sha256'] == aa.digest(Path(quotes.__file__).read_bytes())
    assert new['raw_body_sha256'] == aa.digest(before) and raw.body == before
    assert new['cost_usd'] is None and not new['reservation_release_allowed']
    assert new['source_binding'] == 'caller_asserted_not_admitted'
    fixture = aa.read_json(FIXTURE)
    invalid = messages.interpret_reply(provider_reply(fixture['legacy_annotation']),
        expected_model='synthetic_model', source_text=fixture['source'], response_format=quotes.FORMAT)
    assert invalid['status'] == 'invalid_annotation' and invalid['annotation'] is None
    with pytest.raises(aa.AnnotationRefusal, match='unsupported_response_format'):
        messages.interpret_reply(raw, expected_model='synthetic_model', source_text=text,
                                 response_format='future_format')


@pytest.mark.parametrize('text,quote,reason', [
    ('alpha', 'missing', 'quote_not_found'), ('alpha alpha', 'alpha', 'ambiguous_quote'),
    ('aaaa', 'aaa', 'ambiguous_quote'), ('alpha', ' ', 'empty_quote'),
    ('alpha', 'Alpha', 'quote_not_found'), ('a  b', 'a b', 'quote_not_found'),
    ('e\u0301', '\u00e9', 'quote_not_found'),
])
def test_no_guessing_normalization_or_overlapping_first_match(text: str, quote: str, reason: str) -> None:
    with pytest.raises(aa.AnnotationRefusal, match=reason):
        quotes.normalize(proposal(quote), text)


def test_unicode_codepoints_nested_context_and_input_immutability() -> None:
    text = 'β elsewhere. 🧪 Do α\nif β. β elsewhere.'
    value = proposal('🧪 Do α\nif β.', condition='β', timing='α\n')
    saved = copy.deepcopy(value)
    result = quotes.normalize(value, text)
    assert value == saved
    action = result['actions'][0]
    assert action['evidence']['start'] == 13 and action['evidence']['end'] == 25
    assert action['condition'] == {'start': 23, 'end': 24, 'quote': 'β'}
    assert action['timing'] == {'start': 18, 'end': 20, 'quote': 'α\n'}


@pytest.mark.parametrize('field', ['condition', 'timing'])
def test_nested_match_must_be_unique_within_evidence(field: str) -> None:
    for quote, error in [('alpha', 'ambiguous_quote'), ('outside', 'quote_not_found')]:
        value = proposal('alpha alpha')
        value['actions'][0][field] = {'quote': quote}
        with pytest.raises(aa.AnnotationRefusal, match=error):
            quotes.normalize(value, 'outside. alpha alpha')


@pytest.mark.parametrize('change', ['missing_timing', 'offset', 'null_evidence', 'wrong_version', 'extra', 'numeric'])
def test_schema_before_defaults_coercion_or_binding(change: str) -> None:
    value = proposal('alpha')
    if change == 'missing_timing':
        value['actions'][0].pop('timing')
    elif change == 'offset':
        value['actions'][0]['evidence']['start'] = 0
    elif change == 'null_evidence':
        value['actions'][0]['evidence'] = None
    elif change == 'wrong_version':
        value['schema_version'] = 'other'
    elif change == 'extra':
        value['extra'] = False
    else:
        value['actions'][0]['evidence']['quote'] = 1
    with pytest.raises(aa.AnnotationRefusal, match='quote_schema'):
        quotes.normalize(value, 'alpha')


@pytest.mark.parametrize('change,reason', [('stance', 'unknown_stance'), ('conditional', 'conditional_without_condition'),
                                        ('duplicate', 'duplicate_action')])
def test_all_existing_semantic_constraints_remain(change: str, reason: str) -> None:
    value = proposal('alpha')
    if change == 'duplicate':
        value['actions'].append(copy.deepcopy(value['actions'][0]))
    else:
        value['actions'][0]['stance'] = 'unknown' if change == 'stance' else 'conditional'
    with pytest.raises(aa.AnnotationRefusal, match=reason):
        quotes.normalize(value, 'alpha')


@pytest.mark.parametrize('status,reason', [('no_actions', None), ('uncertain', 'Cannot parse this source.')])
def test_empty_and_uncertain_states_remain_distinct(status: str, reason: str | None) -> None:
    value = {'schema_version': quotes.FORMAT, 'status': status, 'actions': [], 'reason': reason}
    assert quotes.normalize(value, 'alpha') == {'status': status, 'actions': [], 'reason': reason}


def test_invalid_response_keeps_raw_and_provider_proposal() -> None:
    value = proposal('alpha')
    raw = provider_reply(value)
    result = messages.interpret_reply(raw, expected_model='synthetic_model', source_text='alpha alpha',
                                      response_format=quotes.FORMAT)
    assert result['status'] == 'invalid_annotation' and result['refusal'] == 'ambiguous_quote'
    assert result['provider_annotation'] == value and result['annotation'] is None
    assert result['raw_body_sha256'] == aa.digest(raw.body)


@pytest.mark.parametrize('kind,expected', [('partial', 'transport_incomplete'), ('wrong_model', 'model_mismatch'),
    ('truncated', 'truncated'), ('no_request_id', 'missing_request_id'), ('http', 'http_error'),
    ('duplicate_json', 'invalid_annotation'), ('missing_usage', 'invalid_or_missing_usage')])
def test_quote_mode_keeps_existing_message_refusals(kind: str, expected: str) -> None:
    raw = provider_reply(proposal('alpha'))
    body = json.loads(raw.body)
    if kind == 'wrong_model':
        body['model'] = 'another_model'
    elif kind == 'truncated':
        body['stop_reason'] = 'max_tokens'
    elif kind == 'missing_usage':
        body.pop('usage')
    elif kind == 'duplicate_json':
        body['content'][0]['text'] = '{"status":"annotated","status":"no_actions"}'
    reply = transport.Reply(429 if kind == 'http' else 200, None if kind == 'no_request_id' else raw.request_id,
                            aa.encoded(body), kind != 'partial', 'timeout' if kind == 'partial' else None)
    result = messages.interpret_reply(reply, expected_model='synthetic_model', source_text='alpha',
                                      response_format=quotes.FORMAT)
    assert result['status'] == expected and result['annotation'] is None
    assert result['raw_body_sha256'] == aa.digest(reply.body)


@pytest.mark.parametrize('path', [quotes.MANIFEST, quotes.SCHEMA, quotes.RUBRIC])
def test_changed_manifest_or_contract_refuses_before_source_loading(tmp_path: Path, path: Path) -> None:
    manifest = aa.read_json(ROOT / quotes.MANIFEST)
    for relative in [quotes.MANIFEST, *map(Path, manifest['contract_files'])]:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    with (tmp_path / path).open('ab') as stream:
        stream.write(b' ')
    with pytest.raises(aa.AnnotationRefusal, match='input_hash_mismatch'):
        quotes.prepare(tmp_path)


def test_preparation_same_sources_new_frozen_requests_no_live_admission(tmp_path: Path) -> None:
    old = inputs.prepare(ROOT)
    before = aa.encoded(old)
    new = quotes.prepare(ROOT)
    assert aa.encoded(old) == before
    assert new['model_calls'] == 0 and new['execution_enabled'] is False
    assert new['owner_labels_sent'] is False and new['seal_hits'] == 0
    assert len(new['requests']) == 14
    for prior, current in zip(old['requests'], new['requests']):
        for key in ('source_id', 'source_sha256', 'text', 'origin'):
            assert current[key] == prior[key]
        assert current['request_sha256'] != prior['request_sha256']
        assert current['wire']['body']['messages'] == prior['wire']['body']['messages']
        assert current['wire']['body']['model'] == prior['wire']['body']['model']
    assert new == quotes.prepare(ROOT)
    # New manifest is not accepted as a campaign plan, even with an old known nonce.
    params = {'mode': 'run', 'plan_sha256': quotes.MANIFEST_SHA256, 'max_spend': '1.00',
              'expected_commit': '0' * 40, '_nonce': pilot.RECOVERY_NONCE}
    assert pilot.params_problems(params, ROOT) == ['action_fixed_plan_and_nonce_required']
    assert quotes.main(['--out', str(tmp_path / 'prepared')]) == 0
    assert json.loads((tmp_path / 'prepared/inputs.json').read_text()) == new
    assert quotes.main(['--out', str(tmp_path / 'prepared')]) == 2


def test_only_span_instruction_and_version_change_in_rubric() -> None:
    old = aa.read_json(aa.CONTRACT / 'rubric.v1.json')
    new = aa.read_json(ROOT / quotes.RUBRIC)
    assert old['instructions'][2] != new['instructions'][2]
    new['instructions'][2] = old['instructions'][2]
    new['version'] = old['version']
    assert new == old

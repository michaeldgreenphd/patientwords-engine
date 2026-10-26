"""Frozen source admission for one assisted pass; no send, label repair or sampling."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts import action_annotations as aa
from scripts import action_annotation_transport as transport

PLAN = Path('data/action_annotations/assisted_pass.v1.json')
PLAN_SHA256 = '419afe0f304cea83001a95bfbb73ccb54cef72c7205c4a4e2083f06cc48a8a44'
PRICE = Path('data/action_annotations/price.v1.json')
PRICE_SHA256 = '14f0e8302747fb7622d9ebb4ffb5ce3dedd855e9fba7318f45a1b2cfc7c3a0f6'
NONCE = 'assisted-actions-20261025'


def require(condition: bool, reason: str) -> None:
    """Fail closed with a stable, non-content-bearing refusal."""
    if not condition:
        raise aa.AnnotationRefusal(reason)


def verified_bytes(root: Path, name: str | Path, expected: str) -> bytes:
    """Bind all source bytes to a reviewed manifest; reject symlinks outside root."""
    path = (root / name).resolve(strict=True)
    require(path.is_relative_to(root.resolve()), 'input_outside_engine')
    raw = path.read_bytes()
    require(aa.digest(raw) == expected, 'input_hash_mismatch')
    return raw


def parse(raw: bytes) -> Any:
    """Strict JSON, including duplicate members and overflowed numeric values."""
    value = json.loads(raw, object_pairs_hook=aa._pairs, parse_constant=aa._constant)
    aa.encoded(value)
    return value


def prepare(root: Path) -> dict[str, Any]:
    """Admit the fixed 10+4 sources with true origins; construct blinded requests.

    Source selection and request hashes were frozen before inference. Grouping
    identifiers are provisional joins, not independently established families.
    The earlier synthetic-only CLI remains unchanged.
    """
    from scripts import advice_eval as ae
    from scripts import seal_check as sc
    from scripts import tierb_split as tb

    plan = parse(verified_bytes(root, PLAN, PLAN_SHA256))
    contracts = {p: parse(verified_bytes(root, p, h)) for p, h in plan['contract_files'].items()}
    files = plan['source_files']
    source_path, = [p for p in files if p.endswith('.json') and not p.endswith('.report.json')]
    archive_path, = [p for p in files if p.endswith('.jsonl')]
    report_path, = [p for p in files if p.endswith('.report.json')]
    stimuli = parse(verified_bytes(root, source_path, files[source_path]))
    report = parse(verified_bytes(root, report_path, files[report_path]))
    rows = [parse(line) for line in verified_bytes(root, archive_path, files[archive_path]).splitlines() if line.strip()]
    require(ae.verify_chain(rows)[0], 'archive_chain_invalid')
    require(rows[-1]['record_sha256'] == report['chain_head'] == plan['archive_chain_head'], 'chain_head_mismatch')
    require(len(rows) == report['records_total'], 'archive_count_mismatch')
    require(ae.sha256_text(ae.canonical_json(stimuli)) == plan['stimuli_canonical_sha256'], 'stimuli_hash_mismatch')
    by_id = {row['id']: row for row in stimuli['items']}
    require(len(by_id) == len(stimuli['items']), 'duplicate_stimulus_id')
    registry = sc.sealed_registry(str(root / 'data/simulated'), str(root / 'ops/dashboard.json'))
    require(bool(registry), 'empty_seal_registry')
    start = tb.tierb_start_stamp(root / 'ops/dashboard.json')
    require(bool(start), 'missing_seal_start')

    def unsealed(value: Any) -> None:
        require(not sc.scan_text(json.dumps(value), registry, suffix='.json')[0], 'sealed_input')

    fixture = contracts['tests/fixtures/action_annotations/sources.json']
    items = [dict(item, origin='authored_synthetic_challenge') for item in aa.sources(fixture)]
    require([i['source_id'] for i in items] == plan['synthetic_ids'], 'synthetic_coverage')
    for selected in plan['responses']:
        row = rows[selected['archive_line_1based'] - 1]
        require(row['record_type'] == 'advice', 'unexpected_record_type')
        require(row['record_sha256'] == selected['record_sha256'], 'selected_record_mismatch')
        for field in ('arm', 'model_requested', 'sample_k'):
            require(row[field] == selected[field], 'selected_join_mismatch')
        require(row['stimulus_id'] == selected['source_id'], 'selected_source_mismatch')
        require(row['stimuli_sha256'] == plan['stimuli_canonical_sha256'], 'record_stimuli_mismatch')
        text = row['response_text']
        require(aa.digest(text.encode()) == row['response_sha256'] == selected['response_sha256'],
                'response_hash_mismatch')
        item = by_id[row['stimulus_id']]
        ae._selection_seal_check('assisted_admission', Path(source_path).name, item, tb, start,
                                 root / 'ops/dashboard.json', root / 'data/simulated')
        unsealed(item)
        items.append({'source_id': selected['review_id'], 'text': text, 'source_sha256': row['response_sha256'],
                      'origin': 'archived_generated_response', 'archive_join': selected})
    system = json.dumps(contracts['data/action_annotations/rubric.v1.json'], ensure_ascii=False, sort_keys=True)
    system += '\n' + contracts['data/action_annotations/messages_protocol.v1.json']['format_instruction'] + '\n'
    system += aa.encoded(contracts['data/action_annotations/annotation.v1.schema.json']).decode()
    requests = []
    for item in items:
        unsealed(item)
        wire = transport.prepare_wire(system, json.dumps({'response': item['text']}, ensure_ascii=False))
        unsealed(wire)
        request_hash = aa.digest(aa.encoded(wire))
        require(request_hash == plan['request_hashes'][item['source_id']], 'frozen_request_mismatch')
        requests.append({**item, 'wire': wire, 'request_sha256': request_hash})
    require(len(requests) == len({r['request_sha256'] for r in requests}) == 14, 'request_coverage')
    return {'schema_version': 'patientwords.action-pilot-inputs/1', 'plan_sha256': PLAN_SHA256,
            'plan': plan, 'requests': requests, 'seal_registry_count': len(registry), 'seal_hits': 0,
            'purpose': 'assistance_not_independent_accuracy', 'owner_labels_sent': False}

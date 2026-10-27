"""Quote-only provider contract and offline preparation; no live admission or send."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from scripts import action_annotations as aa
from scripts import action_pilot_inputs as inputs
from scripts import action_annotation_transport as transport
from scripts.frontend_contract_schema import check_schema_subset

FORMAT = 'patientwords.action-quotes/1'
SCHEMA = Path('data/action_annotations/annotation_quotes.v1.schema.json')
RUBRIC = Path('data/action_annotations/rubric_quotes.v1.json')
MANIFEST = Path('data/action_annotations/quote_preparation.v1.json')
MANIFEST_SHA256 = '0cdb60c382868c4e3421a3d31df2a13910a7f7423cf142053b49dbd8a5c4804c'


def _locate(quote: str, text: str, offset: int = 0) -> dict[str, Any]:
    """Require exactly one literal occurrence, counting overlapping matches too."""
    if not quote.strip():
        raise aa.AnnotationRefusal('empty_quote')
    start = text.find(quote)
    if start < 0:
        raise aa.AnnotationRefusal('quote_not_found')
    if text.find(quote, start + 1) >= 0:
        raise aa.AnnotationRefusal('ambiguous_quote')
    return {'start': offset + start, 'end': offset + start + len(quote), 'quote': quote}


def normalize(annotation: Any, source_text: str) -> dict[str, Any]:
    """Derive code-point offsets, then apply every unchanged normalized-v1 rule.

    Evidence is unique across the source. Timing/condition are unique within the
    selected evidence, which already identifies their context. No normalization,
    fuzzy matching, first-match guess, quote expansion or legacy-offset repair.
    Structural validity and exact locations do not establish semantic correctness.
    """
    if not isinstance(source_text, str) or not source_text.strip():
        raise aa.AnnotationRefusal('source_text_required')
    aa.encoded(annotation)  # Refuse nonfinite values / invalid Unicode before schema traversal.
    source_text.encode('utf-8')
    schema = aa.read_json(aa.ROOT / SCHEMA)
    errors: list[str] = []
    check_schema_subset(lambda artifact, path, message: errors.append(f'{path}: {message}'),
                        'quote_annotation', annotation, schema)
    if errors:
        raise aa.AnnotationRefusal('quote_schema: ' + '; '.join(errors))
    if annotation['schema_version'] != FORMAT:
        raise aa.AnnotationRefusal('quote_schema_version')
    result = copy.deepcopy(annotation)
    result.pop('schema_version')
    for action in result['actions']:
        evidence = _locate(action['evidence']['quote'], source_text)
        action['evidence'] = evidence
        for field in ('timing', 'condition'):
            if action[field] is not None:
                action[field] = _locate(action[field]['quote'], evidence['quote'], evidence['start'])
    aa.validate_annotation(result, source_text)
    return result


def _requests(packet: dict[str, Any], root: Path) -> list[dict[str, Any]]:
    rubric = aa.read_json(root / RUBRIC)
    protocol = aa.read_json(root / 'data/action_annotations/messages_protocol.v1.json')
    schema = aa.read_json(root / SCHEMA)
    system = json.dumps(rubric, ensure_ascii=False, sort_keys=True)
    system += '\n' + protocol['format_instruction'] + '\n' + aa.encoded(schema).decode()
    requests = []
    for source in packet['requests']:
        wire = transport.prepare_wire(system, json.dumps({'response': source['text']}, ensure_ascii=False))
        requests.append({**source, 'wire': wire, 'request_sha256': aa.digest(aa.encoded(wire)),
                         'response_format': FORMAT})
    return requests


def prepare(root: Path = aa.ROOT) -> dict[str, Any]:
    """Re-admit the same 14 sources; freeze new requests without enabling execution."""
    manifest = inputs.parse(inputs.verified_bytes(root, MANIFEST, MANIFEST_SHA256))
    inputs.require(manifest['prior_plan_sha256'] == inputs.PLAN_SHA256, 'prior_plan_mismatch')
    for path, expected in manifest['contract_files'].items():
        inputs.verified_bytes(root, path, expected)
    packet = inputs.prepare(root)  # Existing source hashes/joins and current holdout-seal checks.
    requests = _requests(packet, root)
    inputs.require({r['source_id']: r['request_sha256'] for r in requests} == manifest['request_hashes'],
                   'quote_request_mismatch')
    # Recheck the changed wire bytes too; old prepare only checked the old request.
    from scripts import seal_check as sc
    registry = sc.sealed_registry(str(root / 'data/simulated'), str(root / 'ops/dashboard.json'))
    inputs.require(bool(registry), 'empty_seal_registry')
    for request in requests:
        inputs.require(not sc.scan_text(json.dumps(request['wire']), registry, suffix='.json')[0], 'sealed_input')
    return {'schema_version': 'patientwords.action-quote-inputs/1',
            'status': 'offline_candidate_not_admitted', 'model_calls': 0, 'execution_enabled': False,
            'prior_plan_sha256': inputs.PLAN_SHA256, 'preparation_sha256': MANIFEST_SHA256,
            'preparation': manifest, 'requests': requests, 'response_format': FORMAT,
            'seal_hits': 0, 'seal_registry_count': len(registry), 'owner_labels_sent': False,
            'purpose': 'assistance_not_independent_accuracy'}


def main(argv: list[str] | None = None) -> int:
    """Write a new external candidate packet only; no live mode exists here."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args(argv)
    from scripts.action_pilot import output_path
    try:
        out = output_path(args.out)
        packet = prepare()
        out.mkdir(exist_ok=False)
        transport._write(out / 'inputs.json', aa.encoded(packet))
    except (OSError, ValueError, KeyError) as exc:
        print('REFUSED: quote preparation failed (' + type(exc).__name__ + ')')
        return 2
    print('Prepared 14 quote-only requests offline; live admission remains disabled.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

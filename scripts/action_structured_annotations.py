"""Frozen structured-JSON quote preparation only; no live campaign or provider call."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts import action_annotations as aa
from scripts import action_annotation_transport as transport
from scripts import action_pilot_inputs as inputs
from scripts import action_quote_annotations as quotes

MANIFEST = Path('data/action_annotations/structured_preparation.v1.json')
MANIFEST_SHA256 = 'cc1e9f1d6f9c4cd6927c49bcb6b014ab59133ddad8c3ad5e2e6f344f367d02f7'


def prepare(root: Path = aa.ROOT) -> dict[str, Any]:
    """Re-admit the old sources, adding only the explicit provider output format.

    The historical preparation/normalized schema and failure remain untouched.
    New request hashes cannot be submitted under any previously admitted plan.
    """
    manifest = inputs.parse(inputs.verified_bytes(root, MANIFEST, MANIFEST_SHA256))
    inputs.require(manifest['prior_preparation_sha256'] == quotes.MANIFEST_SHA256 and
                   manifest['request_format'] == transport.STRUCTURED_FORMAT, 'structured_preparation_identity')
    for path, expected in manifest['contract_files'].items():
        inputs.verified_bytes(root, path, expected)
    prior = quotes.prepare(root)
    requests = []
    for source in prior['requests']:
        body = source['wire']['body']
        wire = transport.prepare_wire(body['system'], body['messages'][0]['content'][0]['text'],
                                      output_format=transport.STRUCTURED_FORMAT)
        requests.append({**source, 'wire': wire, 'request_sha256': aa.digest(aa.encoded(wire)),
                         'request_format': transport.STRUCTURED_FORMAT})
    inputs.require({r['source_id']: r['request_sha256'] for r in requests} == manifest['request_hashes'],
                   'structured_request_mismatch')
    from scripts import seal_check as sc
    registry = sc.sealed_registry(str(root / 'data/simulated'), str(root / 'ops/dashboard.json'))
    inputs.require(bool(registry), 'empty_seal_registry')
    for request in requests:
        inputs.require(not sc.scan_text(json.dumps(request['wire']), registry, suffix='.json')[0], 'sealed_input')
    return {'schema_version': 'patientwords.action-structured-inputs/1',
            'status': 'offline_candidate_not_admitted', 'model_calls': 0, 'execution_enabled': False,
            'preparation_sha256': MANIFEST_SHA256, 'preparation': manifest,
            'prior_prepared_inputs_sha256': aa.digest(aa.encoded(prior)),
            'requests': requests, 'request_format': transport.STRUCTURED_FORMAT,
            'response_format': quotes.FORMAT, 'seal_hits': 0, 'seal_registry_count': len(registry),
            'owner_labels_sent': False, 'purpose': 'assistance_not_independent_accuracy'}


def main(argv: list[str] | None = None) -> int:
    """Write a new external packet; deliberately provides no live mode."""
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
        print('REFUSED: structured preparation failed (' + type(exc).__name__ + ')')
        return 2
    print('Prepared 14 structured-JSON requests offline; live admission remains disabled.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

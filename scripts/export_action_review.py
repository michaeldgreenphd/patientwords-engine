"""Prepare separate private clinical/extraction previews from a landed CI artifact.

No calls, invented annotations, rating import, public export or change to the
original verification instrument. Partial runs retain explicit coverage states.
"""
from __future__ import annotations

import argparse
import copy
from pathlib import Path
import re
from typing import Any

from scripts import action_annotations as aa
from scripts import action_pilot_inputs as inputs
from scripts import action_annotation_transport as transport
from scripts.action_annotation_messages import interpret_reply

SCHEMA = 'patientwords-evidence-review/1'
SEED = 20261028


def artifact_file(folder: Path, relative: str, expected: str) -> bytes:
    """Refuse changed bytes and paths escaping the supplied artifact directory."""
    path = (folder / relative).resolve(strict=True)
    inputs.require(path.is_relative_to(folder.resolve()), 'artifact_path_escape')
    raw = path.read_bytes()
    inputs.require(aa.digest(raw) == expected, 'artifact_hash_mismatch')
    return raw


def load_run(folder: Path, run_id: str, root: Path) -> tuple[dict, dict, dict]:
    """Bind raw responses to the landed sidecar and re-admitted frozen sources."""
    inputs.require(bool(re.fullmatch('[1-9][0-9]*', run_id)), 'run_id_invalid')
    sidecar = aa.read_json(root / f'data/action_annotations/runs/action_{run_id}.report.json')
    report = inputs.parse(artifact_file(folder, 'report.json', sidecar['artifact_report_sha256']))
    inputs.require(report['workflow_run_id'] == run_id and
                   report['inference'] == {'environment': 'github_actions'}, 'ci_report_required')
    inputs.require({k: v for k, v in report.items() if k != 'items'} ==
                   {k: v for k, v in sidecar.items() if k != 'artifact_report_sha256'}, 'sidecar_mismatch')
    for name, digest in report['artifact_hashes'].items():
        artifact_file(folder, name, digest)
    packet = inputs.parse(artifact_file(folder, 'inputs.json', report['inputs_sha256']))
    frozen = inputs.prepare(root)  # Full source-chain, exact joins and current seal checks.
    current = packet['requests']
    inputs.require(len(current) == len(frozen['requests']), 'source_coverage_mismatch')
    for row, original in zip(current, frozen['requests']):
        for key in ('source_id', 'text', 'source_sha256', 'origin', 'archive_join'):
            inputs.require(row.get(key) == original.get(key), 'source_join_mismatch')
        inputs.require(aa.digest(aa.encoded(row['wire'])) == row['request_sha256'], 'wire_hash_mismatch')
    by_id = {r['source_id']: r for r in current}
    states = {key: {'state': 'not_attempted', 'annotation': None} for key in by_id}
    seen = set()
    for item in report['items']:
        key = item['source_id']
        inputs.require(key in by_id and key not in seen, 'attempt_coverage_mismatch')
        seen.add(key)
        source = by_id[key]
        capture = item['capture']
        inputs.require(capture['source_sha256'] == source['source_sha256'] and
                       capture['request_sha256'] == source['request_sha256'], 'attempt_source_mismatch')
        name = 'action_annotation_attempts/' + source['request_sha256'] + '/response.bin'
        raw = artifact_file(folder, name, capture['raw_body_sha256'])
        reply = transport.Reply(capture['http_status'], capture['request_id'], raw,
                                capture['body_complete'], capture['transport_error'])
        parsed = interpret_reply(reply, expected_model=report['model'], source_text=source['text'],
                                 response_format=report['response_format'])
        inputs.require(parsed == item['interpretation'], 'replay_mismatch')
        states[key] = {'state': parsed['status'], 'annotation': parsed['annotation']}
    inputs.require(set(report['not_attempted']) == set(by_id) - seen and
                   len(report['not_attempted']) == len(set(report['not_attempted'])), 'missing_coverage_mismatch')
    return packet, report, states


def build_previews(packet: dict, report: dict, states: dict, prompts: dict[str, str],
                   questions: dict[str, dict]) -> dict[str, Any]:
    """Separate clinical judgments from machine-assisted extraction judgments.

    Clinical bundles never contain annotations or source-model/wording-arm labels.
    Private provenance stays in a separate owner receipt, outside the rater bundle.
    """
    bundles = {}
    joins = {}
    coverage = []
    for task in ('clinical', 'extraction'):
        qdoc = copy.deepcopy(questions[task])
        items = []
        for source in packet['requests']:
            key = source['source_id']
            state = states[key]
            if task == 'clinical' and source['origin'] != 'archived_generated_response':
                continue  # Standalone software challenges have no clinical question.
            if task == 'extraction' and state['state'] != 'validated_semantics_unverified':
                continue
            annotation = copy.deepcopy(state['annotation']) if task == 'extraction' else None
            if annotation is not None:
                aa.validate_annotation(annotation, source['text'])
            prompt = prompts.get(key)
            inputs.require(source['origin'] != 'archived_generated_response' or
                           isinstance(prompt, str) and bool(prompt), 'missing_original_prompt')
            display = {'kind': 'evidence_review', 'task': task, 'origin': source['origin'],
                       'prompt': prompt, 'response': source['text'], 'annotation': annotation}
            identity = aa.digest(aa.encoded({'task': task, 'source': source['source_sha256'],
                                            'display': display, 'questions': qdoc}))[:12]
            item_id = 'vt_' + identity
            items.append({'item_id': item_id, 'family': 'evidence',
                          'question_set': 'evidence_' + task + '_v1', 'display': display, 'reveal': None})
            joins[item_id] = {'source_id': key, 'source_sha256': source['source_sha256'],
                             'archive_join': source.get('archive_join'), 'task': task,
                             'annotation_state': state['state']}
        items.sort(key=lambda r: aa.digest(f'{SEED}|{r["item_id"]}'.encode()))
        inputs.require(len({r['item_id'] for r in items}) == len(items), 'duplicate_review_item')
        bundle = {'schema': SCHEMA, 'purpose': task, 'preview_only': True, 'seed': SEED,
                  'questions': qdoc, 'questions_sha256': aa.digest(aa.encoded(qdoc)), 'items': items}
        bundle['bundle_id'] = 'evidence_preview_' + aa.digest(aa.encoded(bundle))[:16]
        bundles[task] = bundle
    for source in packet['requests']:
        coverage.append({'source_id': source['source_id'], 'origin': source['origin'],
                         'classifier_state': states[source['source_id']]['state']})
    return {**bundles, 'receipt': {'schema': 'patientwords-evidence-preview-receipt/1',
            'run_id': report['workflow_run_id'], 'run_status': report['status'],
            'source_engine_commit': report['engine_commit'], 'seed': SEED, 'coverage': coverage,
            'joins': joins, 'clinical_review': 'not_collected', 'extraction_review': 'not_collected',
            'reference_labels': 'none; prior owner selections remain separate and partial'}}


def prepare(folder: Path, run_id: str, root: Path = aa.ROOT) -> dict[str, Any]:
    """Build the preview without selecting sources by classifier success."""
    packet, report, states = load_run(folder, run_id, root)
    plan = inputs.parse(inputs.verified_bytes(root, inputs.PLAN, inputs.PLAN_SHA256))
    path, = [p for p in plan['source_files'] if p.endswith('.json') and not p.endswith('.report.json')]
    stimuli = inputs.parse(inputs.verified_bytes(root, path, plan['source_files'][path]))
    by_id = {r['id']: r for r in stimuli['items']}
    prompts = {}
    for source in packet['requests']:
        if source['origin'] == 'archived_generated_response':
            join = source['archive_join']
            inputs.require(join['arm'] in ('clinical', 'patient'), 'unknown_wording_arm')
            prompts[source['source_id']] = by_id[join['source_id']][join['arm'] + '_message']
    questions = {task: aa.read_json(root / f'data/action_annotations/review_questions_{task}.v1.json')
                 for task in ('clinical', 'extraction')}
    result = build_previews(packet, report, states, prompts, questions)
    from scripts import seal_check as sc
    registry = sc.sealed_registry(str(root / 'data/simulated'), str(root / 'ops/dashboard.json'))
    inputs.require(bool(registry), 'empty_seal_registry')
    inputs.require(not sc.scan_text(aa.encoded(result).decode(), registry, suffix='.json')[0], 'sealed_preview')
    return result


def main(argv: list[str] | None = None) -> int:
    """Only new external directories; no generated artifacts in either repository."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--artifact', required=True, type=Path)
    p.add_argument('--run-id', required=True)
    p.add_argument('--out', required=True, type=Path)
    args = p.parse_args(argv)
    from scripts.action_pilot import output_path
    try:
        out = output_path(args.out)
        inputs.require(not any((parent / '.git').exists() for parent in [out, *out.parents]),
                       'output_inside_repository')
        value = prepare(args.artifact, args.run_id)
        out.mkdir(exist_ok=False)
        for name, data in value.items():
            transport._write(out / (name + '.json'), aa.encoded(data))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print('REFUSED: evidence preview (' + type(exc).__name__ + ')')
        return 2
    print('Private draft preview:', len(value['clinical']['items']), 'clinical items;',
          len(value['extraction']['items']), 'extraction items. No new calls or clinical validation.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

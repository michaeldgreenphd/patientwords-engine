"""Separate review purposes, literal evidence and unchanged historical admission."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from scripts import action_annotations as aa
from scripts import action_pilot_inputs as inputs
from scripts import export_action_review as review

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def sample() -> tuple:
    text = 'Please wait.'
    annotation = {'status': 'annotated', 'reason': None, 'actions': [{
        'category': 'other_action', 'stance': 'recommended', 'actor': 'reader',
        'evidence': {'start': 0, 'end': len(text), 'quote': text}, 'timing': None, 'condition': None}]}
    requests = [{'source_id': key, 'origin': origin, 'text': text, 'source_sha256': aa.digest(text.encode()),
                 'archive_join': {'model_requested': 'hidden-model', 'arm': 'hidden-arm'} if key == 'R01' else None}
                for key, origin in [('s01', 'authored_synthetic_challenge'),
                                    ('R01', 'archived_generated_response'), ('s02', 'authored_synthetic_challenge')]]
    states = {'s01': {'state': 'validated_semantics_unverified', 'annotation': annotation},
              'R01': {'state': 'not_attempted', 'annotation': None},
              's02': {'state': 'invalid_annotation', 'annotation': None}}
    questions = {task: aa.read_json(ROOT / f'data/action_annotations/review_questions_{task}.v1.json')
                 for task in ('clinical', 'extraction')}
    return ({'requests': requests}, {'workflow_run_id': '1', 'status': 'stopped_incomplete',
                                    'engine_commit': '0' * 40}, states, {'R01': 'What next?'}, questions)


def test_separate_clinical_originals_and_machine_assisted_task(sample: tuple) -> None:
    result = review.build_previews(*sample)
    assert result == review.build_previews(*sample)
    clinical, = result['clinical']['items']
    extraction, = result['extraction']['items']
    assert clinical['display']['prompt'] == 'What next?'
    assert clinical['display']['annotation'] is None
    assert extraction['display']['annotation'] == sample[2]['s01']['annotation']
    for task in ('clinical', 'extraction'):
        b = result[task]
        assert b['schema'] != 'patientwords-verification-tasks/1'
        assert b['preview_only'] is True
        assert b['purpose'] == task and b['seed'] == review.SEED
        assert len(b['questions']['question_sets']) == 1
        assert b['questions_sha256'] == aa.digest(aa.encoded(b['questions']))
        assert b'hidden-model' not in aa.encoded(b) and b'hidden-arm' not in aa.encoded(b)
    assert [r['classifier_state'] for r in result['receipt']['coverage']] == [
        'validated_semantics_unverified', 'not_attempted', 'invalid_annotation']
    assert result['receipt']['clinical_review'] == 'not_collected'


def test_clinical_bundle_identical_before_and_after_machine_success(sample: tuple) -> None:
    before = review.build_previews(*sample)['clinical']
    sample[2]['R01'] = copy.deepcopy(sample[2]['s01'])
    after = review.build_previews(*sample)
    assert after['clinical'] == before
    assert len(after['extraction']['items']) == 2


def test_missing_prompt_refuses_instead_of_context_free_judgment(sample: tuple) -> None:
    sample[3].clear()
    with pytest.raises(aa.AnnotationRefusal, match='missing_original_prompt'):
        review.build_previews(*sample)


def test_literal_span_corruption_refused(sample: tuple) -> None:
    sample[2]['s01']['annotation']['actions'][0]['evidence']['end'] -= 1
    with pytest.raises(aa.AnnotationRefusal, match='evidence_span_mismatch'):
        review.build_previews(*sample)


def test_question_change_changes_bundle_and_item_identity(sample: tuple) -> None:
    before = review.build_previews(*sample)
    sample[4]['clinical']['question_sets']['evidence_clinical_v1']['questions'][0]['text'] += '?'
    after = review.build_previews(*sample)
    assert before['clinical']['bundle_id'] != after['clinical']['bundle_id']
    assert before['clinical']['items'][0]['item_id'] != after['clinical']['items'][0]['item_id']
    assert before['extraction'] == after['extraction']


def test_artifact_path_escape_hash_and_missing_file_refuse(tmp_path: Path) -> None:
    folder = tmp_path / 'artifact'
    folder.mkdir()
    (tmp_path / 'outside').write_bytes(b'fixture')
    digest = aa.digest(b'fixture')
    with pytest.raises(aa.AnnotationRefusal, match='artifact_path_escape'):
        review.artifact_file(folder, '../outside', digest)
    (folder / 'inside').write_bytes(b'fixture')
    assert review.artifact_file(folder, 'inside', digest) == b'fixture'
    with pytest.raises(aa.AnnotationRefusal, match='artifact_hash_mismatch'):
        review.artifact_file(folder, 'inside', '0' * 64)
    with pytest.raises(FileNotFoundError):
        review.artifact_file(folder, 'missing', digest)


def test_missing_and_changed_landed_receipt_refuse(tmp_path: Path) -> None:
    with pytest.raises(aa.AnnotationRefusal, match='run_id_invalid'):
        review.load_run(tmp_path, '../1', ROOT)
    with pytest.raises(aa.AnnotationRefusal, match='unreadable_json'):
        review.load_run(tmp_path, '1', tmp_path)
    # Actual immutable cost sidecar can authenticate the report without loading
    # any patient text or running a provider. Bad bytes cannot enter replay.
    (tmp_path / 'report.json').write_bytes(b'{}')
    with pytest.raises(aa.AnnotationRefusal, match='artifact_hash_mismatch'):
        review.load_run(tmp_path, '40510625603', ROOT)


def test_cli_refuses_existing_output_and_run_failure_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                                 sample: tuple) -> None:
    output = tmp_path / 'new'
    assert review.main(['--artifact', str(tmp_path), '--run-id', '1', '--out', str(output)]) == 2
    assert not output.exists()
    monkeypatch.setattr(review, 'prepare', lambda *args: review.build_previews(*sample))
    assert review.main(['--artifact', str(tmp_path), '--run-id', '1', '--out', str(output)]) == 0
    original = (output / 'clinical.json').read_bytes()
    assert review.main(['--artifact', str(tmp_path), '--run-id', '1', '--out', str(output)]) == 2
    assert (output / 'clinical.json').read_bytes() == original


def test_original_source_admission_still_omits_owner_labels() -> None:
    packet = inputs.prepare(ROOT)
    assert packet['owner_labels_sent'] is False and len(packet['requests']) == 14
    assert packet['seal_hits'] == 0

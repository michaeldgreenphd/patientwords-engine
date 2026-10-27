"""One CI-only assisted pass, with offline prepare and injectable test transports.

No retries, resume, model substitution or reference-label scoring. Failure stops
continuation and preserves the missing rows and unknown charge. Run via -m only.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import time
from typing import Any, Callable, Iterator

from scripts import action_annotations as aa
from scripts import action_annotation_transport as at
from scripts.action_annotation_messages import interpret_reply
from scripts import action_pilot_budget as budget
from scripts import action_pilot_inputs as inputs
from scripts.action_pilot_inputs import require

ROOT = aa.ROOT
TRIGGER = 'action-annotate'
TRIGGER_PATH = Path('.github/trigger/action-annotate.json')
RECOVERY = Path('data/action_annotations/recovery_20261026.v1.json')
RECOVERY_SHA256 = '9758535734715f69ae61e587dc69212c9c4405fb07d20b02b87e6ce7341cf67d'
RECOVERY_NONCE = 'assisted-actions-20261026-recovery-1'
QUOTE_CAMPAIGN = Path('data/action_annotations/quote_campaign.v1.json')
QUOTE_CAMPAIGN_SHA256 = 'af5ebe737664fca846ac9452cf639fbb0ee26fdb83e9f3556763b0326f25906b'
QUOTE_NONCE = 'assisted-action-quotes-20261027-1'


def quote_campaign(root: Path) -> dict[str, Any]:
    """Bind the new format to reviewed code and the preserved earlier failures."""
    from scripts import action_quote_annotations as quotes

    receipt = inputs.parse(inputs.verified_bytes(root, QUOTE_CAMPAIGN, QUOTE_CAMPAIGN_SHA256))
    require(receipt['nonce'] == QUOTE_NONCE and receipt['response_format'] == quotes.FORMAT and
            receipt['preparation_sha256'] == quotes.MANIFEST_SHA256, 'quote_campaign_identity')
    for path, expected in receipt['contract_files'].items():
        inputs.verified_bytes(root, path, expected)
    return receipt


def prepare_campaign(plan_sha256: str, root: Path) -> dict[str, Any]:
    """Prepare one recognized frozen contract; this performs no execution admission."""
    if plan_sha256 == inputs.PLAN_SHA256:
        return inputs.prepare(root)
    require(plan_sha256 == QUOTE_CAMPAIGN_SHA256, 'unknown_campaign_plan')
    from scripts import action_quote_annotations as quotes

    receipt = quote_campaign(root)
    prepared = quotes.prepare(root)
    # Preserve the offline preparation as a separate historical contract, without
    # presenting its execution_enabled:false as the result of live CI admission.
    return {'schema_version': 'patientwords.action-pilot-inputs/2',
            'plan_sha256': QUOTE_CAMPAIGN_SHA256, 'plan': receipt,
            'preparation_sha256': quotes.MANIFEST_SHA256,
            'prepared_inputs_sha256': aa.digest(aa.encoded(prepared)),
            'response_format': quotes.FORMAT, 'requests': prepared['requests'],
            'seal_registry_count': prepared['seal_registry_count'], 'seal_hits': prepared['seal_hits'],
            'purpose': prepared['purpose'], 'owner_labels_sent': False}


def recovery_receipt(root: Path) -> dict[str, Any]:
    """One reviewed pre-transport failure, not a general retry allowance."""
    return inputs.parse(inputs.verified_bytes(root, RECOVERY, RECOVERY_SHA256))


def campaign_identity(entries: list[dict[str, Any]], nonce: str, root: Path) -> dict[str, Any]:
    """Retain all paid history; admit only explicitly reviewed attempt identities."""
    mine = [e for e in entries if e.get('trigger') == TRIGGER and e.get('max_spend') is not None]
    if nonce == QUOTE_NONCE:
        receipt = quote_campaign(root)
        require(len(mine) == 3 and mine[:2] == receipt['prior_reservations'] and
                mine[2].get('nonce') == nonce, 'quote_campaign_history_mismatch')
        return {'quote_campaign': {'receipt_sha256': QUOTE_CAMPAIGN_SHA256, 'nonce': nonce,
                'preparation_sha256': receipt['preparation_sha256'],
                'prior_attempts': receipt['prior_attempts'], 'prior_reservations_retained': True}}
    if nonce == inputs.NONCE:
        require(len(mine) == 1 and mine[0].get('nonce') == nonce, 'campaign_already_reserved')
        return {}
    require(nonce == RECOVERY_NONCE, 'unauthorized_recovery')
    receipt = recovery_receipt(root)
    # Exact equality refuses a removed, resolved, evicted, renamed or edited hold.
    # The current reservation is separately bound to this push by cmd_budget_gate.
    require(len(mine) == 2 and mine[0] == receipt['prior_reservation'] and
            mine[1].get('nonce') == nonce, 'recovery_history_mismatch')
    return {'recovery': {'receipt_sha256': RECOVERY_SHA256, 'nonce': nonce,
                         'prior_failure': receipt['prior_failure'],
                         'prior_reservation_retained': True}}


def git(*args: str, root: Path = ROOT) -> str:
    """Read source identity without including authors, credentials or response text."""
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def params_problems(params: dict[str, Any], root: Path | None = None) -> list[str]:
    """Exact pilot trigger contract, shared by the fire path and execution gate."""
    if not isinstance(params, dict):
        return ['action_params_shape']
    if set(params) - {'mode', 'plan_sha256', 'max_spend', 'expected_commit'} - {
            k for k in params if k.startswith('_')}:
        return ['action_unknown_param']
    if params.get('mode') not in ('park', 'run'):
        return ['action_mode_required']
    if params['mode'] == 'park':
        return [] if all(params.get(k) == v for k, v in {
            'plan_sha256': '', 'max_spend': '0', 'expected_commit': ''}.items()) else ['action_park_values']
    quote_plan = params.get('plan_sha256') == QUOTE_CAMPAIGN_SHA256 and params.get('_nonce') == QUOTE_NONCE
    old_plan = params.get('plan_sha256') == inputs.PLAN_SHA256 and params.get('_nonce') in (inputs.NONCE, RECOVERY_NONCE)
    if not (quote_plan or old_plan):
        return ['action_fixed_plan_and_nonce_required']
    if params.get('max_spend') != '1.00':
        return ['action_full_one_dollar_reservation_required']
    if not isinstance(params.get('expected_commit'), str) or not re.fullmatch('[0-9a-f]{40}', params['expected_commit']):
        return ['action_exact_commit_required']
    if root is not None:
        try:
            inputs.verified_bytes(root, inputs.PLAN, inputs.PLAN_SHA256)
            budget.prices(root, datetime.now(timezone.utc).date())
            if params['_nonce'] == RECOVERY_NONCE:
                recovery_receipt(root)
            if quote_plan:
                quote_campaign(root)
        except (OSError, ValueError):
            return ['action_plan_or_price_unavailable']
    return []


def admit_ci(params: dict[str, Any], env: dict[str, str], root: Path = ROOT) -> dict[str, Any]:
    """Reject manual dispatch, re-run, branch copy and replay before reading a key."""
    from scripts import fire_trigger as ft

    require(not params_problems(params, root) and params['mode'] == 'run', 'action_params_invalid')
    for key, value in {'GITHUB_ACTIONS': 'true', 'GITHUB_EVENT_NAME': 'push', 'GITHUB_REF': 'refs/heads/main',
                       'GITHUB_REPOSITORY': 'michaeldgreenphd/patientwords-engine', 'GITHUB_RUN_ATTEMPT': '1',
                       'GITHUB_ACTOR': 'michaeldgreenphd', 'GITHUB_TRIGGERING_ACTOR': 'michaeldgreenphd'}.items():
        require(env.get(key) == value, 'ci_identity_refused')
    require(bool(re.fullmatch('[1-9][0-9]*', env.get('GITHUB_RUN_ID', ''))), 'run_id_required')
    event = aa.read_json(Path(env['GITHUB_EVENT_PATH']))
    require(event.get('created') is False and event.get('before') == params['expected_commit'], 'push_identity_refused')
    head = git('rev-parse', 'HEAD', root=root)
    require(head == env.get('GITHUB_SHA') and event.get('after') == head, 'checkout_identity_refused')
    require(git('show', '-s', '--format=%P', 'HEAD', root=root) == params['expected_commit'], 'fire_parent_mismatch')
    changed = git('diff', '--name-only', params['expected_commit'], 'HEAD', root=root).splitlines()
    require(set(changed) == {str(TRIGGER_PATH), 'ops/trigger_journal.jsonl'}, 'fire_carries_code_changes')
    require(not git('status', '--porcelain', '--untracked-files=normal', root=root), 'dirty_execution_checkout')
    remote = git('ls-remote', 'origin', 'refs/heads/main', root=root).split()
    require(len(remote) == 2 and remote[0] == head, 'main_advanced_before_admission')
    # The writer journals git's short branch name, as other CI lanes pass ref_name.
    # Normalize only after the exact refs/heads/main identity check above succeeds.
    args = argparse.Namespace(repo=str(root), trigger=TRIGGER, params_file=None,
                              push_before=event['before'], ref=env['GITHUB_REF'].removeprefix('refs/heads/'), run_attempt=1)
    require(ft.cmd_budget_gate(args) == 0, 'journal_or_daily_budget_refused')
    entries = ft.load_journal(root / ft.JOURNAL_RELPATH)
    nonce = params['_nonce']
    recovery = campaign_identity(entries, nonce, root)
    now = datetime.now(timezone.utc)
    require(now.hour < 23 or now.minute < 25, 'too_close_to_utc_rollover')
    available = budget.availability(root, entries, now.date(), nonce)
    return {'engine_commit': head, 'reviewed_code_commit': params['expected_commit'],
            'workflow_run_id': env['GITHUB_RUN_ID'], 'workflow_run_attempt': 1,
            'journal_nonce': nonce, 'inference': {'environment': 'github_actions'},
            'budget_admission': available, 'execution_day_utc': now.date().isoformat(), **recovery}


@contextmanager
def deadline(seconds: float) -> Iterator[None]:
    """A wall-clock deadline including DNS/connect/read, restoring process handlers."""
    require(seconds > 0, 'campaign_deadline')
    require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), 'existing_timer')

    def expired(signum: int, frame: Any) -> None:
        raise TimeoutError('attempt_deadline')

    old = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


def snapshot(path: Path, value: Any) -> None:
    """Atomic local progress snapshot; never applied to a landed artifact."""
    tmp = path.with_suffix(path.suffix + '.tmp')
    at._write(tmp, aa.encoded(value))
    os.replace(tmp, path)
    at._sync_dir(path.parent)


def output_path(out: Path) -> Path:
    """Both CLI modes write only new external artifact directories."""
    out = out.resolve()
    require(not out.is_relative_to(ROOT.resolve()) and not any(p in out.parts for p in ('trace_out', 'pilot', '.git')),
            'output_outside_engine_required')
    return out


def run(packet: dict[str, Any], price: dict[str, Any], identity: dict[str, Any], out: Path,
        send: Callable[[dict[str, Any]], at.Reply], count: Callable[[dict[str, Any]], at.Reply]) -> dict[str, Any]:
    """Injectable single-pass worker; only main constructs real provider clients."""
    plan_sha256 = packet.get('plan_sha256', inputs.PLAN_SHA256)
    require(plan_sha256 in (inputs.PLAN_SHA256, QUOTE_CAMPAIGN_SHA256), 'unknown_campaign_plan')
    response_format = 'patientwords.action-spans/1'
    if plan_sha256 == QUOTE_CAMPAIGN_SHA256:
        from scripts import action_quote_annotations as quotes
        response_format = quotes.FORMAT
        require(packet.get('response_format') == response_format and
                all(r.get('response_format') == response_format for r in packet['requests']) and
                identity.get('journal_nonce') == QUOTE_NONCE and
                identity.get('quote_campaign', {}).get('receipt_sha256') == QUOTE_CAMPAIGN_SHA256,
                'quote_execution_binding_mismatch')
    else:
        require(packet.get('response_format', response_format) == response_format and
                identity.get('journal_nonce') != QUOTE_NONCE, 'legacy_execution_binding_mismatch')
    out = output_path(out)
    out.mkdir(exist_ok=False, parents=False)
    attempts = out / 'action_annotation_attempts'
    attempts.mkdir()
    at._write(out / 'inputs.json', aa.encoded(packet))
    at._write(out / 'price.json', aa.encoded(price))
    report: dict[str, Any] = {'schema_version': 'patientwords.action-pilot-report/1',
        'task': 'assisted_action_annotation', 'model': price['model'], 'billing_channel': 'anthropic',
        'cost_basis': price['cost_basis'], 'cost_usd': None, 'known_cost_usd': '0', 'reserved_usd': '1.00',
        'reservation_release_allowed': False, 'run_timestamp': datetime.now(timezone.utc).isoformat(),
        'plan_sha256': plan_sha256, 'price_sha256': inputs.PRICE_SHA256,
        'runtime': {'python': platform.python_version(), 'platform': platform.platform(),
                    'transport': 'python_stdlib_http.client', 'sdk_retries': 0},
        'purpose': 'assistance_not_independent_accuracy', 'status': 'started', 'model_calls_attempted': 0,
        'count_calls_attempted': 0, 'count_estimates': [], 'items': [],
        'not_attempted': [r['source_id'] for r in packet['requests']], **identity}
    if plan_sha256 == QUOTE_CAMPAIGN_SHA256:
        # Additive fields preserve the cost receipt's version-1 ledger contract.
        report.update(response_format=response_format,
                      inputs_sha256=aa.digest(aa.encoded(packet)),
                      preparation_sha256=packet['preparation_sha256'],
                      prepared_inputs_sha256=packet['prepared_inputs_sha256'])
    snapshot(out / 'report.json', report)
    total = Decimal(0)
    uncertain = False
    end = time.monotonic() + 1800
    try:
        for item in packet['requests']:
            wire = item['wire']
            folder = out / ('count_' + item['source_id'])
            folder.mkdir()
            at._write(folder / 'request.json', aa.encoded({
                'method': 'POST', 'path': '/v1/messages/count_tokens', 'api_version': wire['api_version'],
                'body': {k: wire['body'][k] for k in ('model', 'system', 'messages', 'thinking')}}))
            report['count_calls_attempted'] += 1
            snapshot(out / 'report.json', report)
            with deadline(min(20, end - time.monotonic())):
                reply = count(wire)
            at.validate_reply(reply)
            at._write(folder / 'response.bin', reply.body)
            at._write(folder / 'result.json', aa.encoded({k: v for k, v in vars(reply).items() if k != 'body'}))
            require(reply.complete and reply.http_status == 200, 'count_request_failed')
            result = inputs.parse(reply.body)
            require(isinstance(result, dict) and set(result) <= {'input_tokens', 'context_management'} and
                    result.get('context_management') is None and
                    type(result.get('input_tokens')) is int and 0 <= result['input_tokens'] <= price['context_tokens'],
                    'invalid_count_reply')
            report['count_estimates'].append({'source_id': item['source_id'],
                'request_sha256': item['request_sha256'], 'input_tokens': result['input_tokens']})
        estimated = sum((Decimal(row['input_tokens']) * budget.amount(price['long_input_usd_per_million']) +
                         price['max_output_tokens'] * budget.amount(price['long_output_usd_per_million'])) / 1000000
                        for row in report['count_estimates'])
        report['estimated_total_upper_rate_usd'] = str(estimated)
        require(estimated <= Decimal(1), 'estimated_total_exceeds_ceiling')
        for item in packet['requests']:
            require(total + budget.call_bound(price) <= Decimal(1), 'insufficient_next_call_headroom')
            require(datetime.now(timezone.utc).date().isoformat() == identity['execution_day_utc'], 'utc_day_changed')
            uncertain = True
            report['model_calls_attempted'] += 1
            report['not_attempted'].remove(item['source_id'])
            snapshot(out / 'report.json', report)
            with deadline(min(120, end - time.monotonic())):
                captured = at.capture_attempt(item['wire'], source_id=item['source_id'],
                    source_sha256=item['source_sha256'], run_root=attempts, send=send)
            raw = (attempts / captured['request_sha256'] / 'response.bin').read_bytes()
            require(aa.digest(raw) == captured['raw_body_sha256'] and
                    captured['request_sha256'] == item['request_sha256'], 'capture_binding_mismatch')
            reply = at.Reply(captured['http_status'], captured['request_id'], raw,
                             captured['body_complete'], captured['transport_error'])
            interpreted = interpret_reply(reply, expected_model=price['model'], source_text=item['text'],
                                          response_format=response_format)
            row = {'source_id': item['source_id'], 'origin': item['origin'], 'capture': captured,
                   'interpretation': interpreted, 'cost_usd': None}
            report['items'].append(row)
            snapshot(out / 'report.json', report)
            require(reply.complete and reply.http_status == 200 and interpreted['reported_model'] == price['model'],
                    'unpriceable_response')
            cost = budget.usage_cost(interpreted['usage'], price)
            total += cost
            uncertain = False
            row['cost_usd'] = str(cost)
            report['known_cost_usd'] = str(total)
            snapshot(out / 'report.json', report)
            require(interpreted['status'] == 'validated_semantics_unverified', 'annotation_failed_stop')
        report['status'] = 'complete_semantics_unverified'
    except (Exception, KeyboardInterrupt) as exc:
        report['status'] = 'stopped_incomplete'
        report['failure_class'] = type(exc).__name__
        if isinstance(exc, aa.AnnotationRefusal) and re.fullmatch('[a-z_]+', str(exc)):
            report['refusal'] = str(exc)
    finally:
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        report['known_cost_usd'] = str(total)
        report['cost_usd'] = None if uncertain else float(total)
        report['unknown_charge'] = uncertain
        report['artifact_hashes'] = {str(p.relative_to(out)): aa.digest(p.read_bytes()) for p in sorted(out.rglob('*'))
                                    if p.is_file() and p.name not in ('report.json', 'report.json.tmp')}
        snapshot(out / 'report.json', report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare', 'live'])
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--plan-sha256', help='Offline prepare only; live always reads the admitted trigger')
    args = parser.parse_args(argv)
    if args.mode == 'live' and args.plan_sha256 is not None:
        parser.error('live forbids --plan-sha256')
    try:
        if args.mode == 'prepare':
            args.out = output_path(args.out)
            packet = prepare_campaign(args.plan_sha256 or inputs.PLAN_SHA256, ROOT)
            args.out.mkdir(exist_ok=False)
            at._write(args.out / 'inputs.json', aa.encoded(packet))
            print('Prepared 14 frozen requests offline; no execution or spend admission.')
            return 0
        params = aa.read_json(ROOT / TRIGGER_PATH)
        identity = admit_ci(params, dict(os.environ))
        packet = prepare_campaign(params['plan_sha256'], ROOT)
        price = budget.prices(ROOT, datetime.now(timezone.utc).date())
        client = at.AnthropicTransport(os.environ.get('ANTHROPIC_API_KEY', ''))
        result = run(packet, price, identity, args.out, client, client.count)
        print('Pilot status:', result['status'], '; attempted:', result['model_calls_attempted'])
        return 0 if result['status'] == 'complete_semantics_unverified' else 1
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print('REFUSED: pilot admission failed (' + type(exc).__name__ + '); no retry.')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

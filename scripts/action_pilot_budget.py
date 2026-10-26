"""Conservative admission/accounting for the single authorized assisted pass only."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from scripts import action_annotations as aa
from scripts.action_pilot_inputs import PRICE, PRICE_SHA256, parse, require, verified_bytes

SIDECARS = ('data/simulated/*.report.json', 'data/advice/*.report.json', 'data/pab/*.report.json',
            'data/petri/runs/*/*.report.json', 'data/petri/rejudge/*/*/*.report.json',
            'data/jev/runs/*.report.json', 'trace_out/*/mitigation*.report.json',
            'data/action_annotations/runs/*.report.json')


def amount(value: Any) -> Decimal:
    """Unknown/invalid charges are refusals, never zero."""
    try:
        require(type(value) in (str, int, float), 'unknown_cost')
        result = Decimal(str(value))
        require(result.is_finite() and result >= 0, 'unknown_cost')
        return result
    except InvalidOperation as exc:
        raise aa.AnnotationRefusal('unknown_cost') from exc


def prices(root: Path, today: date) -> dict[str, Any]:
    """Reviewed rates expire; an elapsed estimate is not current price evidence."""
    result = parse(verified_bytes(root, PRICE, PRICE_SHA256))
    require(date.fromisoformat(result['checked_utc']) <= today <= date.fromisoformat(result['expires_utc']),
            'price_receipt_expired_or_future')
    return result


def call_bound(price: dict[str, Any]) -> Decimal:
    """Full context plus capped output at long-context rates, not estimated tokens."""
    return (amount(price['long_input_usd_per_million']) * price['context_tokens'] +
            amount(price['long_output_usd_per_million']) * price['max_output_tokens']) / 1000000


def usage_cost(usage: Any, price: dict[str, Any]) -> Decimal:
    """Gross standard-rate cost; unsupported billing dimensions stop the campaign."""
    require(isinstance(usage, dict), 'unknown_usage')
    allowed = {'input_tokens', 'output_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens',
               'cache_creation', 'server_tool_use', 'service_tier', 'inference_geo', 'speed', 'output_tokens_details'}
    require(set(usage) <= allowed, 'unsupported_usage_dimension')
    for key, bound in [('input_tokens', price['context_tokens']), ('output_tokens', price['max_output_tokens'])]:
        require(type(usage.get(key)) is int and 0 <= usage[key] <= bound, 'usage_out_of_bounds')
    for key in ('cache_creation_input_tokens', 'cache_read_input_tokens'):
        require(key not in usage or type(usage[key]) is int and usage[key] == 0, 'unexpected_cache_usage')
    for key in ('cache_creation', 'server_tool_use', 'output_tokens_details'):
        if key in usage:
            require(isinstance(usage[key], dict) and all(type(v) is int and v == 0 for v in usage[key].values()),
                    'unexpected_auxiliary_usage')
    require(usage.get('service_tier', 'standard') == 'standard', 'unsupported_service_tier')
    require(usage.get('speed', 'standard') == 'standard', 'unsupported_speed')
    require(usage.get('inference_geo', 'global') == 'global', 'unsupported_inference_geo')
    prefix = 'long_' if usage['input_tokens'] > price['long_prompt_threshold'] else ''
    return (usage['input_tokens'] * amount(price[prefix + 'input_usd_per_million']) +
            usage['output_tokens'] * amount(price[prefix + 'output_usd_per_million'])) / 1000000


def availability(root: Path, entries: list[dict[str, Any]], today: date, own_nonce: str | None = None) -> dict[str, str]:
    """Overcount historical/all-provider spend rather than infer missing month splits.

    The existing daily gate still runs separately. This is a guard for this lane,
    not a retrofit of the other lanes' monthly admission. Dashboard lifetime and
    the sum of ALL landed sidecars bound monthly landed usage from above. Add all
    current-month commitments and unresolved older commitments, even if expired.
    No credits, refunds, resolved-current-month or missing charges reduce it.
    """
    from scripts import fire_trigger as ft

    dashboard = aa.read_json(root / 'ops/dashboard.json')
    lifetime = amount(dashboard['spend']['lifetime_generation_usd'])
    sidecar_total = Decimal(0)
    for pattern in SIDECARS:
        for path in sorted(root.glob(pattern)):
            sidecar_total += amount(aa.read_json(path).get('cost_usd'))
    held = Decimal(0)
    for entry in entries:
        if entry.get('max_spend') is None:
            continue
        stamp = ft.parse_utc(entry.get('fired_utc'))
        require(stamp is not None, 'undated_commitment')
        require(type(entry.get('resolved', False)) is bool and type(entry.get('evicted', False)) is bool,
                'invalid_commitment_state')
        if own_nonce and entry.get('trigger') == 'action-annotate' and entry.get('nonce') == own_nonce:
            continue  # the full reservation is added below, exactly once
        if entry.get('evicted') is True:
            continue
        if stamp.strftime('%Y-%m') == today.strftime('%Y-%m') or not entry.get('resolved'):
            held += amount(entry['max_spend'])
    landed_bound = max(lifetime, sidecar_total)
    total = landed_bound + held + Decimal('1')
    require(total <= Decimal('200'), 'monthly_allocation_unavailable')
    return {'landed_upper_bound_usd': str(landed_bound), 'held_upper_bound_usd': str(held),
            'new_reservation_usd': '1.00', 'monthly_ceiling_usd': '200.00', 'committed_upper_bound_usd': str(total)}

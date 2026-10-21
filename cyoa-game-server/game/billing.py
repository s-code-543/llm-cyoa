"""Durable per-call spending, independent of transcript rollback."""
from decimal import Decimal, InvalidOperation

from .models import AuditLog


def amount(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() and result >= 0 else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def record_call(conversation_id, record, model=None, kind='text'):
    usage = record.get('usage') or {}
    cost = amount(usage.get('cost'))
    estimated = False
    if cost is None and model is not None and kind == 'text':
        rates = (model.capabilities or {}).get('pricing', {})
        prompt = amount(usage.get('prompt_tokens', usage.get('input_tokens')))
        completion = amount(usage.get('completion_tokens', usage.get('output_tokens')))
        input_rate, output_rate = amount(rates.get('prompt')), amount(rates.get('completion'))
        # Cache and tier pricing require more than base token rates.
        cached = usage.get('prompt_tokens_details', {}).get('cached_tokens') or usage.get('cache_read_input_tokens') or usage.get('cache_creation_input_tokens')
        if None not in (prompt, completion, input_rate, output_rate) and not cached and not rates.get('overrides'):
            cost = prompt * input_rate + completion * output_rate
            estimated = True
    AuditLog.objects.create(original_text='', refined_text='', details={
        'type': 'api_usage', 'conversation_id': conversation_id, 'kind': kind,
        'cost_usd': str(cost) if cost is not None else None, 'estimated': estimated,
    })
    record['cost_recorded'] = True


def game_cost(conversation_id):
    total, calls, unpriced, estimated = Decimal(0), 0, 0, 0
    for details in AuditLog.objects.filter(details__conversation_id=conversation_id).values_list('details', flat=True):
        if details.get('type') == 'api_usage':
            records = [details]
        else:
            # Older traces contain a single authoritative list of model calls.
            records = [{'cost_usd': (r.get('usage') or {}).get('cost')}
                       for r in details.get('model_requests', []) if not r.get('cost_recorded')]
        for record in records:
            calls += 1
            cost = amount(record.get('cost_usd'))
            if cost is None:
                unpriced += 1
            else:
                total += cost
            estimated += bool(record.get('estimated'))
    return {'total_usd': str(total), 'calls': calls, 'unpriced_calls': unpriced,
            'estimated_calls': estimated, 'currency': 'USD'}

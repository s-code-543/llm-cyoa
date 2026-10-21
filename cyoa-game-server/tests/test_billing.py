from decimal import Decimal
from types import SimpleNamespace

import pytest

from game.billing import game_cost, record_call
from game.models import AuditLog

pytestmark = pytest.mark.django_db


def test_total_retains_failed_and_historical_calls_without_double_counting():
    record = {'usage': {'cost': '0.0012'}}
    record_call('game', record)
    AuditLog.objects.create(details={'conversation_id': 'game', 'model_requests': [record]})
    AuditLog.objects.create(details={'conversation_id': 'game', 'type': 'workflow_error',
                                    'model_requests': [{'usage': {'cost': '0.0023'}}]})
    record_call('game', {})
    record_call('other-game', {'usage': {'cost': 99}})
    result = game_cost('game')
    assert Decimal(result['total_usd']) == Decimal('0.0035')
    assert result['calls'] == 3
    assert result['unpriced_calls'] == 1


def test_estimate_and_unknown_prices():
    model = SimpleNamespace(capabilities={'pricing': {'prompt': '0.001', 'completion': '0.002'}})
    record_call('game', {'usage': {'input_tokens': 10, 'output_tokens': 5}}, model)
    record_call('game', {'usage': {'cost': 'NaN'}}, model)
    record_call('game', {'usage': {'cost': 0}}, kind='image')
    result = game_cost('game')
    assert Decimal(result['total_usd']) == Decimal('0.020')
    assert result['estimated_calls'] == 1
    assert result['unpriced_calls'] == 1


def test_usage_audit_populates_required_text_fields():
    record_call('game', {'usage': {'cost': '0.0012'}})
    audit = AuditLog.objects.get(details__type='api_usage')
    assert audit.original_text == ''
    assert audit.refined_text == ''


def test_cost_endpoint_is_staff_only_and_survives_transcript_deletion(auth_client, admin_client, user):
    from tests.conftest import ChatConversationFactory, ChatMessageFactory
    conversation = ChatConversationFactory(user=user)
    message = ChatMessageFactory(conversation=conversation, role='assistant')
    record_call(conversation.conversation_id, {'usage': {'cost': '0.0042'}})
    url = f'/api/v1/chat/conversations/{conversation.conversation_id}/debug?summary=true'
    assert auth_client.get(url).status_code == 403
    message.delete()
    response = admin_client.get(url)
    assert response.status_code == 200
    assert Decimal(response.json()['cost']['total_usd']) == Decimal('0.0042')
    assert response.json()['cost']['calls'] == 1


def test_model_breakdown_separates_providers_and_reconciles_total():
    for provider, price in [('First', '0.012'), ('Second', '0.023')]:
        model = SimpleNamespace(name='Narrator', model_identifier='story-v1',
                                provider=SimpleNamespace(name=provider), capabilities={})
        record_call('game', {'usage': {'cost': price}}, model)
        record_call('game', {}, model)
    AuditLog.objects.create(details={'conversation_id': 'game', 'model_requests': [
        {'model': 'Legacy judge', 'usage': {'cost': '0.005'}}]})
    result = game_cost('game')
    assert len(result['models']) == 3
    assert sum(Decimal(row['total_usd']) for row in result['models']) == Decimal(result['total_usd'])
    assert sum(row['calls'] for row in result['models']) == result['calls'] == 5
    assert result['models'][0]['provider'] == 'Second'
    assert result['models'][0]['model_identifier'] == 'story-v1'
    assert result['models'][0]['unpriced_calls'] == 1

"""Contracts for the React player API, using mocked generation only."""
import hashlib
import json
import uuid
from unittest.mock import patch

import pytest
from django.test import override_settings
from game.models import ChatSubmission, ChatMessage, GameSession
from tests.conftest import ChatConversationFactory, ChatMessageFactory

BASE = '/api/v1/chat/'


def post(client, path, payload):
    return client.post(BASE + path, json.dumps(payload), content_type='application/json')


@pytest.fixture
def adventure(user, configuration):
    configuration.enable_refusal_detection = False
    configuration.save()
    return ChatConversationFactory(user=user, metadata={'config_id': configuration.pk})


@pytest.mark.django_db
def test_json_session_expiry(client):
    response = client.get(BASE + 'bootstrap')
    assert response.status_code == 401
    assert response.json()['error']['code'] == 'unauthenticated'
    assert 'no-store' in response['Cache-Control']


@pytest.mark.django_db
def test_owned_conversation_only(auth_client, admin_user):
    other = ChatConversationFactory(user=admin_user)
    assert auth_client.get(BASE + f'conversations/{other.conversation_id}').status_code == 404


@pytest.mark.django_db
def test_creation_is_explicit_and_idempotent(auth_client, configuration):
    payload = {'request_id': str(uuid.uuid4()), 'config_id': configuration.pk}
    first = post(auth_client, 'conversations', payload)
    second = post(auth_client, 'conversations', payload)
    assert first.status_code == second.status_code == 200
    assert first.json()['conversation']['id'] == second.json()['conversation']['id']
    assert first.json()['conversation']['state']['max_turns'] == configuration.total_turns


@pytest.mark.django_db
def test_send_reload_and_replay_do_not_call_provider_twice(auth_client, adventure):
    text = '**Turn 1 of 10**\n\nSnow surrounds the base.\n\n**Inventory:** torch, key\n\n1) Enter\n2) Wait'
    payload = {'message': 'Enter the base', 'request_id': str(uuid.uuid4())}
    path = f'conversations/{adventure.conversation_id}/turns'
    with patch('game.chat_views.call_llm', return_value=text) as llm:
        first = post(auth_client, path, payload)
        replay = post(auth_client, path, payload)
        assert first.status_code == replay.status_code == 200
        assert llm.call_count == 1
    loaded = auth_client.get(BASE + f'conversations/{adventure.conversation_id}').json()['conversation']
    assert first.json()['conversation'] == loaded
    assert loaded['state']['turn'] == 1
    assert loaded['state']['inventory'] == ['torch', 'key']
    assert loaded['state']['choices'] == ['Enter', 'Wait']
    assert len(loaded['messages']) == 2
    assert set(loaded['messages'][1]) == {'id', 'role', 'content', 'created_at', 'is_error', 'image_url', 'image_failed'}
    assert loaded['pending_request_id'] is None
    assert ChatSubmission.objects.get().status == 'completed'


@pytest.mark.django_db
def test_completed_submission_replays_after_configuration_deactivation(auth_client, adventure, configuration):
    payload = {'message': 'Go', 'request_id': str(uuid.uuid4())}
    path = f'conversations/{adventure.conversation_id}/turns'
    with patch('game.chat_views.call_llm', return_value='Turn 1 of 10\nSnow\n1) Enter\n2) Wait') as llm:
        first = post(auth_client, path, payload)
        configuration.is_active = False
        configuration.save()
        replay = post(auth_client, path, payload)

    assert first.status_code == replay.status_code == 200
    assert llm.call_count == 1


@pytest.mark.django_db
def test_pending_submission_is_reported_after_configuration_deactivation(auth_client, adventure, configuration):
    payload = {'message': 'Go', 'request_id': str(uuid.uuid4())}
    digest = hashlib.sha256(json.dumps({
        'conversation_id': adventure.conversation_id, 'message': 'Go',
    }, sort_keys=True).encode()).hexdigest()
    ChatSubmission.objects.create(
        conversation=adventure, request_id=payload['request_id'], operation='send', payload_hash=digest,
    )
    configuration.is_active = False
    configuration.save()

    response = post(auth_client, f'conversations/{adventure.conversation_id}/turns', payload)

    assert response.status_code == 409
    assert response.json()['error']['code'] == 'request_pending'


@pytest.mark.django_db
def test_pending_request_blocks_other_actions(auth_client, adventure):
    ChatSubmission.objects.create(conversation=adventure, request_id=uuid.uuid4(), operation='send', payload_hash='hash')
    with patch('game.chat_views.call_llm') as llm:
        response = post(auth_client, f'conversations/{adventure.conversation_id}/turns', {'message': 'Go', 'request_id': str(uuid.uuid4())})
        assert response.status_code == 409
        llm.assert_not_called()
    response = auth_client.post('/chat/api/send', json.dumps({'conversation_id': adventure.conversation_id, 'message': 'Go'}), content_type='application/json')
    assert response.status_code == 409


@pytest.mark.django_db
def test_failed_generation_is_not_retried_on_replay(auth_client, adventure):
    payload = {'message': 'Go', 'request_id': str(uuid.uuid4())}
    with patch('game.chat_views.call_llm', side_effect=Exception('Provider timeout with private details')) as llm:
        first = post(auth_client, f'conversations/{adventure.conversation_id}/turns', payload)
        second = post(auth_client, f'conversations/{adventure.conversation_id}/turns', payload)
        assert first.status_code == second.status_code == 504
        assert llm.call_count == 1
    assert 'private details' not in first.content.decode()
    assert first.json()['conversation']['pending_request_id'] is None


@pytest.mark.django_db
def test_changed_payload_cannot_reuse_request_id(auth_client, adventure):
    request_id = str(uuid.uuid4())
    with patch('game.chat_views.call_llm', return_value='Turn 1 of 10\nStory\n1) Left\n2) Right'):
        assert post(auth_client, f'conversations/{adventure.conversation_id}/turns', {'message': 'Go', 'request_id': request_id}).status_code == 200
        response = post(auth_client, f'conversations/{adventure.conversation_id}/turns', {'message': 'Wait', 'request_id': request_id})
        assert response.status_code == 409


@pytest.mark.django_db
def test_rollback_returns_authoritative_state(auth_client, adventure, configuration):
    ChatMessageFactory(conversation=adventure, role='user', content='Go')
    target = ChatMessageFactory(conversation=adventure, role='assistant', content='Turn 1 of 10\nSnow\n1) Enter\n2) Wait')
    ChatMessageFactory(conversation=adventure, role='user', content='Wait')
    ChatMessageFactory(conversation=adventure, role='assistant', content='Turn 2 of 10\nStorm\n1) Run\n2) Hide')
    GameSession.objects.create(user=adventure.user, session_id=adventure.conversation_id, configuration=configuration, turn_number=2, max_turns=10, game_over=True)
    response = post(auth_client, f'conversations/{adventure.conversation_id}/rollback', {'message_id': target.pk, 'request_id': str(uuid.uuid4())})
    assert response.status_code == 200
    result = response.json()['conversation']
    assert len(result['messages']) == 2
    assert result['state']['turn'] == 1
    assert result['state']['game_over'] is False
    assert result['state']['choices'] == ['Enter', 'Wait']


@pytest.mark.django_db
def test_blocked_refusal_survives_reload(auth_client, adventure):
    ChatMessageFactory(conversation=adventure, role='assistant', content='Cannot continue', metadata={'is_error': True})
    response = auth_client.get(BASE + f'conversations/{adventure.conversation_id}')
    assert response.json()['conversation']['state']['blocked'] is True
    assert post(auth_client, f'conversations/{adventure.conversation_id}/turns', {'message': 'Go', 'request_id': str(uuid.uuid4())}).status_code == 409



@pytest.mark.django_db
def test_malformed_request(auth_client, adventure):
    response = post(auth_client, f'conversations/{adventure.conversation_id}/turns', [])
    assert response.status_code == 400


@pytest.mark.django_db
def test_cannot_reuse_someone_elses_creation_id(auth_client, admin_user, configuration):
    other = ChatConversationFactory(user=admin_user)
    response = post(auth_client, 'conversations', {'request_id': other.conversation_id, 'config_id': configuration.pk})
    assert response.status_code == 404


@pytest.mark.django_db
def test_debug_requires_admin(auth_client, admin_client, adventure):
    path = BASE + f'conversations/{adventure.conversation_id}/debug'
    assert auth_client.get(path).status_code == 403
    assert admin_client.get(path).status_code == 200


@pytest.mark.django_db
def test_debug_records_model_calls_and_failure(admin_client, admin_user, configuration):
    adventure = ChatConversationFactory(user=admin_user, metadata={'config_id': configuration.pk})
    configuration.enable_refusal_detection = False
    configuration.save()
    path = f'conversations/{adventure.conversation_id}'
    with patch('game.chat_views.call_llm', return_value='Turn 1 of 10\nSnow.\n1) Enter\n2) Wait'):
        sent = post(admin_client, path + '/turns', {'message': 'Go', 'request_id': str(uuid.uuid4())})
    assert sent.status_code == 200
    message_id = sent.json()['conversation']['messages'][-1]['id']
    data = admin_client.get(BASE + path + f'/debug?message_id={message_id}').json()
    generation = next(step for step in data['steps'] if step['type'] == 'GenerateTurn')
    assert generation['input']['action'] == 'Go'
    assert generation['model_requests'][0]['output'].startswith('Turn 1')
    assert generation['model_requests'][0]['input']['system_prompt']
    assert data['steps'][-1]['status'] == 'completed'
    with patch('game.chat_views.call_llm', side_effect=RuntimeError('Provider unavailable')):
        failed = post(admin_client, path + '/turns', {'message': 'Wait', 'request_id': str(uuid.uuid4())})
    assert failed.status_code >= 400
    debug = admin_client.get(BASE + path + '/debug').json()
    assert debug['steps'][-1]['status'] == 'failed'
    assert debug['steps'][-1]['model_requests'][0]['error'] == 'Provider unavailable'

"""Admins can inspect player chats without acquiring permission to mutate them."""
import json
import uuid

import pytest

from django.contrib.auth.models import User
from game.models import AuditLog
from tests.conftest import ChatConversationFactory, ChatMessageFactory

pytestmark = pytest.mark.django_db
BASE = '/api/v1/chat/conversations/'


def test_only_admins_can_list_all_chats(client, auth_client, admin_client, user):
    chat = ChatConversationFactory(user=user, title='Lost in the woods')
    assert client.get('/api/v1/admin/chats').status_code == 401
    assert auth_client.get('/api/v1/admin/chats').status_code == 403
    rows = admin_client.get('/api/v1/admin/chats').json()['chats']
    assert rows[0]['id'] == chat.conversation_id
    assert rows[0]['owner'] == (user.email or user.username)


def test_search_and_pagination(admin_client):
    owner = User.objects.create_user(username='search-player', email='findme@example.com')
    target = ChatConversationFactory(user=owner, title='The secret garden')
    ChatConversationFactory.create_batch(50)
    first = admin_client.get('/api/v1/admin/chats').json()
    assert len(first['chats']) == 50 and first['has_more']
    second = admin_client.get('/api/v1/admin/chats?offset=50').json()
    assert len(second['chats']) == 1 and not second['has_more']
    assert not {c['id'] for c in first['chats']} & {c['id'] for c in second['chats']}
    for query in ['search-player', 'findme@example.com', 'secret garden', target.conversation_id]:
        rows = admin_client.get('/api/v1/admin/chats', {'search': query}).json()['chats']
        assert [c['id'] for c in rows] == [target.conversation_id]
    assert admin_client.get('/api/v1/admin/chats?offset=invalid').status_code == 400


def test_admin_reads_transcript_and_debug_without_mutation(admin_client, auth_client, user, configuration):
    chat = ChatConversationFactory(user=user, metadata={'config_id': configuration.pk})
    message = ChatMessageFactory(conversation=chat, role='assistant',
                                 content='Turn 1 of 10\nA path.\n1) Enter\n2) Wait',
                                 metadata={'pipeline_debug': [{'type': 'GenerateTurn', 'status': 'completed'}]})
    path = BASE + chat.conversation_id
    data = admin_client.get(path).json()['conversation']
    assert data['read_only'] and data['owner'] == (user.email or user.username)
    assert data['messages'][0]['id'] == message.pk
    assert not auth_client.get(path).json()['conversation'].get('read_only', False)
    debug = admin_client.get(path + '/debug', {'message_id': message.pk}).json()
    assert debug['steps'][0]['type'] == 'GenerateTurn'
    AuditLog.objects.create(original_text='', refined_text='', details={
        'type': 'workflow_error', 'conversation_id': chat.conversation_id,
        'pipeline_debug': [{'type': 'GenerateTurn', 'status': 'failed'}], 'error': 'Offline',
    })
    assert admin_client.get(path + '/debug').json()['error'] == 'Offline'
    other_message = ChatMessageFactory()
    assert admin_client.get(path + '/debug', {'message_id': other_message.pk}).status_code == 404
    for operation in ['turns', 'rollback']:
        response = admin_client.post(path + '/' + operation, json.dumps({
            'request_id': str(uuid.uuid4()), 'message': 'Go', 'message_id': message.pk,
        }), content_type='application/json')
        assert response.status_code == 404
    assert admin_client.delete(path).status_code == 404
    assert chat.messages.count() == 1


def test_players_cannot_read_or_debug_another_users_chat(auth_client):
    chat = ChatConversationFactory(user=User.objects.create_user(username='other-player'))
    assert auth_client.get(BASE + chat.conversation_id).status_code == 404
    assert auth_client.get(BASE + chat.conversation_id + '/debug').status_code == 403

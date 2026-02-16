"""
Tests for chat conversation CRUD APIs — auth required, user-scoped.
"""
import pytest
import json
import uuid

from game.models import ChatConversation, ChatMessage, GameSession
from tests.conftest import (
    ChatConversationFactory, ChatMessageFactory, GameSessionFactory,
)


# =============================================================================
# New Conversation
# =============================================================================

@pytest.mark.django_db
class TestNewConversationAPI:

    def test_requires_login(self, client):
        resp = client.post('/chat/api/new', content_type='application/json')
        assert resp.status_code == 302  # redirect to login

    def test_creates_new_conversation(self, auth_client):
        resp = auth_client.post(
            '/chat/api/new',
            data=json.dumps({}),
            content_type='application/json',
        )
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert 'conversation_id' in data
        assert 'title' in data
        uuid.UUID(data['conversation_id'])

    def test_creates_conversation_with_config(self, auth_client, db, configuration):
        resp = auth_client.post(
            '/chat/api/new',
            data=json.dumps({'config_id': configuration.id}),
            content_type='application/json',
        )
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert data['title'] == configuration.name

        conv = ChatConversation.objects.get(conversation_id=data['conversation_id'])
        assert conv.metadata.get('config_id') == configuration.id

    def test_handles_invalid_config_id(self, auth_client, db):
        resp = auth_client.post(
            '/chat/api/new',
            data=json.dumps({'config_id': 99999}),
            content_type='application/json',
        )
        assert resp.status_code == 200
        assert 'conversation_id' in json.loads(resp.content)

    def test_creates_conversation_with_empty_body(self, auth_client):
        resp = auth_client.post('/chat/api/new', content_type='application/json')
        assert resp.status_code == 200


# =============================================================================
# Get Conversation
# =============================================================================

@pytest.mark.django_db
class TestGetConversationAPI:

    def test_retrieves_own_conversation(self, auth_client, db, chat_conversation_with_messages):
        conv = chat_conversation_with_messages
        resp = auth_client.get(f'/chat/api/conversation/{conv.conversation_id}')
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert data['conversation_id'] == conv.conversation_id
        assert len(data['messages']) == 2

    def test_returns_404_for_missing(self, auth_client, db):
        resp = auth_client.get('/chat/api/conversation/nonexistent-uuid')
        assert resp.status_code == 404

    def test_cannot_access_other_users_conversation(self, auth_client, admin_client, db, user, admin_user):
        """A user cannot read another user's conversation."""
        conv = ChatConversationFactory(user=admin_user)
        resp = auth_client.get(f'/chat/api/conversation/{conv.conversation_id}')
        assert resp.status_code == 404

    def test_messages_ordered_by_time(self, auth_client, db, chat_conversation):
        ChatMessageFactory(conversation=chat_conversation, role='user', content='First')
        ChatMessageFactory(conversation=chat_conversation, role='assistant', content='Second')
        ChatMessageFactory(conversation=chat_conversation, role='user', content='Third')

        resp = auth_client.get(f'/chat/api/conversation/{chat_conversation.conversation_id}')
        data = json.loads(resp.content)
        assert [m['content'] for m in data['messages']] == ['First', 'Second', 'Third']


# =============================================================================
# List Conversations
# =============================================================================

@pytest.mark.django_db
class TestListConversationsAPI:

    def test_lists_own_conversations(self, auth_client, db, user):
        ChatConversationFactory(user=user)
        ChatConversationFactory(user=user)
        ChatConversationFactory(user=user)

        resp = auth_client.get('/chat/api/conversations')
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert len(data['conversations']) == 3

    def test_does_not_list_other_users(self, auth_client, db, user, admin_user):
        ChatConversationFactory(user=user)
        ChatConversationFactory(user=admin_user)

        resp = auth_client.get('/chat/api/conversations')
        data = json.loads(resp.content)
        assert len(data['conversations']) == 1

    def test_includes_message_count(self, auth_client, db, chat_conversation_with_messages):
        resp = auth_client.get('/chat/api/conversations')
        data = json.loads(resp.content)
        conv_data = next(
            c for c in data['conversations']
            if c['conversation_id'] == chat_conversation_with_messages.conversation_id
        )
        assert conv_data['message_count'] == 2

    def test_limits_to_50_conversations(self, auth_client, db, user):
        for _ in range(60):
            ChatConversationFactory(user=user)
        resp = auth_client.get('/chat/api/conversations')
        data = json.loads(resp.content)
        assert len(data['conversations']) == 50


# =============================================================================
# Delete Conversation
# =============================================================================

@pytest.mark.django_db
class TestDeleteConversationAPI:

    def test_marks_game_as_over(self, auth_client, db, user, configuration):
        gs = GameSessionFactory(user=user, configuration=configuration)
        assert gs.game_over is False

        resp = auth_client.post(f'/chat/api/delete/{gs.session_id}')
        assert resp.status_code == 200
        assert json.loads(resp.content)['success'] is True
        gs.refresh_from_db()
        assert gs.game_over is True

    def test_returns_404_for_missing(self, auth_client, db):
        resp = auth_client.post('/chat/api/delete/nonexistent-id')
        assert resp.status_code == 404

    def test_cannot_delete_other_users_game(self, auth_client, db, admin_user, configuration):
        gs = GameSessionFactory(user=admin_user, configuration=configuration)
        resp = auth_client.post(f'/chat/api/delete/{gs.session_id}')
        assert resp.status_code == 404

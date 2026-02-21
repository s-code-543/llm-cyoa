"""
Tests for the chat rollback API — rolling back to a previous assistant turn.
"""
import pytest
import json

from game.models import ChatMessage
from tests.conftest import (
    ChatConversationFactory, ChatMessageFactory, GameSessionFactory,
)


def _build_conversation(user, config=None, turns=3, game_over=False):
    """
    Helper: build a conversation with N full turns (user + assistant pairs).
    Returns (conversation, game_session, messages_list).
    """
    conv = ChatConversationFactory(user=user)
    msgs = []
    for t in range(1, turns + 1):
        u = ChatMessageFactory(
            conversation=conv,
            role='user',
            content=f'Choice for turn {t}',
        )
        a = ChatMessageFactory(
            conversation=conv,
            role='assistant',
            content=f'**Turn {t} of 10**\n\nSomething exciting.\n\n1) Go left\n2) Go right',
        )
        msgs.extend([u, a])

    gs = GameSessionFactory(
        user=user,
        session_id=conv.conversation_id,
        turn_number=turns,
        max_turns=10,
        game_over=game_over,
        last_death_roll=0.42 if game_over else None,
        last_death_probability=0.35 if game_over else None,
        configuration=config,
    )
    return conv, gs, msgs


# =============================================================================
# Rollback endpoint — happy paths
# =============================================================================

@pytest.mark.django_db
class TestRollbackHappyPath:

    def test_rollback_deletes_later_messages(self, auth_client, user, configuration):
        conv, gs, msgs = _build_conversation(user, configuration, turns=3)
        # Roll back to assistant msg of turn 1 (index 1 in msgs list)
        target = msgs[1]  # first assistant message
        assert target.role == 'assistant'

        resp = auth_client.post(
            '/chat/api/rollback',
            data=json.dumps({
                'conversation_id': conv.conversation_id,
                'message_id': target.id,
            }),
            content_type='application/json',
        )
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert data['success'] is True
        assert data['deleted_count'] == 4  # user2, asst2, user3, asst3

        remaining = ChatMessage.objects.filter(conversation=conv).order_by('id')
        assert remaining.count() == 2
        assert remaining.last().id == target.id

    def test_rollback_resets_game_session(self, auth_client, user, configuration):
        conv, gs, msgs = _build_conversation(user, configuration, turns=3, game_over=True)
        target = msgs[1]  # turn 1 assistant

        resp = auth_client.post(
            '/chat/api/rollback',
            data=json.dumps({
                'conversation_id': conv.conversation_id,
                'message_id': target.id,
            }),
            content_type='application/json',
        )
        assert resp.status_code == 200

        gs.refresh_from_db()
        assert gs.game_over is False
        assert gs.turn_number == 1  # only 1 user message remains
        assert gs.last_death_roll is None
        assert gs.last_death_probability is None

    def test_rollback_returns_updated_messages(self, auth_client, user, configuration):
        conv, gs, msgs = _build_conversation(user, configuration, turns=3)
        target = msgs[3]  # turn 2 assistant

        resp = auth_client.post(
            '/chat/api/rollback',
            data=json.dumps({
                'conversation_id': conv.conversation_id,
                'message_id': target.id,
            }),
            content_type='application/json',
        )
        data = json.loads(resp.content)
        assert len(data['messages']) == 4  # user1, asst1, user2, asst2
        # Every message has an id
        assert all('id' in m for m in data['messages'])

    def test_rollback_returns_game_state(self, auth_client, user, configuration):
        conv, gs, msgs = _build_conversation(user, configuration, turns=3)
        target = msgs[3]  # turn 2 assistant (**Turn 2 of 10**)

        resp = auth_client.post(
            '/chat/api/rollback',
            data=json.dumps({
                'conversation_id': conv.conversation_id,
                'message_id': target.id,
            }),
            content_type='application/json',
        )
        data = json.loads(resp.content)
        assert data['state']['turn_current'] == 2
        assert data['state']['turn_max'] == 10
        assert data['state']['choice1'] == 'Go left'
        assert data['state']['choice2'] == 'Go right'

    def test_rollback_to_last_message_is_noop(self, auth_client, user, configuration):
        conv, gs, msgs = _build_conversation(user, configuration, turns=2)
        target = msgs[-1]  # last assistant msg

        resp = auth_client.post(
            '/chat/api/rollback',
            data=json.dumps({
                'conversation_id': conv.conversation_id,
                'message_id': target.id,
            }),
            content_type='application/json',
        )
        data = json.loads(resp.content)
        assert data['success'] is True
        assert data['deleted_count'] == 0
        assert len(data['messages']) == 4


# =============================================================================
# Rollback endpoint — error cases
# =============================================================================

@pytest.mark.django_db
class TestRollbackErrors:

    def test_requires_login(self, client):
        resp = client.post(
            '/chat/api/rollback',
            data=json.dumps({'conversation_id': 'x', 'message_id': 1}),
            content_type='application/json',
        )
        assert resp.status_code == 302

    def test_missing_params(self, auth_client):
        resp = auth_client.post(
            '/chat/api/rollback',
            data=json.dumps({}),
            content_type='application/json',
        )
        assert resp.status_code == 400

    def test_nonexistent_conversation(self, auth_client, db):
        resp = auth_client.post(
            '/chat/api/rollback',
            data=json.dumps({
                'conversation_id': 'nonexistent',
                'message_id': 99999,
            }),
            content_type='application/json',
        )
        assert resp.status_code == 404

    def test_cannot_rollback_other_users_conversation(self, auth_client, admin_user, db, configuration):
        conv, gs, msgs = _build_conversation(admin_user, configuration, turns=2)
        target = msgs[1]

        resp = auth_client.post(
            '/chat/api/rollback',
            data=json.dumps({
                'conversation_id': conv.conversation_id,
                'message_id': target.id,
            }),
            content_type='application/json',
        )
        assert resp.status_code == 404

    def test_cannot_rollback_to_user_message(self, auth_client, user, configuration):
        conv, gs, msgs = _build_conversation(user, configuration, turns=2)
        user_msg = msgs[0]  # first user message

        resp = auth_client.post(
            '/chat/api/rollback',
            data=json.dumps({
                'conversation_id': conv.conversation_id,
                'message_id': user_msg.id,
            }),
            content_type='application/json',
        )
        assert resp.status_code == 404

    def test_cannot_rollback_to_message_from_different_conversation(self, auth_client, user, configuration):
        conv1, gs1, msgs1 = _build_conversation(user, configuration, turns=2)
        conv2, gs2, msgs2 = _build_conversation(user, configuration, turns=2)

        resp = auth_client.post(
            '/chat/api/rollback',
            data=json.dumps({
                'conversation_id': conv1.conversation_id,
                'message_id': msgs2[1].id,  # assistant from conv2
            }),
            content_type='application/json',
        )
        assert resp.status_code == 404


    def test_error_logged_to_audit(self, auth_client, user):
        """Errors should be logged to AuditLog so they're visible in admin GUI."""
        from game.models import AuditLog
        
        # Malformed JSON should create an audit log entry
        resp = auth_client.post(
            '/chat/api/rollback',
            data='{"invalid": json}',  # Invalid JSON
            content_type='application/json',
        )
        assert resp.status_code == 400
        
        # Check that error was logged to audit
        audit_logs = AuditLog.objects.filter(
            details__type='error',
            details__operation='rollback',
            details__error_type='json_decode'
        )
        assert audit_logs.exists()
        log = audit_logs.first()
        assert 'JSON decode error' in log.refined_text
        assert log.was_modified is False


# =============================================================================
# Rollback with error messages (game_blocked scenarios)
# =============================================================================

@pytest.mark.django_db
class TestRollbackPastErrorMessages:

    def test_rollback_past_error_message_unblocks_game(self, auth_client, user, configuration):
        """Rolling back past an error message should reset game state cleanly."""
        conv, gs, msgs = _build_conversation(user, configuration, turns=2)

        # Add an error message (simulating a refusal)
        user_msg = ChatMessageFactory(
            conversation=conv, role='user', content='Do something risky',
        )
        error_msg = ChatMessageFactory(
            conversation=conv, role='assistant',
            content='The AI refused to play',
            metadata={'is_error': True, 'refusal_info': {'was_refusal': True}},
        )

        # Roll back to turn 2 assistant (before the error)
        target = msgs[3]  # turn 2 assistant

        resp = auth_client.post(
            '/chat/api/rollback',
            data=json.dumps({
                'conversation_id': conv.conversation_id,
                'message_id': target.id,
            }),
            content_type='application/json',
        )
        data = json.loads(resp.content)
        assert data['success'] is True
        assert data['deleted_count'] == 2  # user_msg + error_msg

        # Error message is gone
        remaining = ChatMessage.objects.filter(conversation=conv)
        assert not remaining.filter(metadata__is_error=True).exists()


# =============================================================================
# Message ID in API responses
# =============================================================================

@pytest.mark.django_db
class TestMessageIdInResponses:

    def test_get_conversation_includes_message_ids(self, auth_client, db, chat_conversation_with_messages):
        conv = chat_conversation_with_messages
        resp = auth_client.get(f'/chat/api/conversation/{conv.conversation_id}')
        data = json.loads(resp.content)
        for msg in data['messages']:
            assert 'id' in msg
            assert isinstance(msg['id'], int)

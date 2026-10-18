"""
Tests for the send-message endpoint — LLM calls, refusal, judge pipeline.
All tests use auth_client (logged-in user).
"""
import pytest
import json
from unittest.mock import patch

from game.models import ChatConversation, ChatMessage, GameSession, AuditLog
from tests.conftest import (
    ChatConversationFactory, SAMPLE_VALID_TURN,
    SAMPLE_REFUSAL_TURN, SAMPLE_CORRECTED_TURN,
    SAMPLE_CLASSIFIER_YES,
)


SAMPLE_TURN_1 = (
    "**Turn 1 of 10**\n\n"
    "You awaken in a cold, damp cell.\n\n"
    "**Your choices:**\n"
    "1) Grab the key and try to unlock the cell door\n"
    "2) Call out to whoever is approaching\n\n"
    "**Inventory:** tattered clothes"
)

SAMPLE_TURN_3 = (
    "**Turn 3 of 10**\n\n"
    "The ancient door creaks open, revealing a dimly lit chamber.\n\n"
    "**Your choices:**\n"
    "1) Follow the narrow corridor into the depths\n"
    "2) Climb the spiral staircase toward the light\n\n"
    "**Inventory:** rusty key, torch, 3 gold coins"
)

NO_REFUSAL = {
    'was_refusal': False,
    'classifier_response': '',
    'was_corrected': False,
}

NO_JUDGE = {
    'was_modified': False,
    'steps': [],
}


def _mock_stack(mock_llm, mock_refusal, mock_judge, turn_text):
    """Configure the three mocks for a normal (no-refusal, no-judge-edit) turn."""
    mock_llm.return_value = turn_text
    mock_refusal.return_value = {'final_turn': turn_text, **NO_REFUSAL}
    mock_judge.return_value = {'final_turn': turn_text, **NO_JUDGE}


# =============================================================================
# Basic send-message
# =============================================================================

@pytest.mark.django_db
class TestSendMessageAPI:

    def test_requires_login(self, client):
        resp = client.post(
            '/chat/api/send',
            data=json.dumps({'conversation_id': 'x', 'message': 'hi'}),
            content_type='application/json',
        )
        assert resp.status_code == 302

    def test_requires_conversation_id(self, auth_client):
        resp = auth_client.post(
            '/chat/api/send',
            data=json.dumps({'message': 'Hello'}),
            content_type='application/json',
        )
        assert resp.status_code == 400

    def test_requires_message(self, auth_client, db, chat_conversation):
        resp = auth_client.post(
            '/chat/api/send',
            data=json.dumps({'conversation_id': chat_conversation.conversation_id}),
            content_type='application/json',
        )
        assert resp.status_code == 400

    @patch('game.chat_views.run_judge_pipeline')
    @patch('game.chat_views.process_potential_refusal')
    @patch('game.chat_views.call_llm')
    def test_sends_message_and_gets_response(
        self, mock_llm, mock_refusal, mock_judge,
        auth_client, db, user, full_configuration,
    ):
        _mock_stack(mock_llm, mock_refusal, mock_judge, SAMPLE_TURN_1)
        conv = ChatConversationFactory(user=user, metadata={'config_id': full_configuration.id})

        resp = auth_client.post(
            '/chat/api/send',
            data=json.dumps({'conversation_id': conv.conversation_id, 'message': 'Start the adventure!'}),
            content_type='application/json',
        )
        assert resp.status_code == 200
        data = json.loads(resp.content)
        assert data['message']['role'] == 'assistant'
        assert 'Turn 1 of 10' in data['message']['content']
        assert 'state' in data

    @patch('game.chat_views.run_judge_pipeline')
    @patch('game.chat_views.process_potential_refusal')
    @patch('game.chat_views.call_llm')
    def test_extracts_game_state(
        self, mock_llm, mock_refusal, mock_judge,
        auth_client, db, user, full_configuration,
    ):
        _mock_stack(mock_llm, mock_refusal, mock_judge, SAMPLE_TURN_3)
        conv = ChatConversationFactory(user=user, metadata={'config_id': full_configuration.id})

        resp = auth_client.post(
            '/chat/api/send',
            data=json.dumps({'conversation_id': conv.conversation_id, 'message': 'I choose option 1'}),
            content_type='application/json',
        )
        state = json.loads(resp.content)['state']
        assert state['turn_current'] == 1
        assert state['turn_max'] == 10

    @patch('game.chat_views.run_judge_pipeline')
    @patch('game.chat_views.process_potential_refusal')
    @patch('game.chat_views.call_llm')
    def test_creates_game_session(
        self, mock_llm, mock_refusal, mock_judge,
        auth_client, db, user, full_configuration,
    ):
        _mock_stack(mock_llm, mock_refusal, mock_judge, SAMPLE_TURN_1)
        conv = ChatConversationFactory(user=user, metadata={'config_id': full_configuration.id})

        resp = auth_client.post(
            '/chat/api/send',
            data=json.dumps({'conversation_id': conv.conversation_id, 'message': 'Begin!'}),
            content_type='application/json',
        )
        assert resp.status_code == 200
        session = GameSession.objects.get(session_id=conv.conversation_id)
        assert session.configuration == full_configuration
        assert session.user == user
        assert session.game_over is False

    @patch('game.chat_views.run_judge_pipeline')
    @patch('game.chat_views.process_potential_refusal')
    @patch('game.chat_views.call_llm')
    def test_saves_messages(
        self, mock_llm, mock_refusal, mock_judge,
        auth_client, db, user, full_configuration,
    ):
        _mock_stack(mock_llm, mock_refusal, mock_judge, SAMPLE_TURN_1)
        conv = ChatConversationFactory(user=user, metadata={'config_id': full_configuration.id})

        auth_client.post(
            '/chat/api/send',
            data=json.dumps({'conversation_id': conv.conversation_id, 'message': 'Start adventure!'}),
            content_type='application/json',
        )
        msgs = ChatMessage.objects.filter(conversation=conv)
        assert msgs.count() == 2
        assert msgs.filter(role='user').first().content == 'Start adventure!'
        assert 'Turn 1 of 10' in msgs.filter(role='assistant').first().content

    def test_returns_error_without_config(self, auth_client, db, user):
        conv = ChatConversationFactory(user=user)
        resp = auth_client.post(
            '/chat/api/send',
            data=json.dumps({'conversation_id': conv.conversation_id, 'message': 'Hello'}),
            content_type='application/json',
        )
        assert resp.status_code == 500


# =============================================================================
# Refusal detection
# =============================================================================

@pytest.mark.django_db
class TestRefusalDetection:

    @patch('game.chat_views.run_judge_pipeline')
    @patch('game.chat_views.process_potential_refusal')
    @patch('game.chat_views.call_llm')
    def test_detects_and_corrects_refusal(
        self, mock_llm, mock_refusal, mock_judge,
        auth_client, db, user, full_configuration,
    ):
        mock_llm.return_value = SAMPLE_REFUSAL_TURN
        mock_refusal.return_value = {
            'final_turn': SAMPLE_CORRECTED_TURN,
            'was_refusal': True,
            'classifier_response': SAMPLE_CLASSIFIER_YES,
            'was_corrected': True,
        }
        mock_judge.return_value = {'final_turn': SAMPLE_CORRECTED_TURN, **NO_JUDGE}

        conv = ChatConversationFactory(user=user, metadata={'config_id': full_configuration.id})
        resp = auth_client.post(
            '/chat/api/send',
            data=json.dumps({'conversation_id': conv.conversation_id, 'message': 'Attack!'}),
            content_type='application/json',
        )
        data = json.loads(resp.content)
        assert data['message']['refusal_info']['was_refusal'] is True
        assert data['message']['refusal_info']['was_corrected'] is True

    @patch('game.chat_views.run_judge_pipeline')
    @patch('game.chat_views.process_potential_refusal')
    @patch('game.chat_views.call_llm')
    def test_refusal_creates_audit_log(
        self, mock_llm, mock_refusal, mock_judge,
        auth_client, db, user, full_configuration,
    ):
        mock_llm.return_value = SAMPLE_REFUSAL_TURN
        mock_refusal.return_value = {
            'final_turn': SAMPLE_CORRECTED_TURN,
            'was_refusal': True,
            'classifier_response': SAMPLE_CLASSIFIER_YES,
            'was_corrected': True,
        }
        mock_judge.return_value = {'final_turn': SAMPLE_CORRECTED_TURN, **NO_JUDGE}

        conv = ChatConversationFactory(user=user, metadata={'config_id': full_configuration.id})
        auth_client.post(
            '/chat/api/send',
            data=json.dumps({'conversation_id': conv.conversation_id, 'message': 'Attack!'}),
            content_type='application/json',
        )
        audit = AuditLog.objects.filter(was_refusal=True).first()
        assert audit is not None
        assert audit.was_modified is True

    @patch('game.chat_views.run_judge_pipeline')
    @patch('game.chat_views.process_potential_refusal')
    @patch('game.chat_views.call_llm')
    def test_turn_1_refusal_blocks_game(
        self, mock_llm, mock_refusal, mock_judge,
        auth_client, db, user, full_configuration,
    ):
        mock_llm.return_value = SAMPLE_REFUSAL_TURN
        mock_refusal.return_value = {
            'final_turn': SAMPLE_REFUSAL_TURN,
            'was_refusal': True,
            'classifier_response': SAMPLE_CLASSIFIER_YES,
            'was_corrected': False,
            'turn_1_refusal': True,
            'all_attempts_failed': False,
            'attempts': [],
        }
        conv = ChatConversationFactory(user=user, metadata={'config_id': full_configuration.id})
        resp = auth_client.post(
            '/chat/api/send',
            data=json.dumps({'conversation_id': conv.conversation_id, 'message': 'Start violent adventure!'}),
            content_type='application/json',
        )
        data = json.loads(resp.content)
        assert data.get('game_blocked') is True
        assert 'petulant child' in data['message']['content']


# =============================================================================
# Judge pipeline
# =============================================================================

@pytest.mark.django_db
class TestJudgePipelineInChat:

    @patch('game.chat_views.run_judge_pipeline')
    @patch('game.chat_views.process_potential_refusal')
    @patch('game.chat_views.call_llm')
    def test_runs_judge_pipeline(
        self, mock_llm, mock_refusal, mock_judge,
        auth_client, db, user, full_configuration,
    ):
        mock_llm.return_value = SAMPLE_TURN_1
        mock_refusal.return_value = {'final_turn': SAMPLE_TURN_1, **NO_REFUSAL}
        mock_judge.return_value = {
            'final_turn': SAMPLE_TURN_1,
            'was_modified': False,
            'steps': [{'step_id': 1, 'name': 'test', 'final_used': 'original'}],
        }
        conv = ChatConversationFactory(user=user, metadata={'config_id': full_configuration.id})
        resp = auth_client.post(
            '/chat/api/send',
            data=json.dumps({'conversation_id': conv.conversation_id, 'message': 'Begin'}),
            content_type='application/json',
        )
        data = json.loads(resp.content)
        mock_judge.assert_called_once()
        assert data['message']['judge_info'] is not None

    @patch('game.chat_views.run_judge_pipeline')
    @patch('game.chat_views.process_potential_refusal')
    @patch('game.chat_views.call_llm')
    def test_judge_modification_creates_audit(
        self, mock_llm, mock_refusal, mock_judge,
        auth_client, db, user, full_configuration,
    ):
        original = "**Turn 1 of 10**\n\nOriginal content\n\n1) A\n2) B"
        modified = "**Turn 1 of 10**\n\nModified content\n\n1) A\n2) B"
        mock_llm.return_value = original
        mock_refusal.return_value = {'final_turn': original, **NO_REFUSAL}
        mock_judge.return_value = {
            'final_turn': modified,
            'was_modified': True,
            'steps': [{'step_id': 1, 'name': 'test', 'final_used': 'rewrite'}],
        }
        conv = ChatConversationFactory(user=user, metadata={'config_id': full_configuration.id})
        auth_client.post(
            '/chat/api/send',
            data=json.dumps({'conversation_id': conv.conversation_id, 'message': 'Go'}),
            content_type='application/json',
        )
        audit = AuditLog.objects.filter(was_modified=True, was_refusal=False).first()
        assert audit is not None


@pytest.mark.django_db
class TestTurnCorrectness:
    def send(self, client, conv):
        return client.post('/chat/api/send', json.dumps({
            'conversation_id': conv.conversation_id, 'message': 'Continue'
        }), content_type='application/json')

    def test_full_history_and_turn_count_past_ten(self, auth_client, user, configuration):
        configuration.enable_refusal_detection = False
        configuration.total_turns = 20
        configuration.save()
        conv = ChatConversationFactory(user=user, metadata={'config_id': configuration.pk})
        for n in range(12):
            ChatMessage.objects.create(conversation=conv, role='user', content=f'Action {n}')
            ChatMessage.objects.create(conversation=conv, role='assistant', content=f'Turn {n+1} of 20\nStory\n1) A\n2) B')
        with patch('game.chat_views.call_llm', return_value='Turn 13 of 20\nStory\n1) A\n2) B') as llm:
            assert self.send(auth_client, conv).status_code == 200
        assert len(llm.call_args.kwargs['messages']) == 25
        assert llm.call_args.kwargs['messages'][0]['content'] == 'Action 0'
        assert GameSession.objects.get(session_id=conv.conversation_id).turn_number == 13

    def test_failed_death_generation_preserves_session(self, auth_client, user, full_configuration):
        conv = ChatConversationFactory(user=user, metadata={'config_id': full_configuration.pk})
        ChatMessage.objects.create(conversation=conv, role='user', content='Start')
        ChatMessage.objects.create(conversation=conv, role='assistant', content=SAMPLE_TURN_1)
        session = GameSession.objects.create(user=user, session_id=conv.conversation_id,
                                            configuration=full_configuration, turn_number=1, max_turns=10)
        with patch('game.difficulty_utils.random.random', return_value=0), patch(
            'game.chat_views.call_llm', side_effect=Exception('timeout')
        ):
            assert self.send(auth_client, conv).status_code == 500
        session.refresh_from_db()
        assert session.turn_number == 1
        assert session.game_over is False
        assert session.last_death_roll is None
        assert conv.messages.count() == 2

    def test_first_generation_failure_creates_no_session_or_messages(self, auth_client, user, configuration):
        conv = ChatConversationFactory(user=user, metadata={'config_id': configuration.pk})
        with patch('game.chat_views.call_llm', side_effect=Exception('timeout')):
            assert self.send(auth_client, conv).status_code == 500
        assert not GameSession.objects.filter(session_id=conv.conversation_id).exists()
        assert not conv.messages.exists()

    @pytest.mark.parametrize('marker', ['GAME OVER', '**THE END**', 'VICTORY'])
    def test_early_endings_finish_and_skip_rewrites(self, auth_client, user, configuration, marker):
        configuration.enable_refusal_detection = False
        configuration.save()
        conv = ChatConversationFactory(user=user, metadata={'config_id': configuration.pk})
        with patch('game.chat_views.call_llm', return_value=f'Turn 1 of 10\nYour adventure ends.\n{marker}'), patch(
            'game.chat_views.run_judge_pipeline'
        ) as judge:
            response = self.send(auth_client, conv)
        assert response.status_code == 200
        judge.assert_not_called()
        assert GameSession.objects.get(session_id=conv.conversation_id).game_over
        assert response.json()['state']['game_over']
        assert self.send(auth_client, conv).status_code == 409

    def test_incidental_ending_words_do_not_end_game(self):
        from game.chat_views import is_story_ending
        assert not is_story_ending('You fear this could be game over.\n1) Run\n2) Hide')

    def test_commit_failure_rolls_back_messages_and_session(self, auth_client, user, configuration):
        configuration.enable_refusal_detection = False
        configuration.save()
        conv = ChatConversationFactory(user=user, metadata={'config_id': configuration.pk})
        with patch('game.chat_views.call_llm', return_value=SAMPLE_TURN_1), patch(
            'game.chat_views.GameSession.save', side_effect=Exception('database failure')
        ):
            assert self.send(auth_client, conv).status_code == 500
        assert not conv.messages.exists()
        assert not GameSession.objects.filter(session_id=conv.conversation_id).exists()

    def test_random_death_is_not_undone_by_judge(self, auth_client, user, full_configuration):
        full_configuration.enable_refusal_detection = False
        full_configuration.save()
        conv = ChatConversationFactory(user=user, metadata={'config_id': full_configuration.pk})
        ChatMessage.objects.create(conversation=conv, role='user', content='Start')
        ChatMessage.objects.create(conversation=conv, role='assistant', content=SAMPLE_TURN_1)
        with patch('game.difficulty_utils.random.random', return_value=0), patch(
            'game.chat_views.call_llm', return_value='You slip and die.\nGAME OVER'
        ), patch('game.chat_views.run_judge_pipeline') as judge:
            response = self.send(auth_client, conv)
        assert response.status_code == 200
        judge.assert_not_called()
        session = GameSession.objects.get(session_id=conv.conversation_id)
        assert session.game_over
        assert session.last_death_roll == 0
        assert session.turn_number == 2

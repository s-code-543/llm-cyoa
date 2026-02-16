"""
Tests for home page and chat page views — auth required.
"""
import pytest
import json

from game.models import GameSession
from tests.conftest import ChatConversationFactory, GameSessionFactory


@pytest.mark.django_db
class TestHomePage:

    def test_redirects_when_not_logged_in(self, client):
        resp = client.get('/')
        assert resp.status_code == 302

    def test_home_page_loads(self, auth_client):
        resp = auth_client.get('/')
        assert resp.status_code == 200

    def test_shows_recent_games(self, auth_client, db, user, configuration):
        conv = ChatConversationFactory(user=user)
        GameSessionFactory(
            user=user,
            session_id=conv.conversation_id,
            configuration=configuration,
            game_over=False,
            turn_number=5,
        )
        resp = auth_client.get('/')
        assert resp.status_code == 200
        assert 'recent_games' in resp.context

    def test_only_shows_own_games(self, auth_client, db, user, admin_user, configuration):
        # admin's game — should not appear
        other_conv = ChatConversationFactory(user=admin_user)
        GameSessionFactory(
            user=admin_user,
            session_id=other_conv.conversation_id,
            configuration=configuration,
            game_over=False,
        )
        resp = auth_client.get('/')
        assert len(resp.context['recent_games']) == 0

    def test_shows_configurations(self, auth_client, db, configuration):
        resp = auth_client.get('/')
        assert resp.status_code == 200
        assert len(resp.context['configurations']) >= 1


@pytest.mark.django_db
class TestChatPage:

    def test_redirects_when_not_logged_in(self, client):
        resp = client.get('/chat/')
        assert resp.status_code == 302

    def test_chat_page_loads(self, auth_client):
        resp = auth_client.get('/chat/')
        assert resp.status_code == 200


@pytest.mark.django_db
@pytest.mark.integration
class TestFullGameFlow:

    @pytest.fixture(autouse=True)
    def _setup(self, auth_client, db, user, full_configuration):
        self.client = auth_client
        self.user = user
        self.config = full_configuration

    def _post_json(self, url, payload):
        return self.client.post(url, data=json.dumps(payload), content_type='application/json')

    @pytest.mark.django_db
    def test_complete_game_flow(self):
        from unittest.mock import patch

        turns = [
            "**Turn 1 of 3**\n\nStart!\n\n1) Go\n2) Stay",
            "**Turn 2 of 3**\n\nMiddle!\n\n1) Left\n2) Right",
            "**Turn 3 of 3**\n\nEnd!\n\n**VICTORY!**",
        ]
        no = {'was_refusal': False, 'classifier_response': '', 'was_corrected': False}

        self.config.total_turns = 3
        self.config.save()

        with (
            patch('game.chat_views.call_llm', side_effect=turns),
            patch('game.chat_views.process_potential_refusal',
                  side_effect=[{'final_turn': t, **no} for t in turns]),
            patch('game.chat_views.run_judge_pipeline',
                  side_effect=[{'final_turn': t, 'was_modified': False, 'steps': []} for t in turns]),
        ):
            r = self._post_json('/chat/api/new', {'config_id': self.config.id})
            conv_id = json.loads(r.content)['conversation_id']

            for i, msg in enumerate(['Start!', '1', '2'], start=1):
                r = self._post_json('/chat/api/send', {'conversation_id': conv_id, 'message': msg})
                assert r.status_code == 200
                assert json.loads(r.content)['state']['turn_current'] == i

        session = GameSession.objects.get(session_id=conv_id)
        assert session.game_over is True
        assert session.user == self.user

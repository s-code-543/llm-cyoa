"""
Tests for the React app shell, session API and home API.
"""
import json

from django.test import override_settings
import pytest

from game.models import GameSession
from tests.conftest import ChatConversationFactory, GameSessionFactory


@pytest.mark.django_db
class TestAppShell:

    @override_settings(FRONTEND_DEV=True)
    @pytest.mark.parametrize('path', ['/', '/login', '/chat', '/chat/', '/manage/', '/manage/prompts/3'])
    def test_shell_served_without_login(self, client, path):
        resp = client.get(path)
        assert resp.status_code == 200
        assert 'app/shell.html' in [t.name for t in resp.templates]
        assert b'js/recorder.js' in resp.content


@pytest.mark.django_db
class TestSessionApi:

    def test_anonymous(self, client):
        data = client.get('/api/v1/session').json()
        assert data['user'] is None and data['permissions'] == []

    def test_player_permissions(self, auth_client):
        assert auth_client.get('/api/v1/session').json()['permissions'] == ['play']

    def test_admin_permissions(self, admin_client):
        assert admin_client.get('/api/v1/session').json()['permissions'] == ['play', 'admin']

    def test_login_and_logout(self, client, user):
        post = lambda url, body: client.post(url, json.dumps(body), content_type='application/json')
        assert post('/api/v1/session/login', {'username': user.username, 'password': 'nope'}).status_code == 401
        assert post('/api/v1/session/login', {'username': user.username}).status_code == 400
        resp = post('/api/v1/session/login', {'username': user.username, 'password': 'testpass123'})
        assert resp.status_code == 200 and resp.json()['permissions'] == ['play']
        assert client.get('/api/v1/session').json()['user']['username'] == user.username
        assert post('/api/v1/session/logout', {}).json()['user'] is None
        assert client.get('/api/v1/session').json()['user'] is None


@pytest.mark.django_db
class TestHomeApi:

    def test_requires_login(self, client):
        assert client.get('/api/v1/home').status_code == 401

    def test_shows_recent_games(self, auth_client, user, configuration):
        conv = ChatConversationFactory(user=user)
        GameSessionFactory(user=user, session_id=conv.conversation_id, configuration=configuration,
                           game_over=False, turn_number=5)
        data = auth_client.get('/api/v1/home').json()
        assert [g['id'] for g in data['recent_games']] == [conv.conversation_id]
        assert data['recent_games'][0]['turn'] == 5

    def test_only_shows_own_games(self, auth_client, admin_user, configuration):
        other = ChatConversationFactory(user=admin_user)
        GameSessionFactory(user=admin_user, session_id=other.conversation_id, configuration=configuration,
                           game_over=False)
        assert auth_client.get('/api/v1/home').json()['recent_games'] == []

    def test_lists_configurations(self, auth_client, configuration):
        names = [c['name'] for c in auth_client.get('/api/v1/home').json()['configurations']]
        assert configuration.name in names

    def test_delete_ends_own_game_only(self, auth_client, user, admin_user, configuration):
        mine = ChatConversationFactory(user=user)
        GameSessionFactory(user=user, session_id=mine.conversation_id, configuration=configuration, game_over=False)
        theirs = ChatConversationFactory(user=admin_user)
        assert auth_client.delete(f'/api/v1/chat/conversations/{theirs.conversation_id}').status_code == 404
        assert auth_client.delete(f'/api/v1/chat/conversations/{mine.conversation_id}').status_code == 200
        assert GameSession.objects.get(session_id=mine.conversation_id).game_over is True



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

        # This fixture scripts a surviving playthrough; random-death behavior has separate tests.
        self.config.difficulty = None
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

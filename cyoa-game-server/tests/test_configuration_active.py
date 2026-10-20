"""Publication controls and explanations for saved, unplayable adventures."""
import uuid
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from game.admin_config_api import config_json
from game.config_utils import configuration_unavailable_reason, get_conversation_configuration
from tests.conftest import ConfigurationFactory, ChatConversationFactory, GameSessionFactory, JudgeStepFactory

pytestmark = pytest.mark.django_db


def test_active_status_and_impact_count():
    config = ConfigurationFactory(is_active=False)
    GameSessionFactory(configuration=config)
    GameSessionFactory(configuration=config, game_over=True)
    assert config_json(config)['is_active'] is False
    assert config_json(config)['in_progress_count'] == 1
    assert 'disabled' in configuration_unavailable_reason(config)
    config.is_active = True
    assert configuration_unavailable_reason(config) is None
    config.storyteller_model.is_available = False
    config.storyteller_model.save()
    assert 'models' in configuration_unavailable_reason(config)


@pytest.mark.parametrize('endpoint', ['/api/v1/home', '/api/v1/chat/bootstrap'])
def test_inactive_not_offered(auth_client, endpoint):
    inactive = ConfigurationFactory(is_active=False)
    active = ConfigurationFactory()
    ids = [c['id'] for c in auth_client.get(endpoint).json()['configurations']]
    assert inactive.pk not in ids
    assert active.pk in ids


def test_disabled_cannot_start(auth_client):
    config = ConfigurationFactory(is_active=False)
    response = auth_client.post('/api/v1/chat/conversations', {
        'config_id': config.pk, 'request_id': str(uuid.uuid4()),
    }, content_type='application/json')
    assert response.status_code == 409
    assert 'disabled' in response.json()['error']['message']


def test_saved_adventure_stays_visible_and_recovers(auth_client, user):
    config = ConfigurationFactory(is_active=False)
    conversation = ChatConversationFactory(user=user, metadata={'config_id': config.pk})
    GameSessionFactory(user=user, session_id=conversation.conversation_id, configuration=config)
    game = auth_client.get('/api/v1/home').json()['recent_games'][0]
    assert 'disabled' in game['unavailable_reason']
    response = auth_client.post(f'/api/v1/chat/conversations/{conversation.conversation_id}/turns', {
        'message': 'Continue', 'request_id': str(uuid.uuid4()),
    }, content_type='application/json')
    assert response.status_code == 409
    config.is_active = True
    config.save()
    assert auth_client.get('/api/v1/home').json()['recent_games'][0]['unavailable_reason'] is None
    config.storyteller_model.is_available = False
    config.storyteller_model.save()
    assert 'models' in auth_client.get('/api/v1/home').json()['recent_games'][0]['unavailable_reason']


def test_saved_adventure_resolves_legacy_string_configuration_id(auth_client, user):
    config = ConfigurationFactory()
    conversation = ChatConversationFactory(user=user, metadata={'config_id': str(config.pk)})
    GameSessionFactory(user=user, session_id=conversation.conversation_id, configuration=config)
    game = auth_client.get('/api/v1/home').json()['recent_games'][0]
    assert game['unavailable_reason'] is None


def test_configuration_list_batches_in_progress_counts(admin_client):
    configurations = [ConfigurationFactory() for _ in range(2)]
    GameSessionFactory(configuration=configurations[0])
    GameSessionFactory(configuration=configurations[0], game_over=True)
    GameSessionFactory(configuration=configurations[1])
    JudgeStepFactory(configuration=configurations[0])
    JudgeStepFactory(configuration=configurations[0])
    JudgeStepFactory(configuration=configurations[1])

    with CaptureQueriesContext(connection) as queries:
        response = admin_client.get('/api/v1/admin/configurations')

    assert response.status_code == 200
    results = {config['id']: config for config in response.json()['configurations']}
    assert results[configurations[0].pk]['in_progress_count'] == 1
    assert results[configurations[0].pk]['judge_step_count'] == 2
    assert results[configurations[1].pk]['in_progress_count'] == 1
    assert results[configurations[1].pk]['judge_step_count'] == 1
    assert sum(
        'game_gamesession' in query['sql'] or 'game_judgestep' in query['sql']
        for query in queries
    ) == 1


def test_missing_explicit_configuration_never_falls_back():
    ConfigurationFactory()
    conversation = ChatConversationFactory(metadata={'config_id': 999999})
    assert get_conversation_configuration(conversation) is None

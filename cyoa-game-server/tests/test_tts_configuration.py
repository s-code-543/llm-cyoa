"""Adventure audio availability and generation access controls."""
import json
from unittest.mock import patch

import pytest

from game.models import TTSSettings
from tests.conftest import ChatConversationFactory


@pytest.mark.django_db
@pytest.mark.parametrize('enabled,key,service,expected', [
    (False, 'test-key', True, False),
    (True, None, True, False),
    (True, 'test-key', False, False),
    (True, 'test-key', True, True),
])
def test_conversation_exposes_effective_tts(auth_client, user, configuration, enabled, key, service, expected):
    configuration.enable_tts = enabled
    configuration.save()
    tts = TTSSettings.get_settings()
    tts.enabled = service
    tts.save()
    conversation = ChatConversationFactory(user=user, metadata={'config_id': configuration.id})
    with patch('game.tts_views.OPENAI_API_KEY', key):
        response = auth_client.get(f'/chat/api/conversation/{conversation.conversation_id}')
        assert response.json()['capabilities']['tts'] is expected
        response = auth_client.post('/chat/api/new', json.dumps({'config_id': configuration.id}), content_type='application/json')
        assert response.json()['capabilities']['tts'] is expected


@pytest.mark.django_db
@pytest.mark.parametrize('enabled,key,status', [(False, 'test-key', 403), (True, None, 503)])
def test_unavailable_tts_never_calls_provider(auth_client, user, configuration, enabled, key, status):
    configuration.enable_tts = enabled
    configuration.save()
    conversation = ChatConversationFactory(user=user, metadata={'config_id': configuration.id})
    with patch('game.tts_views.OPENAI_API_KEY', key), patch('game.tts_views.OpenAI') as provider:
        response = auth_client.post('/api/tts/generate', json.dumps({
            'conversation_id': conversation.conversation_id, 'text': 'Narrator text',
        }), content_type='application/json')
        assert response.status_code == status
        provider.assert_not_called()


@pytest.mark.django_db
def test_tts_requires_owned_conversation(auth_client, admin_user, configuration):
    conversation = ChatConversationFactory(user=admin_user, metadata={'config_id': configuration.id})
    with patch('game.tts_views.OpenAI') as provider:
        response = auth_client.post('/api/tts/generate', json.dumps({
            'conversation_id': conversation.conversation_id, 'text': 'Narrator text',
        }), content_type='application/json')
        assert response.status_code == 404
        provider.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize('enabled', [True, False])
def test_admin_can_toggle_adventure_tts(admin_client, configuration, game_ending_prompt, mock_ollama_models, enabled):
    payload = {
        'action': 'save', 'name': configuration.name,
        'adventure_prompt': configuration.adventure_prompt_id,
        'storyteller_model': configuration.storyteller_model_id,
        'game_ending_prompt': game_ending_prompt.id,
        'total_turns': 10, 'phase1_turns': 3, 'phase2_turns': 3,
        'phase3_turns': 3, 'phase4_turns': 1,
    }
    if enabled:
        payload['enable_tts'] = '1'
    configuration.enable_tts = not enabled
    configuration.save()
    response = admin_client.post(f'/admin/configurations/{configuration.id}/', payload)
    assert response.status_code == 302
    configuration.refresh_from_db()
    assert configuration.enable_tts is enabled

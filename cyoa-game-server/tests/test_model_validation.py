"""Unavailable model cleanup preserves presets and prevents broken game starts."""
import json
import uuid
from unittest.mock import patch

import pytest

from game.config_utils import configuration_models_available
from game.models import LLMModel
from tests.conftest import LLMModelFactory, JudgeStepFactory, PromptFactory

pytestmark = pytest.mark.django_db
URL = '/api/v1/admin/models/validate'


def post(client, data):
    return client.post(URL, json.dumps(data), content_type='application/json')


def test_validation_and_cleanup_preserve_configuration(admin_client, auth_client, configuration):
    model = configuration.storyteller_model
    other = LLMModelFactory(provider=model.provider)
    with patch('game.admin_providers_api.fetch_provider_models', return_value=[{'id': other.model_identifier}]):
        result = post(admin_client, {}).json()
    assert model.pk in [m['id'] for m in result['unavailable']]
    configuration.refresh_from_db()
    assert not configuration_models_available(configuration)
    assert configuration.pk not in [c['id'] for c in auth_client.get('/api/v1/home').json()['configurations']]
    assert configuration.pk not in [c['id'] for c in auth_client.get('/api/v1/chat/bootstrap').json()['configurations']]
    response = auth_client.post('/api/v1/chat/conversations', json.dumps({
        'config_id': configuration.pk, 'request_id': str(uuid.uuid4()),
    }), content_type='application/json')
    assert response.status_code == 409
    assert auth_client.post('/chat/api/new', json.dumps({'config_id': configuration.pk}),
                            content_type='application/json').status_code == 409
    assert post(admin_client, {'delete_ids': [model.pk, other.pk]}).json()['removed'] == 1
    configuration.refresh_from_db()
    assert configuration.storyteller_model is None
    assert LLMModel.objects.filter(pk=other.pk).exists()
    assert not configuration_models_available(configuration)


@pytest.mark.parametrize('catalog', [[], RuntimeError('offline')])
def test_provider_failure_does_not_invalidate_or_delete(admin_client, llm_model, catalog):
    kwargs = {'side_effect': catalog} if isinstance(catalog, Exception) else {'return_value': catalog}
    with patch('game.admin_providers_api.fetch_provider_models', **kwargs):
        result = post(admin_client, {}).json()
    assert result['failures']
    assert not result['unavailable']
    llm_model.refresh_from_db()
    assert llm_model.is_available


def test_validation_restores_returned_models(admin_client, llm_model):
    llm_model.is_available = False
    llm_model.save()
    with patch('game.admin_providers_api.fetch_provider_models', return_value=[{'id': llm_model.model_identifier}]):
        post(admin_client, {})
    llm_model.refresh_from_db()
    assert llm_model.is_available


@pytest.mark.parametrize('role', ['classifier_model', 'rewrite_model', 'compare_model'])
def test_judge_models_can_be_deleted_without_removing_configuration(configuration, role):
    step = JudgeStepFactory(configuration=configuration, classifier_model=LLMModelFactory(),
                            classifier_prompt=PromptFactory(prompt_type="classifier"))
    getattr(step, role).delete()
    step.refresh_from_db()
    configuration.refresh_from_db()
    assert getattr(step, role) is None
    assert not configuration_models_available(configuration)


def test_validation_requires_admin(auth_client):
    assert post(auth_client, {}).status_code == 403


@pytest.mark.parametrize('role', ['classifier_model', 'turn_correction_model', 'image_model'])
def test_deleted_optional_roles_block_enabled_features(configuration, role):
    model = LLMModelFactory()
    setattr(configuration, role, model)
    if role == 'image_model':
        configuration.enable_image_generation = True
    elif role == 'classifier_model':
        configuration.classifier_prompt = PromptFactory(prompt_type='classifier')
    else:
        configuration.turn_correction_prompt = PromptFactory(prompt_type='turn-correction')
    configuration.save()
    assert configuration_models_available(configuration)
    model.delete()
    configuration.refresh_from_db()
    assert not configuration_models_available(configuration)


def test_inactive_provider_cannot_start(configuration):
    provider = configuration.storyteller_model.provider
    provider.is_active = False
    provider.save()
    configuration.refresh_from_db()
    assert not configuration_models_available(configuration)


def test_unavailable_model_is_rejected_before_generation(configuration):
    from unittest.mock import Mock
    from game.engine.nodes import TurnUnavailable
    from game.engine.turn_execution import execute_turn
    from tests.conftest import ChatConversationFactory

    conversation = ChatConversationFactory(metadata={'config_id': configuration.pk})
    model = configuration.storyteller_model
    model.is_available = False
    model.save()
    generate = Mock()
    with pytest.raises(TurnUnavailable, match='no longer available'):
        execute_turn(conversation, 'Go', call_llm=generate,
                     correct_refusal=Mock(), judge_turn=Mock())
    generate.assert_not_called()

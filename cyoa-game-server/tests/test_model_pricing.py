"""Provider catalog prices survive browsing/import and can be refreshed safely."""
import json
from unittest.mock import Mock, patch

import pytest

from game.models import LLMModel
from game.openrouter_utils import get_openrouter_models
from tests.conftest import APIProviderFactory, LLMModelFactory

pytestmark = pytest.mark.django_db
PRICING = {'prompt': '0.000001', 'completion': '0.000004', 'request': '0'}
REFRESH = '/api/v1/admin/models/pricing/refresh'


def test_openrouter_keeps_raw_prices_and_undecorated_description():
    text = Mock(status_code=200)
    text.json.return_value = {'data': [{'id': 'test/text', 'description': 'A model', 'pricing': PRICING}]}
    image = Mock(status_code=200)
    image.json.return_value = {'data': [{'id': 'test/image', 'pricing': {'image': '0.04'}}]}
    with patch('game.openrouter_utils.requests.get', side_effect=[text, image]) as fetch:
        models = get_openrouter_models('test')
    assert fetch.call_args_list[0].kwargs['params'] == {'output_modalities': 'text,image'}
    assert models[0]['pricing'] == PRICING
    assert models[0]['description'] == 'A model'
    assert models[1]['pricing'] == {'image': '0.04'}


def test_image_catalog_without_pricing_preserves_shared_text_catalog_prices():
    text = Mock(status_code=200)
    text.json.return_value = {'data': [{'id': 'test/image', 'pricing': PRICING}]}
    image = Mock(status_code=200)
    image.json.return_value = {'data': [{'id': 'test/image'}]}
    with patch('game.openrouter_utils.requests.get', side_effect=[text, image]):
        models = get_openrouter_models('test')
    assert len(models) == 1
    assert models[0]['pricing'] == PRICING


def test_browse_import_list_sync_and_validation_keep_prices(admin_client):
    provider = APIProviderFactory(provider_type='openrouter')
    path = f'/api/v1/admin/providers/{provider.pk}/models'
    item = {'id': 'test/model', 'name': 'Test model', 'pricing': PRICING,
            'context_length': 128000, 'created': 1700000000,
            'architecture': {'input_modalities': ['text', 'image'], 'output_modalities': ['text'], 'tokenizer': 'Qwen'},
            'supported_parameters': ['tools', 'reasoning']}
    with patch('game.admin_providers_api.fetch_provider_models', return_value=[item]):
        assert admin_client.get(path).json()['models'][0]['pricing'] == PRICING
        result = admin_client.post(path + '/import', json.dumps({'model_ids': [item['id']]}), content_type='application/json')
        assert result.status_code == 200
        model = LLMModel.objects.get(provider=provider)
        assert model.capabilities['pricing'] == PRICING
        assert model.capabilities['pricing_updated_at']
        listed = admin_client.get('/api/v1/admin/models').json()['models'][0]
        assert listed['pricing'] == PRICING and listed['pricing_updated_at']
        assert listed['context_length'] == 128000
        assert listed['architecture']['tokenizer'] == 'Qwen'
        assert listed['supported_parameters'] == ['tools', 'reasoning']
        assert listed['created'] == 1700000000
        item['pricing'] = {'prompt': '0', 'completion': '0'}
        assert admin_client.post(path + '/sync', '{}', content_type='application/json').status_code == 200
        model.refresh_from_db()
        assert model.capabilities['pricing'] == item['pricing']
        item['pricing'] = PRICING
        admin_client.post('/api/v1/admin/models/validate', '{}', content_type='application/json')
        model.refresh_from_db()
        assert model.capabilities['pricing'] == PRICING


def test_refresh_is_once_per_provider_and_preserves_availability_and_other_capabilities(admin_client):
    provider = APIProviderFactory(provider_type='openrouter')
    models = [LLMModelFactory(provider=provider, is_available=False, capabilities={'custom': True}) for _ in range(3)]
    catalog = [{'id': model.model_identifier, 'pricing': PRICING} for model in models]
    with patch('game.admin_providers_api.fetch_provider_models', return_value=catalog) as fetch:
        result = admin_client.post(REFRESH, '{}', content_type='application/json').json()
    fetch.assert_called_once()
    assert not result['failures']
    for model in models:
        model.refresh_from_db()
        assert model.capabilities['pricing'] == PRICING
        assert model.capabilities['custom']
        assert not model.is_available


@pytest.mark.parametrize('operation', ['pricing', 'validation', 'sync'])
def test_catalog_updates_preserve_metadata_omitted_by_provider(admin_client, operation):
    provider = APIProviderFactory(provider_type='openrouter')
    model = LLMModelFactory(
        provider=provider,
        capabilities={
            'context_length': 128000,
            'created': 1700000000,
            'architecture': {'tokenizer': 'Qwen'},
            'supported_parameters': ['tools'],
            'image_generation': True,
        },
    )
    catalog = [{'id': model.model_identifier, 'pricing': PRICING}]
    with patch('game.admin_providers_api.fetch_provider_models', return_value=catalog):
        if operation == 'pricing':
            admin_client.post(REFRESH, '{}', content_type='application/json')
        elif operation == 'validation':
            admin_client.post('/api/v1/admin/models/validate', '{}', content_type='application/json')
        else:
            admin_client.post(
                f'/api/v1/admin/providers/{provider.pk}/models/sync',
                '{}',
                content_type='application/json',
            )
    model.refresh_from_db()
    assert model.capabilities['context_length'] == 128000
    assert model.capabilities['created'] == 1700000000
    assert model.capabilities['architecture'] == {'tokenizer': 'Qwen'}
    assert model.capabilities['supported_parameters'] == ['tools']
    if operation == 'validation':
        assert model.capabilities['image_generation'] is False


@pytest.mark.parametrize('catalog', [[], RuntimeError('offline'), [{'id': 'another-model'}]])
def test_failed_refresh_keeps_saved_price_and_timestamp(admin_client, catalog):
    model = LLMModelFactory(capabilities={'pricing': PRICING, 'pricing_updated_at': 'old'})
    kwargs = {'side_effect': catalog} if isinstance(catalog, Exception) else {'return_value': catalog}
    with patch('game.admin_providers_api.fetch_provider_models', **kwargs):
        result = admin_client.post(REFRESH, '{}', content_type='application/json').json()
    assert result['failures']
    model.refresh_from_db()
    assert model.capabilities == {'pricing': PRICING, 'pricing_updated_at': 'old'}


def test_unknown_prices_are_not_recorded_as_free(admin_client):
    model = LLMModelFactory()
    with patch('game.admin_providers_api.fetch_provider_models', return_value=[{'id': model.model_identifier}]):
        admin_client.post(REFRESH, '{}', content_type='application/json')
    model.refresh_from_db()
    assert model.capabilities.get('pricing', {}) == {}


def test_refresh_requires_admin(auth_client):
    assert auth_client.post(REFRESH, '{}', content_type='application/json').status_code == 403


def test_list_backfills_prices_and_reuses_saved_daily_rates(admin_client):
    from django.core.cache import cache
    cache.clear()
    provider = APIProviderFactory(provider_type='openrouter')
    model = LLMModelFactory(provider=provider, capabilities={})
    with patch('game.admin_providers_api.fetch_provider_models', return_value=[
        {'id': model.model_identifier, 'pricing': PRICING}
    ]) as fetch:
        first = admin_client.get('/api/v1/admin/models').json()
        cache.clear()  # Persistence, not just process cache, prevents another fetch.
        second = admin_client.get('/api/v1/admin/models').json()
    fetch.assert_called_once()
    assert first['models'][0]['pricing'] == second['models'][0]['pricing'] == PRICING


def test_missing_provider_prices_preserve_saved_rates_and_throttle_retries(admin_client):
    from django.core.cache import cache
    cache.clear()
    provider = APIProviderFactory(provider_type='openrouter')
    model = LLMModelFactory(provider=provider, capabilities={'pricing': PRICING})
    with patch('game.admin_providers_api.fetch_provider_models', return_value=[
        {'id': model.model_identifier}
    ]) as fetch:
        admin_client.get('/api/v1/admin/models')
        result = admin_client.get('/api/v1/admin/models').json()
        admin_client.post(REFRESH, '{}', content_type='application/json')
    assert fetch.call_count == 2  # One automatic attempt plus explicit refresh.
    model.refresh_from_db()
    assert result['models'][0]['pricing'] == model.capabilities['pricing'] == PRICING
    cache.clear()

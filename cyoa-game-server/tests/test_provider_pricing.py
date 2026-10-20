"""Official standard rates, provenance, caching and failure isolation."""
import json
from unittest.mock import Mock, patch
import pytest
import requests
from django.core.cache import cache
from game.provider_pricing import SOURCES, PricingUnavailable, enrich_models, fetch_rates, parse_anthropic, parse_openai
from tests.conftest import APIProviderFactory, LLMModelFactory

OPENAI = '''Prices per 1M tokens.
### Standard pricing data
| Model | Short context input | Short context cached input | Short context output |
| --- | --- | --- | --- |
| gpt-4o | $2.50 | $1.25 | $10.00 |
| gpt-4o-2024-05-13 | $5.00 | - | $15.00 |
| gpt-5-mini | $0.25 | $0.025 | $2.00 |

### Batch pricing data
| Model | Short context input | Short context output |
| --- | --- | --- |
| gpt-4o | $1.25 | $5.00 |
'''
ANTHROPIC = '''## Model pricing
| Model | Base input tokens | 5m cache writes | Output tokens |
| --- | --- | --- | --- |
| Claude Haiku 4.5 | $1 / MTok | $1.25 / MTok | $5 / MTok |
| Claude Sonnet 4.5 | $3 / MTok<sup>1</sup> | $3.75 / MTok | $15 / MTok<sup>1</sup> |
| Claude Haiku 5.5 (for prompts up to 100,000 tokens) | $0.10 / MTok | $0.125 / MTok | $0.50 / MTok |
| Claude Haiku 5.5 (for prompts over 100,000 tokens) | $0.50 / MTok | $0.625 / MTok | $2.50 / MTok |

## Batch processing
| Model | Base input tokens | Output tokens |
| --- | --- | --- |
| Claude Haiku 4.5 | $0.50 / MTok | $2.50 / MTok |
'''

@pytest.fixture(autouse=True)
def clear_pricing_cache():
    cache.clear()
    yield
    cache.clear()


def response(text):
    result = Mock(text=text, content=text.encode())
    return result


def test_standard_rates_not_batch_cached_or_long_context():
    rates = parse_openai(OPENAI)
    assert rates['gpt-4o'] == {'prompt': '0.0000025', 'completion': '0.00001'}
    assert rates['gpt-4o-2024-05-13']['prompt'] == '0.000005'
    rates = parse_anthropic(ANTHROPIC)
    assert rates['claude-haiku-4-5'] == {'prompt': '0.000001', 'completion': '0.000005'}
    assert rates['claude-sonnet-4-5']['prompt'] == '0.000003'
    assert rates['claude-haiku-5-5']['prompt'] == '0.0000001'


@pytest.mark.parametrize('parser,document', [(parse_openai, OPENAI), (parse_anthropic, ANTHROPIC)])
def test_format_changes_fail_closed(parser, document):
    with pytest.raises(PricingUnavailable):
        parser('<html>Challenge page</html>')
    with pytest.raises(PricingUnavailable):
        parser(document.replace('Short context output', 'Renamed').replace('Output tokens', 'Renamed'))


def test_cache_and_force_refresh_have_checked_date_and_no_credentials():
    with patch('game.provider_pricing.requests.get', return_value=response(OPENAI)) as get:
        first = fetch_rates('openai')
        assert fetch_rates('openai') == first
        assert get.call_count == 1
        fetch_rates('openai', force=True)
        assert get.call_count == 2
        assert first['source'] == SOURCES['openai'] and first['checked_at']
        assert get.call_args.args == (SOURCES['openai'] + '.md',)
        assert 'headers' not in get.call_args.kwargs


def test_model_matches_are_exact_and_anthropic_uses_official_display_name():
    with patch('game.provider_pricing.requests.get', return_value=response(OPENAI)):
        result = enrich_models('openai', [{'id': 'gpt-4o'}, {'id': 'gpt-4o-2099-01-01'}])
    assert result[0]['pricing']['prompt'] == '0.0000025'
    assert 'pricing' not in result[1] and result[1]['pricing_warning']
    with patch('game.provider_pricing.requests.get', return_value=response(ANTHROPIC)):
        result = enrich_models('anthropic', [{'id': 'claude-haiku-4-5-20251001', 'name': 'Claude Haiku 4.5'}])
    assert result[0]['pricing']['prompt'] == '0.000001'


@pytest.mark.django_db
@pytest.mark.parametrize('provider_type,document,model_id,name', [
    ('openai', OPENAI, 'gpt-4o', 'gpt-4o'),
    ('anthropic', ANTHROPIC, 'claude-haiku-4-5-20251001', 'Claude Haiku 4.5'),
])
def test_browse_import_and_refresh_record_official_provenance(admin_client, provider_type, document, model_id, name):
    provider = APIProviderFactory(provider_type=provider_type)
    path = f'/api/v1/admin/providers/{provider.pk}/models'
    model_tool = 'get_openai_models' if provider_type == 'openai' else 'get_anthropic_models'
    with patch('game.admin_providers_api.' + model_tool, return_value=[{'id': model_id, 'name': name}]), patch('game.provider_pricing.requests.get', return_value=response(document)) as get:
        browsed = admin_client.get(path).json()
        assert not browsed['pricing_warnings']
        assert browsed['models'][0]['pricing_source'] == SOURCES[provider_type]
        result = admin_client.post(path + '/import', json.dumps({'model_ids': [model_id]}), content_type='application/json')
        assert result.status_code == 200
        model = provider.llmmodel_set.get()
        assert model.capabilities['pricing_source'] == SOURCES[provider_type]
        assert model.capabilities['pricing_updated_at']
        assert get.call_count == 1
        admin_client.post('/api/v1/admin/models/pricing/refresh', '{}', content_type='application/json')
        assert get.call_count == 2
        listed = admin_client.get('/api/v1/admin/models').json()['models'][0]
        assert listed['pricing_source'] == SOURCES[provider_type]
        assert listed['pricing_note'].startswith('Standard base')


@pytest.mark.django_db
@pytest.mark.parametrize('operation', ['pricing', 'validation', 'sync', 'import'])
@pytest.mark.parametrize('failure', ['timeout', 'format', 'unmatched'])
def test_docs_failure_preserves_prices_and_availability(admin_client, operation, failure):
    provider = APIProviderFactory(provider_type='openai')
    saved = {'pricing': {'prompt': '0.000001', 'completion': '0.000002'},
             'pricing_source': SOURCES['openai'], 'pricing_updated_at': 'previous-check'}
    model = LLMModelFactory(provider=provider, model_identifier='gpt-4o', capabilities=saved)
    urls = {'pricing': '/api/v1/admin/models/pricing/refresh',
            'validation': '/api/v1/admin/models/validate',
            'sync': f'/api/v1/admin/providers/{provider.pk}/models/sync',
            'import': f'/api/v1/admin/providers/{provider.pk}/models/import'}
    kwargs = {'side_effect': requests.Timeout} if failure == 'timeout' else {'return_value': response('<html>Changed</html>' if failure == 'format' else OPENAI.replace('| gpt-4o |', '| unmatched |'))}
    with patch('game.admin_providers_api.get_openai_models', return_value=[{'id': 'gpt-4o', 'name': 'gpt-4o'}]), patch('game.provider_pricing.requests.get', **kwargs):
        result = admin_client.post(urls[operation], json.dumps({'model_ids': ['gpt-4o']}), content_type='application/json')
    assert result.status_code == 200
    model.refresh_from_db()
    for key, value in saved.items():
        assert model.capabilities[key] == value
    assert model.is_available


def test_openai_catalog_includes_current_text_families():
    from game.openai_utils import get_openai_models
    api_response = response('')
    api_response.status_code = 200
    api_response.json.return_value = {'data': [{'id': model} for model in ['gpt-5-mini', 'o3', 'gpt-4o', 'gpt-image-1', 'gpt-4o-audio-preview', 'whisper-1']]}
    with patch('game.openai_utils.requests.get', return_value=api_response):
        models = get_openai_models('test')
    assert {m['id'] for m in models} == {'gpt-5-mini', 'o3', 'gpt-4o'}

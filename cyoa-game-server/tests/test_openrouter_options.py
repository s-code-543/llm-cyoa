from unittest.mock import Mock, patch

import pytest

from game.llm_router import call_llm
from tests.conftest import APIProviderFactory, LLMModelFactory


@pytest.mark.django_db
@pytest.mark.parametrize('disabled', [True, False])
def test_router_forwards_reasoning_control_to_openrouter(disabled):
    provider = APIProviderFactory(provider_type='openrouter', api_key='test-key')
    model = LLMModelFactory(provider=provider, model_identifier='google/gemini-2.5-flash')
    response = Mock(status_code=200)
    response.json.return_value = {'id': 'gen-test', 'usage': {'cost': 0.0001, 'prompt_tokens': 10, 'completion_tokens': 1}, 'choices': [{'message': {'content': 'PASS'}}]}
    with patch('game.openrouter_utils.requests.post', return_value=response) as post:
        result = call_llm([{'role': 'user', 'content': 'Check'}], llm_model=model, disable_thinking=disabled)
        assert result == 'PASS'
        assert result.billing['generation_id'] == 'gen-test'
        assert result.billing['usage']['cost'] == 0.0001
    payload = post.call_args.kwargs['json']
    if disabled:
        assert payload['reasoning'] == {'effort': 'none'}
    else:
        assert 'reasoning' not in payload


def test_image_catalog_merged_with_text_models():
    from game.openrouter_utils import get_openrouter_models
    text = Mock(status_code=200)
    text.json.return_value = {'data': [{'id': 'text/model', 'name': 'Text'}]}
    images = Mock(status_code=200)
    images.json.return_value = {'data': [{'id': 'image/model', 'name': 'Image',
                                          'supported_parameters': {'aspect_ratio': {'type': 'enum', 'values': ['16:9']}}}]}
    with patch('game.openrouter_utils.requests.get', side_effect=[text, images]) as get:
        models = get_openrouter_models('test')
    assert get.call_args.args[0].endswith('/images/models')
    assert [m['id'] for m in models] == ['text/model', 'image/model']
    assert models[1]['image_generation'] is True
    assert 'aspect_ratio' in models[1]['supported_parameters']


@pytest.mark.parametrize('failure', ['timeout', 'json', 'shape', 'entry', 'http'])
def test_optional_image_catalog_failure_preserves_text_models(failure):
    import requests
    from game.openrouter_utils import get_openrouter_models

    text = Mock(status_code=200)
    text.json.return_value = {'data': [{'id': 'text/model', 'name': 'Text'}]}
    images = Mock(status_code=200)
    images.json.return_value = {'data': []}
    if failure == 'timeout':
        images = requests.Timeout('image catalog timed out')
    elif failure == 'json':
        images.json.side_effect = ValueError('invalid JSON')
    elif failure == 'shape':
        images.json.return_value = []
    elif failure == 'entry':
        images.json.return_value = {'data': [{'name': 'missing id'}]}
    else:
        images.status_code = 503
    with patch('game.openrouter_utils.requests.get', side_effect=[text, images]):
        models = get_openrouter_models('test')
    assert [model['id'] for model in models] == ['text/model']

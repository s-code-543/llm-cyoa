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

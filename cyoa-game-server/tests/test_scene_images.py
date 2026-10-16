import base64
from unittest.mock import Mock, patch

import pytest
from django.test import override_settings

from game.scene_images import illustrate_message
from tests.conftest import ChatMessageFactory, APIProviderFactory, LLMModelFactory, PromptFactory


@pytest.fixture
def illustrated_config(configuration):
    provider = APIProviderFactory(provider_type='openrouter', api_key='image-provider-key')
    configuration.image_model = LLMModelFactory(provider=provider, model_identifier='recraft/recraft-v4.1-flash', capabilities={'image_generation': True})
    configuration.image_meta_prompt = PromptFactory(prompt_type='image-meta', prompt_text='Watercolor style.')
    configuration.character_prompt = PromptFactory(prompt_type='character', prompt_text='Mira wears a blue cloak.')
    configuration.enable_image_generation = True
    configuration.image_aspect_ratio = '4:3'
    configuration.image_timeout = 45
    configuration.save()
    return configuration


@pytest.mark.django_db
@pytest.mark.parametrize('image,media_type', [
    (b'\x89PNG\r\n\x1a\nprototype', 'image/png'),
    (b'RIFF\x04\x00\x00\x00WEBPprototype', 'image/webp'),
    (b'\xff\xd8\xffprototype', 'image/jpeg'),
])
def test_image_saved_and_only_owner_can_read(auth_client, user, admin_user, tmp_path, image, media_type, illustrated_config):
    message = ChatMessageFactory(role='assistant', content='A moonlit forest.', conversation__user=user, conversation__metadata={'config_id': illustrated_config.pk}, metadata={})
    png = image
    response = Mock()
    response.json.return_value = {'data': [{'b64_json': base64.b64encode(png).decode(), 'media_type': media_type}]}
    with override_settings(MEDIA_ROOT=tmp_path), patch('game.scene_images.requests.post', return_value=response) as post:
        illustrate_message(message)
        assert post.call_args.kwargs['json']['model'] == illustrated_config.image_model.model_identifier
        payload = post.call_args.kwargs['json']
        assert payload['aspect_ratio'] == '4:3'
        assert post.call_args.kwargs['timeout'] == 45
        assert post.call_args.kwargs['headers']['Authorization'] == 'Bearer image-provider-key'
        assert payload['prompt'].index('Watercolor style.') < payload['prompt'].index('Mira wears a blue cloak.') < payload['prompt'].index('A moonlit forest.')
        illustrate_message(message)
        assert post.call_count == 1
        url = f'/api/v1/chat/images/{message.pk}'
        result = auth_client.get(url)
        assert result.status_code == 200
        assert result['Content-Type'] == media_type
        assert 'scene_image_failed' not in message.metadata
        assert b''.join(result.streaming_content) == png
        auth_client.force_login(admin_user)
        assert auth_client.get(url).status_code == 404


@pytest.mark.django_db
def test_image_failure_preserves_story(illustrated_config):
    message = ChatMessageFactory(role='assistant', content='The story survives.', conversation__metadata={'config_id': illustrated_config.pk}, metadata={})
    with patch('game.scene_images.requests.post', side_effect=TimeoutError):
        illustrate_message(message)
    message.refresh_from_db()
    assert message.content == 'The story survives.'
    assert message.metadata['scene_image_failed'] is True


@pytest.mark.django_db
def test_disabled_configuration_never_calls_provider(illustrated_config):
    illustrated_config.enable_image_generation = False
    illustrated_config.save()
    message = ChatMessageFactory(role='assistant', conversation__metadata={'config_id': illustrated_config.pk})
    with patch('game.scene_images.requests.post') as post:
        illustrate_message(message)
    post.assert_not_called()
    assert 'scene_image_failed' not in message.metadata

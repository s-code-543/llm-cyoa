import base64
from io import BytesIO
from unittest.mock import Mock, patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image

from game.scene_images import illustrate_message
from tests.conftest import ChatMessageFactory, PromptFactory
from tests.test_scene_images import illustrated_config


def png_file():
    image = BytesIO()
    Image.new('RGB', (8, 8), 'blue').save(image, format='PNG')
    return image.getvalue()


@pytest.mark.django_db
def test_upload_attach_read_and_send_on_each_image_call(admin_client, auth_client, tmp_path, illustrated_config):
    with override_settings(MEDIA_ROOT=tmp_path):
        illustrated_config.game_ending_prompt = PromptFactory(prompt_type='game-ending')
        illustrated_config.enable_refusal_detection = False
        illustrated_config.save()
        references = []
        for kind in ('character', 'scene'):
            uploaded = admin_client.post('/api/v1/admin/image-references', {
                'image': SimpleUploadedFile(f'{kind}.png', png_file(), content_type='image/png'),
                'kind': kind, 'name': f'{kind} reference',
            })
            assert uploaded.status_code == 201
            references.append(uploaded.json())
        detail = f'/api/v1/admin/configurations/{illustrated_config.pk}'
        payload = admin_client.get(detail).json()
        payload['image_references'] = references
        updated = admin_client.put(detail, payload, content_type='application/json')
        assert updated.status_code == 200, updated.content
        assert {r['kind'] for r in updated.json()['image_references']} == {'character', 'scene'}
        for reference in references:
            assert auth_client.get(reference['url']).status_code == 403
            response = admin_client.get(reference['url'])
            assert response.status_code == 200
            assert b''.join(response.streaming_content) == png_file()
        result = Mock()
        result.json.return_value = {'data': [{'b64_json': base64.b64encode(png_file()).decode()}]}
        with patch('game.scene_images.requests.post', return_value=result) as post:
            for turn in ('He enters the house.', 'He approaches the stairs.'):
                message = ChatMessageFactory(role='assistant', content=turn,
                    conversation__metadata={'config_id': illustrated_config.pk}, metadata={})
                illustrate_message(message)
                request = post.call_args.kwargs['json']
                assert len(request['input_references']) == 2
                assert all(r['image_url']['url'] == 'data:image/png;base64,' + base64.b64encode(png_file()).decode()
                           for r in request['input_references'])
                assert 'character appearance sheet' in request['prompt']
                assert 'scene/environment reference' in request['prompt']
                assert turn in request['prompt']
            assert post.call_count == 2
        payload['image_references'] = []
        assert admin_client.put(detail, payload, content_type='application/json').status_code == 200
        assert not illustrated_config.image_references.exists()


@pytest.mark.django_db
def test_upload_rejects_non_images_and_non_admins(admin_client, auth_client, tmp_path):
    with override_settings(MEDIA_ROOT=tmp_path):
        assert auth_client.post('/api/v1/admin/image-references', {}).status_code == 403
        for content in (b'not a png', b'<svg xmlns="http://www.w3.org/2000/svg"/>'):
            response = admin_client.post('/api/v1/admin/image-references', {
                'kind': 'character', 'image': SimpleUploadedFile('fake.png', content, content_type='image/png')})
            assert response.status_code == 400


@pytest.mark.django_db
def test_configuration_rejects_missing_duplicate_and_excess_references(admin_client, configuration):
    detail = f'/api/v1/admin/configurations/{configuration.pk}'
    payload = admin_client.get(detail).json()
    for references in ([{'id': 'missing'}], [None], [{}] * 5):
        payload['image_references'] = references
        response = admin_client.put(detail, payload, content_type='application/json')
        assert response.status_code == 400
        assert 'image_references' in response.json()['error']['fields']


@pytest.mark.django_db
def test_model_reference_limits_are_enforced(admin_client, illustrated_config, tmp_path):
    with override_settings(MEDIA_ROOT=tmp_path):
        reference = admin_client.post('/api/v1/admin/image-references', {
            'kind': 'character', 'image': SimpleUploadedFile('hero.png', png_file(), content_type='image/png')}).json()
        illustrated_config.game_ending_prompt = PromptFactory(prompt_type='game-ending')
        illustrated_config.enable_refusal_detection = False
        illustrated_config.save()
        model = illustrated_config.image_model
        model.capabilities = {'image_generation': True, 'supported_parameters': {'aspect_ratio': {'type': 'enum'}}}
        model.save()
        detail = f'/api/v1/admin/configurations/{illustrated_config.pk}'
        payload = admin_client.get(detail).json()
        payload['image_references'] = [reference]
        response = admin_client.put(detail, payload, content_type='application/json')
        assert response.status_code == 400
        assert 'does not accept' in response.json()['error']['fields']['image_model']
        model.capabilities['supported_parameters']['input_references'] = {'max': 4}
        model.save()
        assert admin_client.put(detail, payload, content_type='application/json').status_code == 200
        payload['image_references'] = [reference, reference]
        response = admin_client.put(detail, payload, content_type='application/json')
        assert 'image_references' in response.json()['error']['fields']

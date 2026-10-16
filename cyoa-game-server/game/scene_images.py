"""Prototype scene illustrations; failures never undo a saved story turn."""
import base64
import logging
import uuid
from pathlib import Path

import requests
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET

from .models import ChatMessage
from .config_utils import get_conversation_configuration
from .response_format import public_content

logger = logging.getLogger(__name__)


def illustrate_message(message):
    if message.role != 'assistant' or message.metadata.get('is_error') or message.metadata.get('scene_image'):
        return
    config = get_conversation_configuration(message.conversation)
    if not config or not config.enable_image_generation:
        return
    try:
        model = config.image_model
        if (not model or not config.image_meta_prompt or not model.is_available
                or not model.capabilities.get('image_generation')
                or 'vector' in model.model_identifier.lower()
                or model.provider.provider_type != 'openrouter'
                or not model.provider.is_active or not model.provider.api_key):
            raise ValueError('Image generation configuration is incomplete')
        api_key = model.provider.api_key
        # Only send player-visible prose; hidden engine state must never enter the image prompt.
        scene = public_content(message.content, message.metadata)
        parts = [config.image_meta_prompt.prompt_text]
        if config.character_prompt:
            parts.append('Character descriptions (use only characters present in the scene):\n'
                         + config.character_prompt.prompt_text)
        parts.append('Narrative turn (illustrate the current scene, not unchosen options):\n' + scene)
        prompt = '\n\n'.join(parts)
        response = requests.post(
            'https://openrouter.ai/api/v1/images',
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            json={'model': model.model_identifier, 'prompt': prompt,
                  'aspect_ratio': config.image_aspect_ratio, 'n': 1, 'output_format': 'png'},
            timeout=config.image_timeout,
        )
        response.raise_for_status()
        result = response.json()
        item = result['data'][0]
        data = base64.b64decode(item['b64_json'], validate=True)
        if data.startswith(b'\x89PNG\r\n\x1a\n'):
            extension, media_type = 'png', 'image/png'
        elif data.startswith(b'RIFF') and data[8:12] == b'WEBP':
            extension, media_type = 'webp', 'image/webp'
        elif data.startswith(b'\xff\xd8\xff'):
            extension, media_type = 'jpg', 'image/jpeg'
        else:
            raise ValueError('Unsupported raster illustration')
        directory = Path(settings.MEDIA_ROOT) / 'scene_images'
        directory.mkdir(parents=True, exist_ok=True)
        filename = f'{uuid.uuid4().hex}.{extension}'
        (directory / filename).write_bytes(data)
        message.metadata['scene_image'] = {'filename': filename, 'model': model.model_identifier, 'media_type': media_type,
                                            'image_meta_prompt_id': config.image_meta_prompt_id,
                                            'character_prompt_id': config.character_prompt_id,
                                            'usage': result.get('usage', {})}
        message.metadata.pop('scene_image_failed', None)
        message.save(update_fields=['metadata'])
    except Exception:
        # Avoid logging provider response bodies or credentials.
        logger.warning('Scene illustration failed for message %s', message.pk)
        message.metadata['scene_image_failed'] = True
        message.save(update_fields=['metadata'])


@login_required
@require_GET
def scene_image(request, message_id):
    message = get_object_or_404(ChatMessage, pk=message_id, conversation__user=request.user)
    filename = message.metadata.get('scene_image', {}).get('filename', '')
    if not filename or Path(filename).name != filename:
        raise Http404
    try:
        response = FileResponse(open(Path(settings.MEDIA_ROOT) / 'scene_images' / filename, 'rb'), content_type=message.metadata['scene_image'].get('media_type', 'image/png'))
    except FileNotFoundError:
        raise Http404
    response['Cache-Control'] = 'private, no-store'
    return response

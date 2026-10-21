"""Prototype scene illustrations; failures never undo a saved story turn."""
import base64
import logging
import time
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
    started = time.monotonic()
    model = config.image_model
    step = {
        'index': len(message.metadata.get('pipeline_debug') or []),
        'type': 'GenerateImage', 'status': 'running',
        'configuration': {'model': getattr(model, 'model_identifier', None),
                          'aspect_ratio': config.image_aspect_ratio, 'timeout': config.image_timeout},
        'input': {}, 'output': {}, 'model_requests': [],
    }
    request_attempted = False
    usage = {}
    usage_recorded = False
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
        from .image_references import reference_inputs, reference_limit
        references, descriptions = reference_inputs(config)
        if references:
            limit = reference_limit(model)
            if limit is not None and len(references) > limit:
                raise ValueError("Image model cannot accept the configured references")
            parts.append('Reference images, in attachment order:\n' + '\n'.join(descriptions)
                         + '\nUse character sheets for consistent identity and scene references for architecture and surroundings. '
                         'Compose the current narrative scene; references do not require absent characters or locations to appear.')
        prompt = '\n\n'.join(parts)
        step['input'] = {'prompt': prompt, 'reference_count': len(references)}
        request_attempted = True
        response = requests.post(
            'https://openrouter.ai/api/v1/images',
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            json={'model': model.model_identifier, 'prompt': prompt,
                  'aspect_ratio': config.image_aspect_ratio, 'n': 1, 'output_format': 'png',
                  **({'input_references': references} if references else {})},
            timeout=config.image_timeout,
        )
        result = response.json()
        usage = result.get('usage') or {}
        response.raise_for_status()
        from .billing import record_call
        usage_recorded = True
        record_call(message.conversation.conversation_id, {'usage': usage}, model, kind='image')
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
        step['status'] = 'completed'
        step['output'] = {'media_type': media_type, 'image_url': f'/api/v1/chat/images/{message.pk}'}
    except Exception:
        if request_attempted and not usage_recorded:
            usage_recorded = True
            try:
                from .billing import record_call
                record_call(message.conversation.conversation_id, {'usage': usage}, model, kind='image')
            except Exception:
                logger.warning('Scene illustration usage could not be recorded for message %s', message.pk)
        # Avoid logging provider response bodies or credentials.
        logger.warning('Scene illustration failed for message %s', message.pk)
        message.metadata['scene_image_failed'] = True
        message.save(update_fields=['metadata'])
        step['status'] = 'failed'
        step['error'] = 'Scene illustration failed. The saved story was preserved.'
    finally:
        from .billing import amount
        step['elapsed_ms'] = round((time.monotonic() - started) * 1000)
        cost = amount(usage.get('cost'))
        step['cost_usd'] = str(cost) if cost is not None else None
        if request_attempted:
            step['model_requests'] = [{
                'model': getattr(model, 'name', None),
                'model_identifier': getattr(model, 'model_identifier', None),
                'status': step['status'], 'usage': usage,
            }]
        message.metadata.setdefault('pipeline_debug', [])
        if message.metadata['pipeline_debug'] is None:
            message.metadata['pipeline_debug'] = []
        message.metadata['pipeline_debug'].append(step)
        message.save(update_fields=['metadata'])


@login_required
@require_GET
def scene_image(request, message_id):
    messages = ChatMessage.objects.all() if request.user.is_staff else ChatMessage.objects.filter(conversation__user=request.user)
    message = get_object_or_404(messages, pk=message_id)
    filename = message.metadata.get('scene_image', {}).get('filename', '')
    if not filename or Path(filename).name != filename:
        raise Http404
    try:
        response = FileResponse(open(Path(settings.MEDIA_ROOT) / 'scene_images' / filename, 'rb'), content_type=message.metadata['scene_image'].get('media_type', 'image/png'))
    except FileNotFoundError:
        raise Http404
    response['Cache-Control'] = 'private, no-store'
    return response

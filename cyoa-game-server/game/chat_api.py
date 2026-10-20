"""Versioned player API. Adapts the legacy engine without duplicating its rules."""
import hashlib
import json
import logging
import re
import time
import uuid
from functools import wraps

from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import never_cache

from . import chat_views
from .response_format import public_content
from .config_utils import get_conversation_configuration, conversation_tts_enabled, configuration_unavailable_reason
from .models import ChatConversation, Configuration, GameSession, ChatSubmission

logger = logging.getLogger(__name__)


def error(code, message, status):
    return JsonResponse({'error': {'code': code, 'message': message}}, status=status)


def player_api(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return error('unauthenticated', 'Please sign in again.', 401)
        try:
            return view(request, *args, **kwargs)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError, TypeError, KeyError):
            return error('invalid_request', 'Invalid request data.', 400)
        except Exception as exc:
            from django.http import Http404
            if isinstance(exc, Http404):
                return error('not_found', 'Adventure not found.', 404)
            logger.exception('Chat API failed')
            return error('internal_error', 'The request failed. Reload the adventure before trying again.', 500)
    return never_cache(wrapped)


def body(request):
    data = json.loads(request.body or b'{}')
    if not isinstance(data, dict):
        raise ValueError('Expected object')
    return data


def owned(request, conversation_id):
    return get_object_or_404(ChatConversation, conversation_id=conversation_id, user=request.user)


def snapshot(conversation):
    config = get_conversation_configuration(conversation)
    messages = list(conversation.messages.order_by('id'))
    last_story = next((msg for msg in reversed(messages) if msg.role == 'assistant' and not msg.metadata.get('is_error')), None)
    last_assistant = next((msg for msg in reversed(messages) if msg.role == 'assistant'), None)
    session = GameSession.objects.filter(session_id=conversation.conversation_id, user=conversation.user).first()
    state = chat_views.extract_game_state(public_content(last_story.content, last_story.metadata)) if last_story else {
        'turn_current': 0, 'turn_max': config.total_turns if config else 20,
        'choice1': '', 'choice2': '', 'inventory': [],
    }
    if session:
        state['turn_current'] = session.turn_number if last_story else 0
        state['turn_max'] = session.max_turns
    inventory = []
    if last_story:
        match = re.search(r'(?im)^\s*\*{0,2}Inventory\*{0,2}\s*:\s*\*{0,2}([^\n]+)', last_story.content)
        if match:
            inventory = [item.strip(' *') for item in match.group(1).split(',') if item.strip(' *')]
    if session and isinstance(session.hidden_state.get('inventory'), list):
        items = session.hidden_state['inventory']
        if all(isinstance(item, str) for item in items):
            inventory = items
    pending = conversation.submissions.filter(status='pending').first()
    return {
        'id': conversation.conversation_id,
        'title': conversation.title,
        'unavailable_reason': configuration_unavailable_reason(config),
        'configuration': {'id': config.pk, 'name': config.name} if config else None,
        'messages': [{
            'id': msg.pk, 'role': msg.role, 'content': public_content(msg.content, msg.metadata) if msg.role == 'assistant' else msg.content,
            'created_at': msg.created_at.isoformat(), 'is_error': bool(msg.metadata.get('is_error')),
            'image_url': f'/api/v1/chat/images/{msg.pk}' if msg.metadata.get('scene_image') else None,
            'image_failed': bool(msg.metadata.get('scene_image_failed')),
        } for msg in messages if msg.role != 'system'],
        'state': {
            'turn': state['turn_current'], 'max_turns': state['turn_max'],
            'choices': [] if session and session.game_over else [
                text for text in (state['choice1'], state['choice2']) if text
            ],
            'inventory': inventory,
            'blocked': bool(last_assistant and last_assistant.metadata.get('is_error')),
            'game_over': bool(session and session.game_over),
        },
        'capabilities': {'tts': conversation_tts_enabled(conversation)},
        'pending_request_id': str(pending.request_id) if pending else None,
    }


@player_api
@require_http_methods(['GET'])
def bootstrap(request):
    from .config_utils import configuration_models_available, with_model_availability
    configurations = with_model_availability(Configuration.objects.all())
    return JsonResponse({
        'debug_allowed': request.user.is_staff,
        'configurations': [
            {'id': c.pk, 'name': c.name}
            for c in configurations if c.is_active and configuration_models_available(c)
        ],
    })


@player_api
@require_http_methods(['GET', 'POST'])
def conversations(request):
    if request.method == 'GET':
        return JsonResponse({'conversations': list(ChatConversation.objects.filter(user=request.user).values('conversation_id', 'title')[:50])})
    data = body(request)
    conversation_id = str(uuid.UUID(data['request_id']))
    existing = ChatConversation.objects.filter(conversation_id=conversation_id).first()
    if existing and existing.user_id != request.user.pk:
        return error('not_found', 'Adventure not found.', 404)
    config = get_object_or_404(Configuration, pk=data.get('config_id'), storyteller_model__isnull=False)
    reason = configuration_unavailable_reason(config)
    if reason:
        return error('configuration_unavailable', reason, 409)
    conversation, _ = ChatConversation.objects.get_or_create(
        conversation_id=conversation_id, user=request.user,
        defaults={'title': config.name, 'metadata': {'config_id': config.pk}},
    )
    if conversation.metadata.get('config_id') != config.pk:
        return error('request_conflict', 'This request was already used with another configuration.', 409)
    return JsonResponse({'conversation': snapshot(conversation)})


@player_api
@require_http_methods(['GET', 'DELETE'])
def detail(request, conversation_id):
    conversation = (get_object_or_404(ChatConversation, conversation_id=conversation_id)
                    if request.method == 'GET' and request.user.is_staff
                    else owned(request, conversation_id))
    if request.method == 'DELETE':
        GameSession.objects.filter(session_id=conversation_id, user=request.user).update(game_over=True)
        return JsonResponse({'deleted': True})
    data = snapshot(conversation)
    if conversation.user_id != request.user.pk:
        data['read_only'] = True
        data['owner'] = conversation.user.email or conversation.user.get_username()
    return JsonResponse({'conversation': data})


def mutate(request, conversation_id, operation):
    conversation = owned(request, conversation_id)
    reason = configuration_unavailable_reason(get_conversation_configuration(conversation))
    if reason:
        return error('configuration_unavailable', reason, 409)
    data = body(request)
    request_id = uuid.UUID(data.get('request_id', ''))
    if operation == 'send':
        message = data.get('message')
        if not isinstance(message, str) or not message.strip() or len(message) > 20000:
            return error('invalid_message', 'Enter an action of at most 20,000 characters.', 400)
        payload = {'conversation_id': conversation_id, 'message': message.strip()}
    else:
        payload = {'conversation_id': conversation_id, 'message_id': int(data['message_id'])}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    previous = conversation.submissions.filter(request_id=request_id).first()
    if previous:
        if previous.payload_hash != digest or previous.operation != operation:
            return error('request_conflict', 'This request ID was already used for another action.', 409)
        if previous.status == 'pending':
            return error('request_pending', 'This action is still running. Reload to check its result; do not resend it.', 409)
        # Return current state; replaying an old request must not restore a stale transcript after rollback.
        replay = dict(previous.response)
        replay['conversation'] = snapshot(conversation)
        return JsonResponse(replay, status=previous.http_status)
    current = snapshot(conversation)
    if operation == 'send' and (current['state']['blocked'] or current['state']['game_over']):
        return error('game_finished', 'This adventure cannot accept another turn. Roll back or start a new adventure.', 409)
    try:
        with transaction.atomic():
            submission = ChatSubmission.objects.create(conversation=conversation, request_id=request_id, operation=operation, payload_hash=digest)
    except IntegrityError:
        return error('request_pending', 'Another action is running. Reload to check its result.', 409)
    started = time.monotonic()
    # Preserve the CSRF/auth checks at the URL boundary, then call the existing engine view.
    try:
        handler = chat_views.chat_api_send_message if operation == 'send' else chat_views.chat_api_rollback_to_message
        response = handler(request, payload=payload, submission_id=submission.pk)
        legacy = json.loads(response.content)
        http_status = response.status_code
        result = {}
        if http_status >= 400:
            message = str(legacy.get('error', 'Turn failed'))
            # Do not send raw provider exceptions or response bodies to the client.
            timeout = 'timeout' in message.lower()
            http_status = 504 if timeout else (http_status if http_status < 500 else 502)
            result['error'] = {
                'code': 'provider_timeout' if timeout else 'action_failed',
                'message': 'The action did not complete. Reload and inspect the saved transcript before trying again.',
            }
    except Exception:
        logger.exception('Chat mutation failed request_id=%s', request_id)
        http_status = 500
        result = {'error': {'code': 'internal_error', 'message': 'The action failed. Reload before trying again.'}}
    elapsed = round((time.monotonic() - started) * 1000)
    submission.status = 'completed' if http_status < 400 else 'failed'
    submission.http_status = http_status
    submission.finished_at = timezone.now()
    submission.response = result
    submission.save()
    result['conversation'] = snapshot(conversation)
    result['request_id'] = str(request_id)
    result['elapsed_ms'] = elapsed
    submission.response = result
    submission.save(update_fields=['response'])
    logger.info('chat_action operation=%s conversation_id=%s request_id=%s status=%s elapsed_ms=%s', operation, conversation_id, request_id, http_status, elapsed)
    return JsonResponse(result, status=http_status)


@player_api
@require_http_methods(['POST'])
def send(request, conversation_id):
    return mutate(request, conversation_id, 'send')


@player_api
@require_http_methods(['POST'])
def rollback(request, conversation_id):
    return mutate(request, conversation_id, 'rollback')


@player_api
@require_http_methods(['GET'])
def debug(request, conversation_id):
    """Administrators can inspect full prompts and hidden state for any player."""
    if not request.user.is_staff:
        return error('forbidden', 'Administrator access required.', 403)
    conversation = get_object_or_404(ChatConversation, conversation_id=conversation_id)
    message_id = request.GET.get('message_id')
    if message_id:
        message = get_object_or_404(conversation.messages, pk=int(message_id), role='assistant')
        steps = message.metadata.get('pipeline_debug')
        return JsonResponse({'steps': steps, 'status': 'blocked' if message.metadata.get('is_error') else 'completed'})
    from .models import AuditLog
    failure = AuditLog.objects.filter(details__conversation_id=conversation_id,
                                     details__type='workflow_error').order_by('-id').first()
    return JsonResponse({'steps': failure.details.get('pipeline_debug') if failure else None,
                         'status': 'failed', 'error': failure.details.get('error') if failure else None})

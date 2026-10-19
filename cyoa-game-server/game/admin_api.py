"""JSON API for the React administration pages. Every view requires the admin role."""
from functools import wraps
from pathlib import Path

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .app_api import ADMIN, require_permission
from .chat_api import body, error
from .models import AuditLog, Prompt

PROMPT_TYPES = [
    ('adventure', 'Adventure Prompt'),
    ('turn-correction', 'Turn Correction Prompt'),
    ('game-ending', 'Game Ending Prompt'),
    ('classifier', 'Classifier Prompt'),
    ('judge', 'Judge Prompt'),
    ('character', 'Character Prompt'),
    ('image-meta', 'Image Meta Prompt'),
]
AUDIT_LIST_LIMIT = 100


def admin_api(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except ValueError:
            return error('invalid_request', 'Send a valid JSON object.', 400)
    return require_permission(ADMIN)(wrapped)


def invalid(fields):
    """400 with per-field messages so forms can show them inline."""
    return JsonResponse({'error': {
        'code': 'validation_failed',
        'message': 'Please fix the highlighted fields.',
        'fields': fields,
    }}, status=400)


def valid_prompt_name(name):
    return bool(name) and name not in {'.', '..'} and not any(
        char in name for char in ('/', '\\', '\x00')
    )


def save_prompt_to_disk(prompt):
    """
    Write a prompt to its corresponding .txt file on disk.
    Creates the file if it doesn't exist, or overwrites if it does.
    Returns a success message.
    """
    import os
    
    if not valid_prompt_name(prompt.name):
        raise ValueError("Prompt name must be a simple filename without path separators.")

    # Determine base directory
    if os.path.exists('/story_prompts'):
        base_dir = '/story_prompts'
    else:
        base_dir = Path(__file__).resolve().parents[2] / 'cyoa_prompts'
    
    # Map prompt type to directory
    type_to_dir = {
        'adventure': 'story_prompts',
        'turn-correction': 'turn_correction_prompts',
        'game-ending': 'game_ending_prompts',
        'classifier': 'classifier_prompts',
        'judge': 'judge_prompts',
        'character': 'character_prompts',
        'image-meta': 'image_meta_prompts',
    }
    
    dir_name = type_to_dir.get(prompt.prompt_type)
    if not dir_name:
        raise ValueError(f"Unknown prompt type: {prompt.prompt_type}")
    
    # Build filename with version
    filename = f"{prompt.name}_v{prompt.version}.txt"
    prompt_root = Path(base_dir).resolve()
    filepath = (prompt_root / dir_name / filename).resolve()
    if not filepath.is_relative_to(prompt_root):
        raise ValueError("Prompt file must remain inside the prompt directory.")
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    # Write content
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(prompt.prompt_text)
    
    # Update file_path in model
    relative_path = f"{dir_name}/{filename}"
    prompt.file_path = relative_path
    prompt.save(update_fields=['file_path'])
    
    return f'Saved to {relative_path}'


def normalize_text(value):
    """Browsers submit CRLF; prompts are stored with LF."""
    return str(value or '').replace('\r\n', '\n')


def audit_summary(log):
    return {
        'id': log.id,
        'timestamp': log.timestamp.isoformat(),
        'was_modified': log.was_modified,
        'was_refusal': log.was_refusal,
        'preview': log.original_text[:200],
    }


def audit_full(log):
    return {
        **audit_summary(log),
        'original_text': log.original_text,
        'refined_text': log.refined_text,
        'classifier_response': log.classifier_response,
        'prompt_used': str(log.prompt_used) if log.prompt_used else None,
        'correction_prompt_used': (
            str(log.correction_prompt_used) if log.correction_prompt_used else None
        ),
        'details': log.details,
    }


def prompt_summary(prompt):
    return {
        'id': prompt.id,
        'type': prompt.prompt_type,
        'name': prompt.name,
        'version': prompt.version,
        'description': prompt.description,
    }


def prompt_full(prompt):
    versions = Prompt.objects.filter(
        prompt_type=prompt.prompt_type, name=prompt.name
    ).order_by('-version')
    return {
        **prompt_summary(prompt),
        'prompt_text': prompt.prompt_text,
        'file_path': prompt.file_path,
        'versions': [
            {'id': v.id, 'version': v.version, 'description': v.description}
            for v in versions
        ],
    }


@admin_api
@require_http_methods(['GET'])
def dashboard(request):
    total = AuditLog.objects.count()
    corrections = AuditLog.objects.filter(was_modified=True).count()
    return JsonResponse({
        'total_requests': total,
        'total_refusals': AuditLog.objects.filter(was_refusal=True).count(),
        'total_corrections': corrections,
        'correction_rate': round(corrections / total * 100, 1) if total else 0,
        'recent': [audit_summary(log) for log in AuditLog.objects.all()[:10]],
    })


@admin_api
@require_http_methods(['GET', 'DELETE'])
def audit_collection(request):
    if request.method == 'DELETE':
        deleted = AuditLog.objects.count()
        AuditLog.objects.all().delete()
        return JsonResponse({'deleted': deleted})
    logs = AuditLog.objects.all()
    if request.GET.get('modified_only') == 'true':
        logs = logs.filter(was_modified=True)
    return JsonResponse({'logs': [audit_summary(log) for log in logs[:AUDIT_LIST_LIMIT]]})


@admin_api
@require_http_methods(['GET'])
def audit_detail(request, log_id):
    log = AuditLog.objects.filter(pk=log_id).first()
    if not log:
        return error('not_found', 'Audit entry not found.', 404)
    return JsonResponse(audit_full(log))


@admin_api
@require_http_methods(['GET', 'POST'])
def prompt_collection(request):
    if request.method == 'GET':
        prompts = Prompt.objects.order_by('prompt_type', 'name', '-version')
        return JsonResponse({
            'types': [{'value': v, 'label': label} for v, label in PROMPT_TYPES],
            'prompts': [prompt_summary(p) for p in prompts],
        })
    data = body(request)
    prompt_type = data.get('type')
    name = str(data.get('name', '')).strip()
    if prompt_type not in dict(PROMPT_TYPES):
        return error('invalid_request', 'Choose a prompt type.', 400)
    if not valid_prompt_name(name):
        return error('invalid_request', 'Prompt name must be a simple filename without path separators.', 400)
    latest = Prompt.objects.filter(
        prompt_type=prompt_type, name=name
    ).order_by('-version').first()
    prompt = Prompt.objects.create(
        prompt_type=prompt_type,
        name=name,
        version=latest.version + 1 if latest else 1,
        description=str(data.get('description', '')),
        prompt_text=normalize_text(data.get('prompt_text')),
    )
    return JsonResponse(prompt_full(prompt), status=201)


@admin_api
@require_http_methods(['GET', 'PUT'])
def prompt_detail(request, prompt_id):
    prompt = Prompt.objects.filter(pk=prompt_id).first()
    if not prompt:
        return error('not_found', 'Prompt not found.', 404)
    if request.method == 'PUT':
        data = body(request)
        prompt.description = str(data.get('description', prompt.description))
        prompt.prompt_text = normalize_text(data.get('prompt_text', prompt.prompt_text))
        prompt.save()
    return JsonResponse(prompt_full(prompt))


@admin_api
@require_http_methods(['POST'])
def prompt_new_version(request, prompt_id):
    prompt = Prompt.objects.filter(pk=prompt_id).first()
    if not prompt:
        return error('not_found', 'Prompt not found.', 404)
    data = body(request)
    latest = Prompt.objects.filter(
        prompt_type=prompt.prompt_type, name=prompt.name
    ).order_by('-version').first()
    created = Prompt.objects.create(
        prompt_type=prompt.prompt_type,
        name=prompt.name,
        version=latest.version + 1,
        description=str(data.get('description', '')),
        prompt_text=normalize_text(data.get('prompt_text')),
    )
    return JsonResponse(prompt_full(created), status=201)


@admin_api
@require_http_methods(['POST'])
def prompt_save_to_disk(request, prompt_id):

    prompt = Prompt.objects.filter(pk=prompt_id).first()
    if not prompt:
        return error('not_found', 'Prompt not found.', 404)
    try:
        message = save_prompt_to_disk(prompt)
    except ValueError as exc:
        return error('invalid_request', str(exc), 400)
    except Exception as exc:
        return error('save_failed', f'Failed to save to disk: {exc}', 500)
    return JsonResponse({'message': message, 'prompt': prompt_full(prompt)})


@admin_api
@require_http_methods(['GET'])
def chat_collection(request):
    """Find chats across all players for administrator inspection."""
    from django.db.models import Q
    from .models import ChatConversation
    search = request.GET.get('search', '').strip()
    offset = max(0, int(request.GET.get('offset', 0)))
    chats = ChatConversation.objects.select_related('user').order_by('-updated_at', '-pk')
    if search:
        chats = chats.filter(Q(title__icontains=search) | Q(user__username__icontains=search)
                             | Q(user__email__icontains=search) | Q(conversation_id__icontains=search))
    rows = list(chats[offset:offset + 51])
    return JsonResponse({
        'chats': [{'id': c.conversation_id, 'title': c.title,
                   'owner': c.user.email or c.user.get_username(),
                   'updated_at': c.updated_at.isoformat()} for c in rows[:50]],
        'has_more': len(rows) > 50,
    })

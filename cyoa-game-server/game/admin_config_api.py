"""Admin JSON API: game configurations with their judge steps and workflow."""
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .admin_api import admin_api, invalid, prompt_summary
from .chat_api import body, error
from .models import Configuration, DifficultyProfile, JudgeStep, LLMModel, Prompt, GameSession

CONFIG_INT_FIELDS = {
    'storyteller_timeout': (60, 1),
    'image_timeout': (60, 1),
    'turn_correction_timeout': (60, 1),
    'classifier_timeout': (60, 1),
    'total_turns': (10, 1),
    'phase1_turns': (3, 0),
    'phase2_turns': (3, 0),
    'phase3_turns': (3, 0),
    'phase4_turns': (1, 0),
}
CONFIG_TEXT_FIELDS = ('description', 'classifier_question')
CONFIG_PROMPT_FIELDS = {
    'adventure_prompt': 'adventure',
    'image_meta_prompt': 'image-meta',
    'character_prompt': 'character',
    'turn_correction_prompt': 'turn-correction',
    'game_ending_turn_correction_prompt': 'turn-correction',
    'game_ending_prompt': 'game-ending',
    'classifier_prompt': 'classifier',
}
CONFIG_MODEL_FIELDS = ('storyteller_model', 'turn_correction_model', 'classifier_model', 'image_model')
STEP_PROMPTS = {'classifier_prompt': 'classifier', 'rewrite_prompt': 'judge', 'compare_prompt': 'judge'}
STEP_MODELS = ('classifier_model', 'rewrite_model', 'compare_model')
STEP_INTS = {
    'classifier_timeout': 10, 'rewrite_timeout': 60, 'compare_timeout': 60, 'max_rewrite_attempts': 3,
}
STEP_TEXT = ('classifier_question', 'rewrite_instruction', 'compare_question')
STEP_BOOLS = ('enabled', 'classifier_use_full_context', 'rewrite_use_full_context', 'compare_use_full_context')
REFUSAL_REQUIRED = {
    'turn_correction_prompt': 'Turn correction prompt is required when refusal detection is on.',
    'turn_correction_model': 'Turn correction model is required when refusal detection is on.',
    'classifier_prompt': 'Classifier prompt is required when refusal detection is on.',
    'classifier_model': 'Classifier model is required when refusal detection is on.',
}


def step_json(step):
    data = {'id': step.id, 'name': step.name}
    for key in STEP_BOOLS:
        data[key] = getattr(step, key)
    for key in STEP_INTS:
        data[key] = getattr(step, key)
    for key in STEP_TEXT:
        data[key] = getattr(step, key)
    for key in (*STEP_PROMPTS, *STEP_MODELS):
        data[key] = getattr(step, f'{key}_id')
    return data


def config_summary(config):
    return {
        'id': config.id,
        'name': config.name,
        'is_active': config.is_active,
        'in_progress_count': GameSession.objects.filter(configuration=config, game_over=False).count(),
        'description': config.description,
        'storyteller_model': config.storyteller_model.name if config.storyteller_model else '',
        'total_turns': config.total_turns,
        'enable_refusal_detection': config.enable_refusal_detection,
        'enable_tts': config.enable_tts,
        'enable_image_generation': config.enable_image_generation,
        'image_aspect_ratio': config.image_aspect_ratio,
    }


def config_json(config):
    data = {
        'id': config.id,
        'name': config.name,
        'is_active': config.is_active,
        'in_progress_count': GameSession.objects.filter(configuration=config, game_over=False).count(),
        'enable_tts': config.enable_tts,
        'enable_image_generation': config.enable_image_generation,
        'image_aspect_ratio': config.image_aspect_ratio,
        'enable_refusal_detection': config.enable_refusal_detection,
        'difficulty': config.difficulty_id,
        'workflow': config.workflow or {},
        'judge_steps': [
            step_json(s) for s in JudgeStep.objects.filter(configuration=config).order_by('order', 'id')
        ],
    }
    for key in CONFIG_INT_FIELDS:
        data[key] = getattr(config, key)
    for key in CONFIG_TEXT_FIELDS:
        data[key] = getattr(config, key)
    for key in (*CONFIG_PROMPT_FIELDS, *CONFIG_MODEL_FIELDS):
        data[key] = getattr(config, f'{key}_id')
    return data


def pk_or_none(value):
    if value in (None, '', 0):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def lookup(model, value, label, fields, key, **extra):
    """Resolve an optional foreign-key id, recording a field error when it is unknown."""
    pk = pk_or_none(value)
    if pk is None:
        return None
    found = model.objects.filter(pk=pk, **extra).first()
    if not found:
        fields[key] = f'Choose a valid {label}.'
    return found


def read_int(data, key, default, minimum, fields, prefix=''):
    try:
        value = int(data.get(key, default))
    except (TypeError, ValueError):
        fields[prefix + key] = 'Must be a whole number.'
        return default
    if value < minimum:
        fields[prefix + key] = f'Must be at least {minimum}.'
    return value


def parse_step(data, index, fields):
    prefix = f'judge_steps.{index}.'
    step_fields = {}
    values = {
        'name': str(data.get('name') or '').strip() or f'Step {index + 1}',
        'order': index,
    }
    for key in STEP_BOOLS:
        values[key] = bool(data.get(key, key == 'enabled'))
    for key, default in STEP_INTS.items():
        values[key] = read_int(data, key, default, 1, step_fields)
    for key in STEP_TEXT:
        values[key] = str(data.get(key) or '').strip()
    for key, prompt_type in STEP_PROMPTS.items():
        values[key] = lookup(Prompt, data.get(key), 'prompt', step_fields, key, prompt_type=prompt_type)
    for key in STEP_MODELS:
        values[key] = lookup(LLMModel, data.get(key), 'model', step_fields, key)
    for key in ('rewrite_prompt', 'rewrite_model', 'compare_prompt', 'compare_model'):
        if values[key] is None and key not in step_fields:
            step_fields[key] = 'Required (the classifier phase is optional).'
    fields.update({prefix + key: message for key, message in step_fields.items()})
    return values


def parse_config(data):
    """Returns (values, judge_step_values, fields) from a request payload."""
    fields = {}
    values = {}
    values['is_active'] = bool(data.get('is_active', True))
    values['name'] = str(data.get('name') or '').strip()
    if not values['name']:
        fields['name'] = 'Configuration name is required.'
    for key, (default, minimum) in CONFIG_INT_FIELDS.items():
        values[key] = read_int(data, key, default, minimum, fields)
    for key in CONFIG_TEXT_FIELDS:
        values[key] = str(data.get(key) or '').strip()
    if not values['classifier_question']:
        values['classifier_question'] = 'Is this a content policy refusal?'
    values['enable_tts'] = bool(data.get('enable_tts'))
    values['enable_image_generation'] = bool(data.get('enable_image_generation'))
    values['image_aspect_ratio'] = str(data.get('image_aspect_ratio', '16:9'))
    if values['image_aspect_ratio'] not in ('1:1', '16:9', '9:16', '4:3', '3:4', '3:2', '2:3'):
        fields['image_aspect_ratio'] = 'Choose a listed aspect ratio.'
    values['enable_refusal_detection'] = bool(data.get('enable_refusal_detection'))
    for key, prompt_type in CONFIG_PROMPT_FIELDS.items():
        values[key] = lookup(Prompt, data.get(key), 'prompt', fields, key, prompt_type=prompt_type)
    for key in CONFIG_MODEL_FIELDS:
        values[key] = lookup(LLMModel, data.get(key), 'model', fields, key)
    for key in CONFIG_MODEL_FIELDS:
        if key != 'image_model' and values[key] and values[key].capabilities.get('image_generation'):
            fields[key] = 'Choose a text model for this role.'
    image_model = values['image_model']
    if image_model and (image_model.provider.provider_type != 'openrouter'
                        or not image_model.capabilities.get('image_generation')
                        or 'vector' in image_model.model_identifier.lower()
                        or not image_model.is_available or not image_model.provider.is_active):
        fields['image_model'] = 'Choose an available OpenRouter image model.'
    if values['enable_image_generation']:
        for key in ('image_meta_prompt', 'image_model'):
            if values[key] is None and key not in fields:
                fields[key] = 'Required when image generation is enabled.'
        if image_model and not image_model.provider.api_key:
            fields['image_model'] = 'Configure an API key for this image model’s provider.'
    values['difficulty'] = lookup(DifficultyProfile, data.get('difficulty'), 'difficulty', fields, 'difficulty')

    for key, label in (('adventure_prompt', 'Adventure prompt'), ('game_ending_prompt', 'Game ending prompt'),
                       ('storyteller_model', 'Storyteller model')):
        if values[key] is None and key not in fields:
            fields[key] = f'{label} is required.'
    if values['enable_refusal_detection']:
        for key, message in REFUSAL_REQUIRED.items():
            if values[key] is None and key not in fields:
                fields[key] = message
    else:
        for key in REFUSAL_REQUIRED:
            values[key] = None

    workflow = data.get('workflow') or {}
    if not isinstance(workflow, dict):
        fields['workflow'] = 'Workflow must be a JSON object.'
    elif workflow:
        from .engine.turn_execution import validate_workflow
        try:
            validate_workflow(workflow)
        except ValueError as exc:
            fields['workflow'] = str(exc)
    values['workflow'] = workflow

    raw_steps = data.get('judge_steps') or []
    if not isinstance(raw_steps, list):
        fields['judge_steps'] = 'Judge steps must be a list.'
        raw_steps = []
    steps = [
        (raw.get('id') if isinstance(raw, dict) else None, parse_step(raw if isinstance(raw, dict) else {}, i, fields))
        for i, raw in enumerate(raw_steps)
    ]
    return values, steps, fields


@transaction.atomic
def save_config(config, values, steps):
    for key, value in values.items():
        setattr(config, key, value)
    config.save()
    existing = {s.id: s for s in JudgeStep.objects.filter(configuration=config)}
    keep = set()
    for step_id, step_values in steps:
        step = existing.get(step_id) or JudgeStep(configuration=config)
        for key, value in step_values.items():
            setattr(step, key, value)
        step.save()
        keep.add(step.id)
    for step_id, step in existing.items():
        if step_id not in keep:
            step.delete()
    return config


@admin_api
@require_http_methods(['GET'])
def config_options(request):
    def prompts(kind):
        return [prompt_summary(p) for p in Prompt.objects.filter(prompt_type=kind).order_by('name', '-version')]

    return JsonResponse({
        'adventure_prompts': prompts('adventure'),
        'turn_correction_prompts': prompts('turn-correction'),
        'game_ending_prompts': prompts('game-ending'),
        'classifier_prompts': prompts('classifier'),
        'judge_prompts': prompts('judge'),
        'character_prompts': prompts('character'),
        'image_meta_prompts': prompts('image-meta'),
        'image_models': [
            {'id': m.id, 'name': m.name, 'available': m.is_available}
            for m in LLMModel.objects.select_related('provider').filter(
                provider__provider_type='openrouter', provider__is_active=True,
                is_available=True, capabilities__image_generation=True).exclude(
                    model_identifier__icontains='vector').order_by('name')
        ],
        'models': [
            {'id': m.id, 'name': m.name, 'available': m.is_available}
            for m in LLMModel.objects.select_related('provider').order_by('provider__name', 'name')
            if not (m.capabilities or {}).get('image_generation')
        ],
        'difficulties': [
            {'id': d.id, 'name': d.name} for d in DifficultyProfile.objects.all()
        ],
    })


@admin_api
@require_http_methods(['GET', 'POST'])
def config_collection(request):
    if request.method == 'GET':
        configs = Configuration.objects.select_related('storyteller_model')
        return JsonResponse({'configurations': [
            {**config_summary(c), 'judge_step_count': JudgeStep.objects.filter(configuration=c).count()}
            for c in configs
        ]})
    values, steps, fields = parse_config(body(request))
    if fields:
        return invalid(fields)
    config = save_config(Configuration(), values, steps)
    return JsonResponse(config_json(config), status=201)


@admin_api
@require_http_methods(['GET', 'PUT', 'DELETE'])
def config_detail(request, config_id):
    config = Configuration.objects.filter(pk=config_id).first()
    if not config:
        return error('not_found', 'Configuration not found.', 404)
    if request.method == 'DELETE':
        try:
            config.delete()
        except ProtectedError:
            return error('in_use', 'This configuration is still referenced.', 409)
        return JsonResponse({'deleted': True})
    if request.method == 'PUT':
        values, steps, fields = parse_config(body(request))
        if fields:
            return invalid(fields)
        save_config(config, values, steps)
    return JsonResponse(config_json(config))

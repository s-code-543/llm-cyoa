"""Admin JSON API: providers, models, difficulty profiles and voice settings."""
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .admin_api import admin_api, invalid
from .anthropic_utils import get_anthropic_models, test_anthropic_connection
from .chat_api import body, error
from .models import (
    APIProvider, Configuration, DifficultyProfile, JudgeStep, LLMModel, TTSSettings,
)
from .ollama_utils import get_ollama_models, test_ollama_connection
from .openai_utils import get_openai_models, test_openai_connection
from .openrouter_utils import get_openrouter_models, test_openrouter_connection

PROVIDER_TYPES = [{'value': v, 'label': label} for v, label in APIProvider.PROVIDER_TYPES]


def provider_json(provider):
    key = provider.api_key
    return {
        'id': provider.id,
        'name': provider.name,
        'provider_type': provider.provider_type,
        'base_url': provider.base_url,
        'has_api_key': bool(key),
        'api_key_hint': key[-4:] if len(key) > 8 else '',
        'is_active': provider.is_active,
        'last_tested': provider.last_tested.isoformat() if provider.last_tested else None,
        'test_status': provider.test_status,
        'model_count': provider.llmmodel_set.count(),
    }


def run_connection_test(provider_type, base_url, api_key):
    if provider_type == 'ollama':
        return test_ollama_connection(base_url)
    if provider_type == 'anthropic':
        return test_anthropic_connection(api_key)
    if provider_type == 'openai':
        return test_openai_connection(api_key)
    if provider_type == 'openrouter':
        return test_openrouter_connection(api_key)
    return {'success': False, 'message': 'Unknown provider type'}


def fetch_provider_models(provider):
    if provider.provider_type == 'ollama':
        return get_ollama_models(provider.base_url)
    if provider.provider_type == 'anthropic':
        return get_anthropic_models(provider.api_key)
    if provider.provider_type == 'openai':
        return get_openai_models(provider.api_key)
    if provider.provider_type == 'openrouter':
        return get_openrouter_models(provider.api_key)
    return []


def pricing_metadata(item, checked_at=None):
    pricing = item.get('pricing')
    return {
        'pricing': pricing if isinstance(pricing, dict) else {},
        'pricing_updated_at': checked_at or timezone.now().isoformat(),
    }


def catalog_metadata(item):
    return {
        'context_length': item.get('context_length', 0),
        'created': item.get('created'),
        'architecture': item.get('architecture') or {},
        'supported_parameters': item.get('supported_parameters') or {},
    }


def get_provider(provider_id):
    return APIProvider.objects.filter(pk=provider_id).first()


def not_found(what):
    return error('not_found', f'{what} not found.', 404)


def provider_field_errors(name, provider_type, exclude=None):
    fields = {}
    if not name:
        fields['name'] = 'Name is required.'
    elif APIProvider.objects.filter(name=name).exclude(pk=exclude).exists():
        fields['name'] = 'A provider with this name already exists.'
    if provider_type not in dict(APIProvider.PROVIDER_TYPES):
        fields['provider_type'] = 'Choose a provider type.'
    return fields


@admin_api
@require_http_methods(['GET', 'POST'])
def provider_collection(request):
    if request.method == 'GET':
        return JsonResponse({
            'types': PROVIDER_TYPES,
            'providers': [provider_json(p) for p in APIProvider.objects.all()],
        })
    data = body(request)
    name = str(data.get('name', '')).strip()
    provider_type = data.get('provider_type')
    fields = provider_field_errors(name, provider_type)
    if fields:
        return invalid(fields)
    provider = APIProvider.objects.create(
        name=name,
        provider_type=provider_type,
        base_url=str(data.get('base_url', '')).strip(),
        api_key=str(data.get('api_key', '')).strip(),
        is_active=True,
    )
    return JsonResponse(provider_json(provider), status=201)


@admin_api
@require_http_methods(['GET', 'PUT', 'DELETE'])
def provider_detail(request, provider_id):
    provider = get_provider(provider_id)
    if not provider:
        return not_found('Provider')
    if request.method == 'DELETE':
        try:
            provider.delete()
        except ProtectedError:
            return error('in_use', 'A model from this provider is used by a configuration.', 409)
        return JsonResponse({'deleted': True})
    if request.method == 'PUT':
        data = body(request)
        name = str(data.get('name', provider.name)).strip()
        provider_type = data.get('provider_type', provider.provider_type)
        fields = provider_field_errors(name, provider_type, exclude=provider.pk)
        if fields:
            return invalid(fields)
        provider.name = name
        provider.provider_type = provider_type
        provider.base_url = str(data.get('base_url', provider.base_url)).strip()
        new_key = str(data.get('api_key') or '').strip()
        if new_key:
            provider.api_key = new_key
        elif data.get('clear_api_key'):
            provider.api_key = ''
        provider.save()
    return JsonResponse(provider_json(provider))


@admin_api
@require_http_methods(['POST'])
def provider_test(request):
    data = body(request)
    provider = get_provider(data.get('provider_id')) if data.get('provider_id') else None
    api_key = str(data.get('api_key') or '').strip() or (provider.api_key if provider else '')
    result = run_connection_test(
        data.get('provider_type'), str(data.get('base_url', '')).strip(), api_key,
    )
    if provider and result.get('success'):
        provider.last_tested = timezone.now()
        provider.test_status = result['message']
        provider.save()
    return JsonResponse({'success': bool(result.get('success')), 'message': result.get('message', '')})


@admin_api
@require_http_methods(['GET'])
def provider_models(request, provider_id):
    provider = get_provider(provider_id)
    if not provider:
        return not_found('Provider')
    imported = set(
        LLMModel.objects.filter(provider=provider).values_list('model_identifier', flat=True)
    )
    available = [
        {
            'id': m['id'],
            'name': m.get('name', m['id']),
            'description': m.get('description', ''),
            'size': m.get('size', 0),
            'imported': m['id'] in imported,
            'image_generation': bool(m.get('image_generation')),
            'pricing': m.get('pricing') or {},
            **catalog_metadata(m),
        }
        for m in fetch_provider_models(provider)
    ]
    return JsonResponse({'provider': provider_json(provider), 'models': available})


def model_ids_from(request):
    ids = body(request).get('model_ids')
    if not isinstance(ids, list) or not ids:
        return None
    return [str(i) for i in ids]


@admin_api
@require_http_methods(['POST'])
def provider_models_import(request, provider_id):
    provider = get_provider(provider_id)
    if not provider:
        return not_found('Provider')
    wanted = model_ids_from(request)
    if not wanted:
        return error('invalid_request', 'Select at least one model.', 400)
    count = 0
    for item in fetch_provider_models(provider):
        if item['id'] in wanted:
            LLMModel.objects.update_or_create(
                provider=provider,
                model_identifier=item['id'],
                defaults={
                    'name': f"{provider.name}: {item['name']}",
                    'is_available': True,
                    'capabilities': {
                        **pricing_metadata(item),
                        **catalog_metadata(item),
                        'description': item.get('description', ''),
                        'size': item.get('size', 0),
                        'image_generation': bool(item.get('image_generation')),
                        'supported_parameters': item.get('supported_parameters', {}),
                    },
                },
            )
            count += 1
    return JsonResponse({'message': f'Imported {count} models from {provider.name}', 'imported': count})


@admin_api
@require_http_methods(['POST'])
def provider_models_remove(request, provider_id):
    provider = get_provider(provider_id)
    if not provider:
        return not_found('Provider')
    wanted = model_ids_from(request)
    if not wanted:
        return error('invalid_request', 'Select at least one model.', 400)
    try:
        removed, _ = LLMModel.objects.filter(
            provider=provider, model_identifier__in=wanted
        ).delete()
    except ProtectedError:
        return error('in_use', 'A selected model is used by a configuration.', 409)
    return JsonResponse({'message': f'Removed {removed} models from {provider.name}', 'removed': removed})


@admin_api
@require_http_methods(['POST'])
def provider_models_sync(request, provider_id):
    provider = get_provider(provider_id)
    if not provider:
        return not_found('Provider')
    available = fetch_provider_models(provider)
    if not available:
        return error(
            'provider_unavailable',
            f'Could not fetch models from {provider.name}. Provider may be unavailable.',
            502,
        )
    valid = {m['id'] for m in available}
    removed = updated = skipped = 0
    for model in LLMModel.objects.filter(provider=provider):
        if model.model_identifier not in valid:
            try:
                model.delete()
                removed += 1
            except ProtectedError:
                skipped += 1
        else:
            item = next(m for m in available if m['id'] == model.model_identifier)
            capabilities = dict(model.capabilities or {})
            capabilities.update(pricing_metadata(item))
            capabilities.update(catalog_metadata(item))
            capabilities.update(image_generation=bool(item.get('image_generation')),
                                supported_parameters=item.get('supported_parameters', {}))
            if not model.is_available or model.capabilities != capabilities:
                model.is_available = True
                model.capabilities = capabilities
                model.save(update_fields=['is_available', 'capabilities'])
                updated += 1
    parts = []
    if removed:
        parts.append(f'removed {removed} invalid models')
    if updated:
        parts.append(f'updated {updated} models')
    if skipped:
        parts.append(f'kept {skipped} unavailable models that are in use')
    message = f"Sync complete: {' and '.join(parts)}" if parts else 'All models are in sync with provider'
    return JsonResponse({'message': message, 'removed': removed, 'updated': updated})


def model_json(model):
    return {
        'id': model.id,
        'name': model.name,
        'model_identifier': model.model_identifier,
        'provider_id': model.provider_id,
        'provider_name': model.provider.name,
        'provider_type': model.provider.provider_type,
        'is_available': model.is_available,
        **catalog_metadata(model.capabilities or {}),
        'pricing': (model.capabilities or {}).get('pricing', {}),
        'pricing_updated_at': (model.capabilities or {}).get('pricing_updated_at'),
        'description': (model.capabilities or {}).get('description', ''),
        'image_generation': bool((model.capabilities or {}).get('image_generation')),
    }


@admin_api
@require_http_methods(['GET'])
def model_collection(request):
    models = LLMModel.objects.select_related('provider')
    return JsonResponse({
        'models': [model_json(m) for m in models],
        'providers': [{'id': p.id, 'name': p.name} for p in APIProvider.objects.filter(is_active=True)],
    })


@admin_api
@require_http_methods(['POST'])
def refresh_model_pricing(request):
    """Refresh saved rates without removing models or changing availability."""
    updated, failures = 0, []
    for provider in APIProvider.objects.filter(llmmodel__isnull=False).distinct():
        try:
            catalog = fetch_provider_models(provider)
            if not catalog:
                raise ValueError('No catalog returned')
            items = {item['id']: item for item in catalog}
        except Exception:
            failures.append(f'Could not refresh costs from {provider.name}; saved prices were kept.')
            continue
        checked_at = timezone.now().isoformat()
        for model in LLMModel.objects.filter(provider=provider):
            item = items.get(model.model_identifier)
            if item is None:
                failures.append(f'{model.name} was absent from the catalog; its saved price was kept.')
                continue
            capabilities = dict(model.capabilities or {})
            capabilities.update(pricing_metadata(item, checked_at))
            capabilities.update(catalog_metadata(item))
            model.capabilities = capabilities
            model.save(update_fields=['capabilities'])
            updated += 1
    return JsonResponse({'message': f'Refreshed costs for {updated} models.', 'failures': failures})


@admin_api
@require_http_methods(['POST'])
def validate_models(request):
    """Catalog failures must never be interpreted as missing models."""
    data = body(request)
    if 'delete_ids' in data:
        ids = data['delete_ids']
        if not isinstance(ids, list) or any(type(pk) is not int for pk in ids):
            return error('invalid_request', 'Select models from validation results.', 400)
        removed, _ = LLMModel.objects.filter(pk__in=ids, is_available=False).delete()
        return JsonResponse({'message': f'Deleted {removed} unavailable models.', 'removed': removed})
    unavailable, failures = [], []
    for provider in APIProvider.objects.filter(llmmodel__isnull=False).distinct():
        try:
            catalog = fetch_provider_models(provider)
            if not catalog:
                raise ValueError('No catalog returned')
            available = {item['id']: item for item in catalog}
        except Exception:
            failures.append(f'Could not validate {provider.name}; its models were left unchanged.')
            continue
        for model in LLMModel.objects.filter(provider=provider):
            model.is_available = model.model_identifier in available
            if model.is_available:
                model.capabilities = {**(model.capabilities or {}), **pricing_metadata(available[model.model_identifier]),
                                      **catalog_metadata(available[model.model_identifier])}
            model.save(update_fields=['is_available', 'capabilities'])
            if not model.is_available:
                unavailable.append(model_json(model))
    return JsonResponse({'unavailable': unavailable, 'failures': failures})


def model_usage(model):
    names = list(
        Configuration.objects.filter(
            Q(storyteller_model=model) | Q(turn_correction_model=model) | Q(classifier_model=model) | Q(image_model=model)
        ).distinct().values_list('name', flat=True)
    )
    for step in JudgeStep.objects.filter(
        Q(classifier_model=model) | Q(rewrite_model=model) | Q(compare_model=model)
    ).select_related('configuration'):
        if step.configuration.name not in names:
            names.append(step.configuration.name)
    return names


@admin_api
@require_http_methods(['DELETE'])
def model_detail(request, model_id):
    model = LLMModel.objects.filter(pk=model_id).first()
    if not model:
        return not_found('Model')
    try:
        model.delete()
    except ProtectedError:
        used_by = ', '.join(f'"{n}"' for n in model_usage(model))
        return error(
            'in_use',
            f'Cannot delete "{model.name}" because it is used by: {used_by or "other objects"}. '
            'Update or delete those configurations first.',
            409,
        )
    return JsonResponse({'deleted': True})


def difficulty_json(profile):
    return {
        'id': profile.id,
        'name': profile.name,
        'description': profile.description,
        'function': profile.function,
        'curve_points': profile.curve_points,
    }


def valid_curve(points):
    return (
        isinstance(points, list)
        and len(points) == 5
        and all(isinstance(p, (int, float)) and not isinstance(p, bool) and 0 <= p <= 1 for p in points)
    )


def apply_difficulty(profile, data):
    """Returns field errors, or None after assigning validated values."""
    name = str(data.get('name', '')).strip()
    fields = {}
    if not name:
        fields['name'] = 'Name is required.'
    elif DifficultyProfile.objects.filter(name=name).exclude(pk=profile.pk).exists():
        fields['name'] = 'A profile with this name already exists.'
    points = data.get('curve_points')
    function = ''
    if points is not None:
        if valid_curve(points):
            function = DifficultyProfile.from_curve_points(points)
        else:
            fields['curve_points'] = 'Provide five values between 0 and 1.'
    else:
        function = str(data.get('function', '')).strip()
        if not function:
            fields['function'] = 'Enter a function or draw a curve.'
    if function and 'function' not in fields:
        try:
            eval(function, {'__builtins__': {}}, {'x': 1, 'n': 10, 'min': min, 'max': max})
        except Exception as exc:
            fields['function'] = f'Function could not be evaluated: {exc}'
    if fields:
        return fields
    profile.name = name
    profile.description = str(data.get('description', ''))
    profile.function = function
    profile.curve_points = points
    return None


@admin_api
@require_http_methods(['GET', 'POST'])
def difficulty_collection(request):
    if request.method == 'GET':
        return JsonResponse({'profiles': [difficulty_json(p) for p in DifficultyProfile.objects.all()]})
    profile = DifficultyProfile()
    fields = apply_difficulty(profile, body(request))
    if fields:
        return invalid(fields)
    profile.save()
    return JsonResponse(difficulty_json(profile), status=201)


@admin_api
@require_http_methods(['GET', 'PUT', 'DELETE'])
def difficulty_detail(request, difficulty_id):
    profile = DifficultyProfile.objects.filter(pk=difficulty_id).first()
    if not profile:
        return not_found('Difficulty profile')
    if request.method == 'DELETE':
        try:
            profile.delete()
        except ProtectedError:
            return error('in_use', 'This profile is used by a configuration.', 409)
        return JsonResponse({'deleted': True})
    if request.method == 'PUT':
        fields = apply_difficulty(profile, body(request))
        if fields:
            return invalid(fields)
        profile.save()
    return JsonResponse(difficulty_json(profile))


def choices_of(field):
    return [{'value': v, 'label': label} for v, label in TTSSettings._meta.get_field(field).choices]


def tts_json(settings):
    return {
        'enabled': settings.enabled,
        'openai_model': settings.openai_model,
        'openai_voice': settings.openai_voice,
        'max_text_length': settings.max_text_length,
        'audio_retention_days': settings.audio_retention_days,
        'auto_cleanup_enabled': settings.auto_cleanup_enabled,
        'model_choices': choices_of('openai_model'),
        'voice_choices': choices_of('openai_voice'),
    }


def whole_number(data, key, current, low, high=None):
    try:
        value = int(data.get(key, current))
    except (TypeError, ValueError):
        return current, 'Must be a whole number.'
    if value < low or (high is not None and value > high):
        bounds = f'between {low} and {high}' if high else f'at least {low}'
        return current, f'Must be {bounds}.'
    return value, None


@admin_api
@require_http_methods(['GET', 'PUT'])
def tts_settings(request):
    settings = TTSSettings.get_settings()
    if request.method == 'PUT':
        data = body(request)
        fields = {}
        length, problem = whole_number(data, 'max_text_length', settings.max_text_length, 1, 4096)
        if problem:
            fields['max_text_length'] = problem
        days, problem = whole_number(data, 'audio_retention_days', settings.audio_retention_days, 1)
        if problem:
            fields['audio_retention_days'] = problem
        for key in ('openai_model', 'openai_voice'):
            allowed = {c['value'] for c in choices_of(key)}
            if data.get(key, getattr(settings, key)) not in allowed:
                fields[key] = 'Choose a listed option.'
        if fields:
            return invalid(fields)
        settings.enabled = bool(data.get('enabled', settings.enabled))
        settings.openai_model = data.get('openai_model', settings.openai_model)
        settings.openai_voice = data.get('openai_voice', settings.openai_voice)
        settings.max_text_length = length
        settings.audio_retention_days = days
        settings.auto_cleanup_enabled = bool(data.get('auto_cleanup_enabled', settings.auto_cleanup_enabled))
        settings.save()
    return JsonResponse(tts_json(settings))

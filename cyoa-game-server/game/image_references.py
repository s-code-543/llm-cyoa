"""Private, reusable character sheets and scene references for illustrations."""
import base64
import uuid

from django.core.files.base import ContentFile
from django.http import FileResponse, Http404, JsonResponse
from django.views.decorators.http import require_http_methods
from PIL import Image, UnidentifiedImageError

from .admin_api import admin_api
from .chat_api import error
from .models import ImageReference

MAX_REFERENCE_BYTES = 8 * 1024 * 1024
MAX_REFERENCES = 4


def reference_limit(model):
    """None means older catalog metadata does not state the input limit."""
    metadata = model.capabilities or {}
    parameters = metadata.get('supported_parameters')
    if isinstance(parameters, dict) and parameters:
        descriptor = parameters.get('input_references')
        if not descriptor:
            return 0
        if isinstance(descriptor, dict) and isinstance(descriptor.get('max'), (int, float)):
            return max(0, int(descriptor['max']))
    modalities = (metadata.get('architecture') or {}).get('input_modalities')
    if modalities and 'image' not in modalities:
        return 0
    return None


def reference_json(reference):
    return {'id': str(reference.pk), 'name': reference.name, 'kind': reference.kind,
            'url': f'/api/v1/admin/image-references/{reference.pk}'}


@admin_api
@require_http_methods(['POST'])
def upload_reference(request):
    upload = request.FILES.get('image')
    kind = request.POST.get('kind')
    if kind not in ('character', 'scene'):
        return error('invalid_reference', 'Choose a character sheet or scene reference.', 400)
    if not upload or upload.size > MAX_REFERENCE_BYTES:
        return error('invalid_reference', 'Upload a PNG, JPEG or WebP image up to 8 MB.', 400)
    try:
        with Image.open(upload) as image:
            if image.format not in ('PNG', 'JPEG', 'WEBP') or image.width * image.height > 40_000_000:
                raise ValueError('Unsupported image')
            media_type = Image.MIME[image.format]
            extension = {'PNG': 'png', 'JPEG': 'jpg', 'WEBP': 'webp'}[image.format]
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return error('invalid_reference', 'Upload a valid PNG, JPEG or WebP image (up to 40 megapixels).', 400)
    upload.seek(0)
    reference = ImageReference(name=str(request.POST.get('name') or upload.name)[:160],
                               kind=kind, media_type=media_type)
    reference.image.save(f'{uuid.uuid4().hex}.{extension}', ContentFile(upload.read()), save=True)
    return JsonResponse(reference_json(reference), status=201)


@admin_api
@require_http_methods(['GET'])
def reference_image(request, reference_id):
    reference = ImageReference.objects.filter(pk=reference_id).first()
    if not reference:
        raise Http404
    try:
        response = FileResponse(reference.image.open('rb'), content_type=reference.media_type)
    except FileNotFoundError:
        raise Http404
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


def reference_inputs(config):
    """Read private files locally; never ask the provider to fetch authenticated URLs."""
    references, descriptions = [], []
    for index, reference in enumerate(config.image_references.order_by('kind', 'id'), 1):
        with reference.image.open('rb') as image:
            encoded = base64.b64encode(image.read()).decode('ascii')
        references.append({'type': 'image_url', 'image_url': {
            'url': f'data:{reference.media_type};base64,{encoded}'}})
        purpose = 'character appearance sheet' if reference.kind == 'character' else 'scene/environment reference'
        descriptions.append(f'Reference {index}: {reference.name} ({purpose}).')
    return references, descriptions

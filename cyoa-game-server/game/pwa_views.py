"""
Views that serve PWA root-level files (service worker, favicon, manifest).
"""
from django.http import FileResponse
from django.conf import settings
from pathlib import Path


STATIC_DIR = Path(settings.BASE_DIR) / 'static'
ICONS_DIR = STATIC_DIR / 'icons'


def service_worker(request):
    """Serve SW from root scope with correct headers."""
    sw_path = STATIC_DIR / 'js' / 'sw.js'
    response = FileResponse(
        open(sw_path, 'rb'),
        content_type='application/javascript',
    )
    response['Service-Worker-Allowed'] = '/'
    response['Cache-Control'] = 'no-cache'
    return response


def favicon_ico(request):
    """Serve favicon.ico from root so browsers find it automatically."""
    return FileResponse(
        open(ICONS_DIR / 'favicon.ico', 'rb'),
        content_type='image/x-icon',
    )


def apple_touch_icon(request):
    """Serve apple-touch-icon.png from root for iOS home screen."""
    return FileResponse(
        open(ICONS_DIR / 'apple-touch-icon.png', 'rb'),
        content_type='image/png',
    )


def web_manifest(request):
    """Serve webmanifest from root with correct content type."""
    manifest_path = STATIC_DIR / 'site.webmanifest'
    return FileResponse(
        open(manifest_path, 'rb'),
        content_type='application/manifest+json',
    )

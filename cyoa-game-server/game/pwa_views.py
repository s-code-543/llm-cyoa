"""
Views that serve PWA root-level files (service worker, favicon, manifest, offline page).
"""
from django.http import FileResponse, HttpResponse, Http404
from django.conf import settings
from pathlib import Path


STATIC_DIR = Path(settings.BASE_DIR) / 'static'
ICONS_DIR = STATIC_DIR / 'icons'


def _serve_file(path, content_type, extra_headers=None):
    """Serve a static file with proper content type (CORS headers added by middleware)."""
    if not path.exists():
        raise Http404(f"File not found: {path.name}")    
    response = FileResponse(
        open(path, 'rb'),
        content_type=content_type,
    )
    
    if extra_headers:
        for key, value in extra_headers.items():
            response[key] = value
    return response


def service_worker(request):
    """Serve SW from root scope with correct headers."""
    return _serve_file(
        STATIC_DIR / 'js' / 'sw.js',
        'application/javascript',
        {'Service-Worker-Allowed': '/', 'Cache-Control': 'no-cache'},
    )


def favicon_ico(request):
    """Serve favicon.ico from root so browsers find it automatically."""
    return _serve_file(ICONS_DIR / 'favicon.ico', 'image/x-icon')


def apple_touch_icon(request):
    """Serve apple-touch-icon.png from root for iOS home screen."""
    return _serve_file(ICONS_DIR / 'apple-touch-icon.png', 'image/png')


def web_manifest(request):
    """Serve webmanifest from root with correct content type."""
    return _serve_file(
        STATIC_DIR / 'site.webmanifest',
        'application/manifest+json',
    )


def offline_page(request):
    """Minimal offline fallback page."""
    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CYOA - Offline</title>
    <style>
        body { font-family: system-ui, sans-serif; display: flex; align-items: center;
               justify-content: center; min-height: 100vh; margin: 0; background: #f9fafb; color: #374151; }
        .card { text-align: center; padding: 2rem; }
        h1 { font-size: 1.5rem; margin-bottom: 0.5rem; }
        p { color: #6b7280; }
        button { margin-top: 1rem; padding: 0.5rem 1.5rem; background: #4f46e5; color: white;
                 border: none; border-radius: 0.5rem; font-size: 1rem; cursor: pointer; }
    </style>
</head>
<body>
    <div class="card">
        <h1>You're offline</h1>
        <p>Check your connection and try again.</p>
        <button onclick="location.reload()">Retry</button>
    </div>
</body>
</html>"""
    return HttpResponse(html, content_type='text/html')

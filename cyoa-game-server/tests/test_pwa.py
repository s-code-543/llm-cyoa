"""Keep the app shell wired to the installable app and offline fallback."""
import json
from pathlib import Path

from django.conf import settings
from django.test import override_settings
from django.template.loader import render_to_string
import pytest


@override_settings(FRONTEND_DEV=False)
def test_shell_advertises_pwa():
    html = render_to_string('app/shell.html', {'frontend_dev': False})
    assert 'rel="manifest" href="/site.webmanifest" crossorigin="use-credentials"' in html
    assert 'rel="apple-touch-icon"' in html
    assert "register('/sw.js', { scope: '/'" in html


@override_settings(FRONTEND_DEV=True)
def test_dev_shell_does_not_register_worker(client):
    assert "navigator.serviceWorker.register" not in client.get('/').content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize('path,content_type', [
    ('/sw.js', 'application/javascript'),
    ('/site.webmanifest', 'application/manifest+json'),
    ('/offline.html', 'text/html'),
    ('/favicon.ico', 'image/x-icon'),
    ('/apple-touch-icon.png', 'image/png'),
])
def test_pwa_endpoints(client, path, content_type):
    response = client.get(path)
    assert response.status_code == 200
    assert response['Content-Type'].startswith(content_type)
    if path == '/sw.js':
        assert response['Service-Worker-Allowed'] == '/'
        assert response['Cache-Control'] == 'no-cache'
    response.close()


def test_manifest_icons_exist():
    static = Path(settings.BASE_DIR) / 'static'
    manifest = json.loads((static / 'site.webmanifest').read_text())
    assert manifest['scope'] == manifest['start_url'] == '/'
    assert manifest['display'] == 'standalone'
    assert manifest['theme_color'] == '#172c33'
    for icon in manifest['icons']:
        assert (static / icon['src'].removeprefix('/static/')).is_file()
        if icon['purpose'] == 'maskable':
            assert 'maskable-' in icon['src']

"""Tests for the React admin JSON API (dashboard, audit log, prompts)."""
import json

import pytest

from game.models import AuditLog, Prompt

pytestmark = pytest.mark.django_db


def put(client, url, data):
    return client.put(url, json.dumps(data), content_type='application/json')


def post(client, url, data):
    return client.post(url, json.dumps(data), content_type='application/json')


class TestPermissions:
    def test_signed_out_is_401(self, client):
        assert client.get('/api/v1/admin/dashboard').status_code == 401

    def test_player_is_403(self, auth_client):
        for url in ('/api/v1/admin/dashboard', '/api/v1/admin/audit', '/api/v1/admin/prompts'):
            assert auth_client.get(url).status_code == 403
        assert auth_client.delete('/api/v1/admin/audit').status_code == 403


class TestDashboardAndAudit:
    def test_dashboard_counts(self, admin_client):
        AuditLog.objects.create(original_text='a', refined_text='b', was_modified=True)
        AuditLog.objects.create(original_text='c', refined_text='c', was_refusal=True)
        data = admin_client.get('/api/v1/admin/dashboard').json()
        assert data['total_requests'] == 2
        assert data['total_corrections'] == 1
        assert data['total_refusals'] == 1
        assert data['correction_rate'] == 50.0
        assert len(data['recent']) == 2

    def test_audit_filter_detail_and_clear(self, admin_client):
        log = AuditLog.objects.create(original_text='a', refined_text='b', was_modified=True)
        AuditLog.objects.create(original_text='c', refined_text='c')
        assert len(admin_client.get('/api/v1/admin/audit').json()['logs']) == 2
        only = admin_client.get('/api/v1/admin/audit?modified_only=true').json()['logs']
        assert [row['id'] for row in only] == [log.id]
        assert admin_client.get(f'/api/v1/admin/audit/{log.id}').json()['refined_text'] == 'b'
        assert admin_client.get('/api/v1/admin/audit/999999').status_code == 404
        assert admin_client.delete('/api/v1/admin/audit').json() == {'deleted': 2}
        assert AuditLog.objects.count() == 0


class TestPrompts:
    def test_create_list_and_version(self, admin_client):
        created = post(admin_client, '/api/v1/admin/prompts', {
            'type': 'classifier', 'name': 'probe', 'prompt_text': 'a\r\nb'})
        assert created.status_code == 201
        prompt = created.json()
        assert prompt['version'] == 1 and prompt['prompt_text'] == 'a\nb'
        newer = post(admin_client, f"/api/v1/admin/prompts/{prompt['id']}/versions",
                     {'prompt_text': 'c', 'description': 'v2'}).json()
        assert newer['version'] == 2
        assert [v['version'] for v in newer['versions']] == [2, 1]
        listing = admin_client.get('/api/v1/admin/prompts').json()
        assert len([p for p in listing['prompts'] if p['name'] == 'probe']) == 2
        assert {'character', 'image-meta'} <= {t['value'] for t in listing['types']}

    def test_update_normalizes_line_endings(self, admin_client):
        prompt = Prompt.objects.create(prompt_type='judge', name='j', version=1, prompt_text='x')
        data = put(admin_client, f'/api/v1/admin/prompts/{prompt.id}',
                   {'description': 'd', 'prompt_text': 'one\r\ntwo'}).json()
        assert data['prompt_text'] == 'one\ntwo' and data['description'] == 'd'

    def test_validation(self, admin_client):
        assert post(admin_client, '/api/v1/admin/prompts', {'type': 'nope', 'name': 'x'}).status_code == 400
        assert post(admin_client, '/api/v1/admin/prompts', {'type': 'judge', 'name': ' '}).status_code == 400
        assert admin_client.get('/api/v1/admin/prompts/999999').status_code == 404
        assert admin_client.post('/api/v1/admin/prompts', 'nonsense',
                                 content_type='application/json').status_code == 400


class TestLegacyUrls:
    @pytest.mark.parametrize('old,new', [
        ('/admin/dashboard/', '/manage'),
        ('/admin/configurations/5/', '/manage/configurations'),
        ('/admin/tts-settings/', '/manage/voice'),
        ('/admin/', '/manage'),
    ])
    def test_old_admin_pages_redirect(self, client, old, new):
        resp = client.get(old)
        assert resp.status_code == 301 and resp['Location'] == new

    def test_django_admin_kept_for_users_and_groups(self, admin_client, client):
        assert admin_client.get('/django-admin/').status_code == 200
        assert client.get('/django-admin/').status_code == 302


@pytest.mark.parametrize('name', ['../escape', '/tmp/escape', '..\\escape', '.', '..', 'bad\x00name'])
def test_prompt_names_cannot_escape_directory(admin_client, name):
    from game.admin_api import save_prompt_to_disk
    from unittest.mock import patch

    assert post(admin_client, '/api/v1/admin/prompts', {
        'type': 'judge', 'name': name, 'prompt_text': 'unsafe',
    }).status_code == 400
    # Existing database rows must also be rejected before any write occurs.
    prompt = Prompt(name=name, version=1, prompt_type='judge', prompt_text='unsafe')
    with patch('builtins.open') as opened:
        with pytest.raises(ValueError):
            save_prompt_to_disk(prompt)
        opened.assert_not_called()


def test_provider_connection_fixture_targets(mock_ollama_connection, mock_anthropic_connection,
                                            mock_anthropic_models, mock_openai_connection,
                                            mock_openai_models, mock_openrouter_connection,
                                            mock_openrouter_models):
    from game import admin_providers_api

    assert admin_providers_api.test_ollama_connection is mock_ollama_connection
    assert admin_providers_api.test_anthropic_connection is mock_anthropic_connection
    assert admin_providers_api.get_anthropic_models is mock_anthropic_models
    assert admin_providers_api.test_openai_connection is mock_openai_connection
    assert admin_providers_api.get_openai_models is mock_openai_models
    assert admin_providers_api.test_openrouter_connection is mock_openrouter_connection
    assert admin_providers_api.get_openrouter_models is mock_openrouter_models


def test_prompt_save_stays_under_root_and_rejects_symlinks(tmp_path):
    from unittest.mock import patch
    from game.admin_api import save_prompt_to_disk

    prompt = Prompt.objects.create(name='safe prompt', version=1, prompt_type='judge', prompt_text='saved')
    root = tmp_path / 'cyoa_prompts'
    with patch('game.admin_api.__file__', str(tmp_path / 'server/game/admin_api.py')), \
            patch('os.path.exists', return_value=False):
        save_prompt_to_disk(prompt)
        target = root / 'judge_prompts/safe prompt_v1.txt'
        assert target.read_text() == 'saved'
        prompt.refresh_from_db()
        assert prompt.file_path == 'judge_prompts/safe prompt_v1.txt'
        outside = tmp_path / 'outside.txt'
        outside.write_text('unchanged')
        target.unlink()
        target.symlink_to(outside)
        with pytest.raises(ValueError):
            save_prompt_to_disk(prompt)
        assert outside.read_text() == 'unchanged'

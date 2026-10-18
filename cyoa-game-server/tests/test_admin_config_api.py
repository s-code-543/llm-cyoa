"""Tests for the admin JSON API: providers, models, difficulty, voice, configurations."""
import json
from unittest.mock import patch

import pytest

from game.models import APIProvider, Configuration, DifficultyProfile, JudgeStep, LLMModel, TTSSettings

pytestmark = pytest.mark.django_db

PROV = 'game.admin_providers_api'


def send(method, client, url, data=None):
    return getattr(client, method)(url, json.dumps(data or {}), content_type='application/json')


ENDPOINTS = [
    '/api/v1/admin/providers', '/api/v1/admin/models', '/api/v1/admin/difficulty',
    '/api/v1/admin/tts', '/api/v1/admin/configurations', '/api/v1/admin/configurations/options',
]


class TestPermissions:
    @pytest.mark.parametrize('url', ENDPOINTS)
    def test_anonymous_and_player_blocked(self, client, auth_client, url):
        assert client.get(url).status_code == 401
        assert auth_client.get(url).status_code == 403

    @pytest.mark.parametrize('url', ENDPOINTS)
    def test_admin_allowed(self, admin_client, url):
        assert admin_client.get(url).status_code == 200


class TestProviders:
    def test_api_key_is_never_returned(self, admin_client):
        resp = send('post', admin_client, '/api/v1/admin/providers', {
            'name': 'OR', 'provider_type': 'openrouter', 'api_key': 'sk-or-secret-1234567890'})
        assert resp.status_code == 201
        assert 'secret' not in resp.content.decode()
        assert resp.json()['has_api_key'] is True
        assert resp.json()['api_key_hint'] == '7890'
        assert 'secret' not in admin_client.get('/api/v1/admin/providers').content.decode()

    def test_blank_key_keeps_stored_and_clear_removes(self, admin_client):
        p = APIProvider.objects.create(name='A', provider_type='openai', api_key='sk-keepkeepkeep')
        send('put', admin_client, f'/api/v1/admin/providers/{p.id}', {'name': 'B', 'api_key': ''})
        p.refresh_from_db()
        assert (p.name, p.api_key) == ('B', 'sk-keepkeepkeep')
        send('put', admin_client, f'/api/v1/admin/providers/{p.id}', {'clear_api_key': True})
        p.refresh_from_db()
        assert p.api_key == ''

    def test_validation(self, admin_client):
        APIProvider.objects.create(name='Dup', provider_type='ollama')
        resp = send('post', admin_client, '/api/v1/admin/providers', {'name': 'Dup', 'provider_type': 'nope'})
        assert resp.status_code == 400
        assert set(resp.json()['error']['fields']) == {'name', 'provider_type'}

    def test_connection_uses_stored_key_and_records(self, admin_client):
        p = APIProvider.objects.create(name='A', provider_type='openrouter', api_key='stored-key-123')
        with patch(f'{PROV}.test_openrouter_connection', return_value={'success': True, 'message': 'ok'}) as t:
            resp = send('post', admin_client, '/api/v1/admin/providers/test', {
                'provider_id': p.id, 'provider_type': 'openrouter', 'api_key': ''})
        t.assert_called_once_with('stored-key-123')
        assert resp.json() == {'success': True, 'message': 'ok'}
        p.refresh_from_db()
        assert p.test_status == 'ok' and p.last_tested

    def test_browse_import_remove_sync(self, admin_client):
        p = APIProvider.objects.create(name='OR', provider_type='openrouter', api_key='k')
        remote = [{'id': 'a/one', 'name': 'One', 'description': 'd', 'size': 1},
                  {'id': 'a/two', 'name': 'Two'}]
        with patch(f'{PROV}.get_openrouter_models', return_value=remote):
            browse = admin_client.get(f'/api/v1/admin/providers/{p.id}/models').json()
            assert [m['imported'] for m in browse['models']] == [False, False]
            resp = send('post', admin_client, f'/api/v1/admin/providers/{p.id}/models/import',
                        {'model_ids': ['a/one']})
            assert resp.json()['imported'] == 1
            assert LLMModel.objects.get().name == 'OR: One'
            LLMModel.objects.create(name='stale', model_identifier='gone', provider=p)
            sync = send('post', admin_client, f'/api/v1/admin/providers/{p.id}/models/sync')
            assert sync.json()['removed'] == 1
            removed = send('post', admin_client, f'/api/v1/admin/providers/{p.id}/models/remove',
                           {'model_ids': ['a/one']})
            assert removed.json()['removed'] == 1
            assert send('post', admin_client, f'/api/v1/admin/providers/{p.id}/models/import',
                        {'model_ids': []}).status_code == 400

    def test_sync_fails_when_provider_unreachable(self, admin_client):
        p = APIProvider.objects.create(name='OR', provider_type='openrouter')
        with patch(f'{PROV}.get_openrouter_models', return_value=[]):
            assert send('post', admin_client, f'/api/v1/admin/providers/{p.id}/models/sync').status_code == 502


class TestModelsAndConfigs:
    def payload(self, **over):
        base = {
            'name': 'Cfg', 'adventure_prompt': self.adv.id, 'game_ending_prompt': self.end.id,
            'storyteller_model': self.model.id, 'enable_refusal_detection': False,
        }
        base.update(over)
        return base

    @pytest.fixture(autouse=True)
    def setup(self, adventure_prompt, game_ending_prompt, classifier_prompt, turn_correction_prompt,
              judge_prompt, llm_model):
        self.adv, self.end, self.cls = adventure_prompt, game_ending_prompt, classifier_prompt
        self.corr, self.judge, self.model = turn_correction_prompt, judge_prompt, llm_model

    def test_model_list_and_protected_delete_names_configs(self, admin_client):
        send('post', admin_client, '/api/v1/admin/configurations', self.payload(name='Uses It'))
        assert admin_client.get('/api/v1/admin/models').json()['models'][0]['id'] == self.model.id
        resp = admin_client.delete(f'/api/v1/admin/models/{self.model.id}')
        assert resp.status_code == 409
        assert 'Uses It' in resp.json()['error']['message']

    def test_create_minimal_and_clears_refusal_fields(self, admin_client):
        resp = send('post', admin_client, '/api/v1/admin/configurations',
                    self.payload(classifier_prompt=self.cls.id))
        assert resp.status_code == 201
        assert resp.json()['classifier_prompt'] is None
        assert Configuration.objects.count() == 1

    def test_refusal_requires_extras_with_field_errors(self, admin_client):
        resp = send('post', admin_client, '/api/v1/admin/configurations',
                    self.payload(enable_refusal_detection=True))
        assert resp.status_code == 400
        assert {'turn_correction_prompt', 'turn_correction_model',
                'classifier_prompt', 'classifier_model'} <= set(resp.json()['error']['fields'])

    def test_required_and_wrong_prompt_type(self, admin_client):
        resp = send('post', admin_client, '/api/v1/admin/configurations', {
            'name': '', 'adventure_prompt': self.end.id})
        fields = resp.json()['error']['fields']
        assert {'name', 'adventure_prompt', 'game_ending_prompt', 'storyteller_model'} <= set(fields)

    def test_bad_workflow_rejected(self, admin_client):
        resp = send('post', admin_client, '/api/v1/admin/configurations',
                    self.payload(workflow={'version': 2, 'nodes': []}))
        assert 'workflow' in resp.json()['error']['fields']

    def test_judge_steps_create_update_delete(self, admin_client):
        step = {'name': 'Judge', 'rewrite_prompt': self.judge.id, 'rewrite_model': self.model.id,
                'compare_prompt': self.judge.id, 'compare_model': self.model.id}
        created = send('post', admin_client, '/api/v1/admin/configurations',
                       self.payload(judge_steps=[step, {**step, 'name': 'Second'}])).json()
        first, second = created['judge_steps']
        url = f"/api/v1/admin/configurations/{created['id']}"
        updated = send('put', admin_client, url, self.payload(
            judge_steps=[{**step, 'id': first['id'], 'name': 'Renamed'}])).json()
        assert [s['name'] for s in updated['judge_steps']] == ['Renamed']
        assert not JudgeStep.objects.filter(pk=second['id']).exists()

    def test_judge_step_requires_rewrite_and_compare(self, admin_client):
        resp = send('post', admin_client, '/api/v1/admin/configurations',
                    self.payload(judge_steps=[{'name': 'x'}]))
        assert 'judge_steps.0.rewrite_prompt' in resp.json()['error']['fields']

    def test_workflow_roundtrip_and_delete(self, admin_client):
        wf = {'version': 1, 'nodes': [{'type': 'ApplyDifficulty'}, {'type': 'GenerateTurn'}, {'type': 'ValidateTurn'}, {'type': 'SaveGame'}]}
        created = send('post', admin_client, '/api/v1/admin/configurations', self.payload(workflow=wf))
        assert created.status_code == 201, created.content
        cid = created.json()['id']
        assert admin_client.get(f'/api/v1/admin/configurations/{cid}').json()['workflow'] == wf
        assert admin_client.delete(f'/api/v1/admin/configurations/{cid}').status_code == 200
        assert admin_client.get(f'/api/v1/admin/configurations/{cid}').status_code == 404

    def test_image_config_validation_and_roundtrip(self, admin_client):
        from tests.conftest import PromptFactory, APIProviderFactory, LLMModelFactory
        meta = PromptFactory(prompt_type='image-meta')
        character = PromptFactory(prompt_type='character')
        provider = APIProviderFactory(provider_type='openrouter', api_key='test')
        model = LLMModelFactory(provider=provider, capabilities={'image_generation': True})
        url = '/api/v1/admin/configurations'
        missing = send('post', admin_client, url, self.payload(enable_image_generation=True))
        assert {'image_model', 'image_meta_prompt'} <= set(missing.json()['error']['fields'])
        data = self.payload(enable_image_generation=True, image_model=model.pk,
                            image_meta_prompt=meta.pk, character_prompt=character.pk,
                            image_aspect_ratio='4:3', image_timeout=45)
        created = send('post', admin_client, url, data)
        assert created.status_code == 201, created.content
        assert created.json()['image_model'] == model.pk
        assert created.json()['character_prompt'] == character.pk
        cid = created.json()['id']
        loaded = admin_client.get(f'{url}/{cid}').json()
        assert loaded['image_aspect_ratio'] == '4:3' and loaded['image_timeout'] == 45
        options = admin_client.get(url + '/options').json()
        assert model.pk in [m['id'] for m in options['image_models']]
        assert model.pk not in [m['id'] for m in options['models']]
        bad = send('put', admin_client, f'{url}/{cid}', {**data, 'image_model': self.model.pk})
        assert 'image_model' in bad.json()['error']['fields']
        bad = send('put', admin_client, f'{url}/{cid}', {**data, 'character_prompt': self.adv.pk})
        assert 'character_prompt' in bad.json()['error']['fields']
        disabled = send('put', admin_client, f'{url}/{cid}', {**data, 'enable_image_generation': False})
        assert disabled.status_code == 200 and disabled.json()['image_model'] == model.pk
        assert admin_client.delete(f'/api/v1/admin/models/{model.pk}').status_code == 409

    def test_options(self, admin_client):
        data = admin_client.get('/api/v1/admin/configurations/options').json()
        assert data['adventure_prompts'][0]['id'] == self.adv.id
        assert data['models'][0]['id'] == self.model.id


class TestDifficultyAndTTS:
    def test_curve_generates_function(self, admin_client):
        resp = send('post', admin_client, '/api/v1/admin/difficulty', {
            'name': 'Curve', 'curve_points': [0.1, 0.2, 0.3, 0.4, 0.5]})
        assert resp.status_code == 201
        assert resp.json()['function']

    def test_function_mode_and_validation(self, admin_client):
        ok = send('post', admin_client, '/api/v1/admin/difficulty', {'name': 'F', 'function': '0.1 + x/n'})
        assert ok.status_code == 201 and ok.json()['curve_points'] is None
        bad = send('post', admin_client, '/api/v1/admin/difficulty', {'name': 'G', 'function': 'boom('})
        assert 'function' in bad.json()['error']['fields']
        evil = send('post', admin_client, '/api/v1/admin/difficulty', {'name': 'H', 'function': '__import__("os")'})
        assert evil.status_code == 400
        out = send('post', admin_client, '/api/v1/admin/difficulty', {'name': 'C', 'curve_points': [2, 0, 0, 0, 0]})
        assert 'curve_points' in out.json()['error']['fields']

    def test_update_delete_and_protected(self, admin_client, configuration):
        p = DifficultyProfile.objects.create(name='P', function='x/n')
        assert send('put', admin_client, f'/api/v1/admin/difficulty/{p.id}',
                    {'name': 'P2', 'function': 'x/n'}).json()['name'] == 'P2'
        configuration.difficulty = p
        configuration.save()
        assert admin_client.delete(f'/api/v1/admin/difficulty/{p.id}').status_code == 409
        configuration.difficulty = None
        configuration.save()
        assert admin_client.delete(f'/api/v1/admin/difficulty/{p.id}').status_code == 200

    def test_tts_roundtrip_and_validation(self, admin_client):
        resp = send('put', admin_client, '/api/v1/admin/tts', {
            'enabled': True, 'openai_voice': 'nova', 'max_text_length': 500, 'audio_retention_days': 3})
        assert resp.status_code == 200
        assert TTSSettings.get_settings().openai_voice == 'nova'
        bad = send('put', admin_client, '/api/v1/admin/tts', {'max_text_length': 99999, 'openai_voice': 'x'})
        assert set(bad.json()['error']['fields']) == {'max_text_length', 'openai_voice'}

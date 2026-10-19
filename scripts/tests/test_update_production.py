"""Deployment failure tests; Docker and HTTP are mocked, never the live app."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('updater', Path(__file__).parents[1] / 'update-production.py')
u = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(u)


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.overlay = self.root / 'compose.home-prod.yml'
        self.overlay.write_text('services:\n  cyoa-game-server:\n    image: previous\n')
        self.state = {'Id': 'old-container', 'Image': 'sha256:old', 'Config': {
            'Image': 'old-image', 'Labels': {'com.docker.compose.project': 'llm-cyoa'}}}
        p = patch.dict(u.os.environ)
        p.start()
        self.addCleanup(p.stop)
        self.calls = []
        self.failure = None
        self.current = {'Id': 'new-container', 'State': {'StartedAt': '0001-01-01T00:00:00Z'}}
        self.args = type('Args', (), {'force': False})()
        for name, value in [('ROOT', self.root), ('output', self.output), ('run', self.fake_run)]:
            p = patch.object(u, name, value)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(u.time, 'sleep')
        p.start()
        self.addCleanup(p.stop)
        p = patch.object(u.urllib.request, 'urlopen', self.response)
        p.start()
        self.addCleanup(p.stop)

    def output(self, *args):
        if args[:2] == ('git', 'rev-parse'):
            return ('a' if args[2] == 'HEAD' else 'b') * 40
        if 'config' in args:
            return json.dumps({'services': {'cyoa-game-server': {'image': 'previous',
                'environment': {'SECRET': 'sensitive'}, 'volumes': ['/actual/media:/app/media']}}})
        if args[:2] == ('docker', 'inspect'):
            if self.current is None:
                raise subprocess.CalledProcessError(1, args)
            return json.dumps([self.current])
        if args[:3] == ('docker', 'ps', '-aq'):
            return ''
        raise AssertionError(args)

    def fake_run(self, *args, **kwargs):
        self.calls.append(args)
        if self.failure == 'build' and args[:2] == ('docker', 'build'):
            raise subprocess.CalledProcessError(1, args)
        if self.failure == 'create' and 'create' in args:
            raise subprocess.CalledProcessError(1, args)
        if self.failure == 'start' and args[:2] == ('docker', 'start'):
            raise subprocess.CalledProcessError(1, args)
        if self.failure == 'backup' and args[:2] == ('docker', 'cp'):
            raise subprocess.CalledProcessError(1, args)
        if args[:2] == ('docker', 'cp'):
            destination = Path(args[3])
            destination.mkdir()
            if args[2].endswith('/db'):
                c = sqlite3.connect(destination / 'db.sqlite3')
                c.execute('create table preserved (id integer)')
                c.commit()
                c.close()
            else:
                (destination / 'user-upload.txt').write_text('actual-volume-data')
        return subprocess.CompletedProcess(args, 0)

    def response(self, *args, **kwargs):
        if self.failure == 'health':
            raise OSError('unhealthy')
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self): return b'<script src="/static/frontend/main.js"></script>'
        return Response()

    def rollback_calls(self):
        return [c for c in self.calls if any(str(x).endswith('rollback.json') for x in c)]

    def test_success_backs_up_container_media_without_host_media(self):
        u.update(self.args, self.state)
        backup = next((self.root / 'backups').iterdir())
        with tarfile.open(backup / 'media.tar.gz') as t:
            self.assertEqual(t.extractfile('media/user-upload.txt').read(), b'actual-volume-data')
        self.assertEqual((backup / 'rollback.json').stat().st_mode & 0o777, 0o600)
        self.assertIn('b' * 12, u.os.environ['CYOA_IMAGE'])
        self.assertIn('image: previous', self.overlay.read_text())
        self.assertIn(('docker', 'image', 'tag', 'llm-cyoa-cyoa-game-server:' + 'b' * 12,
                       'llm-cyoa-cyoa-game-server:home-production'), self.calls)
        self.assertFalse(self.rollback_calls())

    def test_build_failure_keeps_old_app_running(self):
        self.failure = 'build'
        with self.assertRaises(subprocess.CalledProcessError): u.update(self.args, self.state)
        self.assertNotIn(('docker', 'stop', 'cyoa-game-server'), self.calls)

    def test_backup_failure_restarts_original_container(self):
        self.failure = 'backup'
        with self.assertRaises(subprocess.CalledProcessError): u.update(self.args, self.state)
        self.assertIn(('docker', 'start', 'cyoa-game-server'), self.calls)
        self.assertFalse(self.rollback_calls())

    def test_create_failure_restores_previous_image(self):
        self.failure = 'create'
        with self.assertRaises(subprocess.CalledProcessError): u.update(self.args, self.state)
        self.assertEqual(len(self.rollback_calls()), 1)
        self.assertIn('image: previous', self.overlay.read_text())

    def test_start_failure_before_entrypoint_restores_previous_image(self):
        self.failure = 'start'
        with self.assertRaises(subprocess.CalledProcessError): u.update(self.args, self.state)
        self.assertEqual(len(self.rollback_calls()), 1)

    def test_missing_container_after_create_failure_restores_previous_image(self):
        self.current = None
        self.failure = 'create'
        with self.assertRaises(subprocess.CalledProcessError): u.update(self.args, self.state)
        self.assertEqual(len(self.rollback_calls()), 1)

    def test_health_failure_after_start_requires_manual_database_recovery(self):
        self.current['State']['StartedAt'] = '2026-10-18T01:00:00Z'
        self.failure = 'health'
        with patch.object(u.subprocess, 'run') as logs:
            with self.assertRaises(RuntimeError): u.update(self.args, self.state)
            logs.assert_called_once()
        self.assertFalse(self.rollback_calls())

    def test_unknown_docker_state_prevents_unsafe_rollback(self):
        with patch.object(u, 'output', side_effect=subprocess.CalledProcessError(1, 'docker')):
            self.assertTrue(u.migration_may_have_started('old-container'))


if __name__ == '__main__':
    unittest.main()

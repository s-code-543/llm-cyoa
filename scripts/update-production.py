#!/usr/bin/env python3
"""Update this Mac's existing CYOA deployment, preserving its tunnel and data."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ['docker', 'compose', '-f', 'docker-compose.mac.yml', '-f', 'compose.home-prod.yml']


def run(*args, capture=False, **kwargs):
    return subprocess.run(args, cwd=ROOT, check=True, text=True,
                          stdout=subprocess.PIPE if capture else None, **kwargs)


def output(*args):
    return run(*args, capture=True).stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Check local prerequisites without updating or restarting')
    parser.add_argument('--force', action='store_true', help='Rebuild even when main has no new commits')
    args = parser.parse_args()
    os.chdir(ROOT)
    if output('git', 'branch', '--show-current') != 'main':
        raise RuntimeError('Switch to main before updating.')
    # The known local packaging fix is allowed; other tracked edits need review.
    changes = output('git', 'diff', 'HEAD', '--name-only').splitlines()
    if set(changes) - {'.dockerignore'}:
        raise RuntimeError('Tracked files have local edits; commit or stash them first: ' + ', '.join(changes))
    if output('git', 'ls-files', '--others', '--exclude-standard', '--', 'cyoa-game-server', 'frontend', 'deploy', 'cyoa_prompts'):
        raise RuntimeError('Untracked application files exist; commit or move them before updating.')
    run(*COMPOSE, 'config', '--quiet')
    state = json.loads(output('docker', 'inspect', 'cyoa-game-server'))[0]
    if not state['State']['Running']:
        raise RuntimeError('The existing app must be running before starting an update.')
    if args.check:
        print('Prerequisites OK. No files, containers, or remote refs changed.')
        return
    # Prevent overlapping invocations without leaving a stale lock after a crash.
    import fcntl
    with (ROOT / '.git' / 'cyoa-update.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        update(args, state)


def update(args, state):
    run('git', 'fetch', 'origin', 'main')
    old = output('git', 'rev-parse', 'HEAD')
    new = output('git', 'rev-parse', 'origin/main')
    run('git', 'merge-base', '--is-ancestor', old, new)
    if old == new and not args.force:
        print('Already on the latest main. Nothing restarted. Use --force to rebuild.')
        return
    stamp = time.strftime('%Y%m%d-%H%M%S')
    image = 'llm-cyoa-cyoa-game-server:' + new[:12]
    print('Building ' + new[:12] + ' while the current app stays online.', flush=True)
    with tempfile.TemporaryDirectory(prefix='cyoa-release-') as temporary:
        archive = Path(temporary) / 'source.tar'
        source = Path(temporary) / 'source'
        source.mkdir()
        run('git', 'archive', '--format=tar', '-o', str(archive), new)
        # This archive comes from our trusted Git commit; use system tar for macOS Python compatibility.
        run('tar', '-xf', str(archive), '-C', str(source))
        ignore = source / '.dockerignore'
        with ignore.open('a') as f:
            f.write('\n!frontend/src/media/\n!frontend/src/media/**\n')
        run('docker', 'build', '-f', str(source / 'deploy/Dockerfile.prod'), '-t', image, str(source))
    backup = ROOT / 'backups' / stamp
    backup.mkdir(parents=True, mode=0o700)
    previous = state['Config']['Image']
    (backup / 'release.json').write_text(json.dumps({'previous_commit': old, 'target_commit': new,
        'previous_image': previous, 'previous_image_id': state['Image'], 'new_image': image}, indent=2))
    overlay = ROOT / 'compose.home-prod.yml'
    (backup / 'compose.home-prod.yml').write_bytes(overlay.read_bytes())
    run('docker', 'image', 'tag', state['Image'], 'llm-cyoa-cyoa-game-server:rollback-' + stamp)
    stopped = False
    deployment_attempted = False
    try:
        print('Stopping briefly to take a consistent backup and deploy.', flush=True)
        run('docker', 'stop', 'cyoa-game-server')
        stopped = True
        run('docker', 'cp', 'cyoa-game-server:/app/db', str(backup / 'db'))
        import sqlite3
        connection = sqlite3.connect(str(backup / 'db' / 'db.sqlite3'))
        try:
            if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Database backup failed its integrity check.')
        finally:
            connection.close()
        with tarfile.open(backup / 'media.tar.gz', 'w:gz') as tar:
            tar.add(ROOT / 'cyoa-game-server' / 'media', arcname='media')
        run('git', 'merge', '--ff-only', 'origin/main')
        text = overlay.read_text()
        text, count = re.subn(r'(?m)^    image: .+$', '    image: ' + image, text)
        if count != 1:
            raise RuntimeError('Expected exactly one image setting in the local overlay.')
        overlay.write_text(text)
        run(*COMPOSE, 'config', '--quiet')
        deployment_attempted = True
        run(*COMPOSE, 'up', '-d', '--no-build', '--no-deps', 'cyoa-game-server')
        for attempt in range(60):
            try:
                with urllib.request.urlopen('http://127.0.0.1:8001/', timeout=3) as response:
                    html = response.read().decode()
                assets = re.findall(r'(?:src|href)="(/static/[^\"]+)"', html)
                if not any('.js' in asset and '/frontend/' in asset for asset in assets):
                    raise RuntimeError('Frontend bundle missing from page.')
                for asset in assets:
                    with urllib.request.urlopen('http://127.0.0.1:8001' + asset, timeout=3) as response:
                        response.read()
                break
            except Exception:
                if attempt == 59:
                    raise RuntimeError('App did not become healthy within the startup window.')
                time.sleep(2)
        run('docker', 'exec', 'cyoa-game-server', 'python', 'manage.py', 'check')
        run('docker', 'exec', 'cyoa-game-server', 'python', 'manage.py', 'migrate', '--check')
        print(f'Updated to {new[:12]}. App and frontend assets respond successfully.\nBackup: {backup}\nOpen https://cyoa.chat-sdp.org/ to verify your signed-in session.')
    except BaseException:
        if stopped and not deployment_attempted:
            overlay.write_bytes((backup / 'compose.home-prod.yml').read_bytes())
            run('docker', 'start', 'cyoa-game-server')
            print('The previous container was restarted; deployment had not begun.')
        elif deployment_attempted:
            print('Deployment failed. Backup: ' + str(backup))
            print('No automatic rollback: migrations may have changed the database. Restore matching database and image together.')
            subprocess.run(COMPOSE + ['logs', '--tail=80', 'cyoa-game-server'], cwd=ROOT)
        raise


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        raise SystemExit('Update stopped: ' + str(error))

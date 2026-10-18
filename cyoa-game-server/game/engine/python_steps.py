"""Run data-only scripts outside the Django process, with bounded resources."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from .python_worker import validate_script


def run_python(code, state, turn_input, seed):
    validate_script(code)
    payload = json.dumps({'code': code, 'state': state, 'input': turn_input, 'seed': seed}, allow_nan=False)
    if len(payload.encode()) > 1024 * 1024:
        raise ValueError('Python step input exceeds 1 MB')
    with tempfile.TemporaryDirectory(prefix='cyoa-step-') as directory:
        result = subprocess.run(
            [sys.executable, '-I', '-S', str(Path(__file__).with_name('python_worker.py'))],
            input=payload, text=True, capture_output=True, timeout=3,
            cwd=directory, env={'LANG': 'C.UTF-8'},
        )
    if result.returncode:
        raise ValueError('RunPython failed: ' + result.stderr[-500:])
    return json.loads(result.stdout)

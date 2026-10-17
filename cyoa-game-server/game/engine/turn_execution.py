"""Start here to see how a turn runs. Node mechanics live in nodes.py.

An empty configuration uses DEFAULT_WORKFLOW. Adventures can insert data
transformations and prompt operations, omit the judge, and condition steps on
state. SaveGame is always last; it commits visible and hidden state together.
"""
from copy import deepcopy
import time
import json

from . import nodes

DEFAULT_WORKFLOW = {
    'version': 1,
    'nodes': [
        {'type': 'ApplyDifficulty'},
        {'type': 'ConcatenatePrompt', 'include_state': False},
        {'type': 'GenerateTurn'},
        {'type': 'ReWriteRefusal'},
        {'type': 'ReWriteJudge'},
        {'type': 'ValidateTurn'},
        {'type': 'SaveGame'},
    ],
}

NODE_HANDLERS = {
    'RunPython': nodes.run_python_step,
    'GateInventory': nodes.gate_inventory,
    'ApplyDifficulty': nodes.apply_difficulty,
    'ApplyRandomPrompt': nodes.apply_random_prompt,
    'ConcatenatePrompt': nodes.concatenate_prompt,
    'GenerateTurn': nodes.generate_turn,
    'ReWriteRefusal': nodes.rewrite_refusal,
    'ReWriteJudge': nodes.rewrite_judge,
    'ExtractJSON': nodes.extract_json,
    'ApplyStateChanges': nodes.apply_state_changes,
    'ValidateTurn': nodes.validate_turn,
    'SaveGame': nodes.save_game,
}


def execute_turn(conversation, action, *, call_llm, correct_refusal, judge_turn):
    """Load → validate workflow → execute named nodes → commit exactly once."""
    turn = nodes.load_turn(conversation, action, call_llm, correct_refusal, judge_turn)
    workflow = deepcopy(turn.session.workflow_snapshot or turn.config.workflow or DEFAULT_WORKFLOW)
    validate_workflow(workflow)
    turn.session.workflow_snapshot = workflow

    def snapshot():
        return json.loads(json.dumps({'action': turn.action, 'state': turn.state,
                         'proposed_state': turn.proposed_state, 'narrative': turn.candidate,
                         'context': turn.context, 'messages': turn.messages,
                         'random_results': turn.random_results, 'blocked': turn.blocked,
                         'refusal': turn.refusal, 'judge': turn.judge}))

    for index, step in enumerate(workflow['nodes']):
        started = time.monotonic()
        entry = {'index': index, 'type': step['type'], 'configuration': deepcopy(step),
                 'status': 'running', 'input': snapshot(), 'model_requests': []}
        turn.debug_steps.append(entry)
        call_start = len(turn.model_requests)
        try:
            if started >= turn.deadline:
                raise TimeoutError('Turn execution deadline exceeded')
            if not nodes.condition_matches(turn, step.get('when')):
                entry.update(status='skipped', reason='Condition did not match')
                turn.trace.append({'index': index, 'type': step['type'], 'status': 'skipped'})
                continue
            # SaveGame persists this entry inside its atomic commit.
            if step['type'] == 'SaveGame':
                entry.update(status='completed', output=snapshot())
            NODE_HANDLERS[step['type']](turn, step)
            entry['status'] = 'blocked' if turn.blocked else 'completed'
        except Exception as error:
            entry.update(status='failed', error=str(error), output=snapshot(),
                         model_requests=deepcopy(turn.model_requests[call_start:]),
                         elapsed_ms=round((time.monotonic() - started) * 1000))
            turn.trace.append({'index': index, 'type': step['type'], 'status': 'failed'})
            nodes.record_failure(turn, step, error)
            raise
        finally:
            entry.update(output=snapshot(), model_requests=deepcopy(turn.model_requests[call_start:]),
                         elapsed_ms=round((time.monotonic() - started) * 1000))
        turn.trace.append({'index': index, 'type': step['type'], 'status': 'completed',
                           'elapsed_ms': entry['elapsed_ms']})
        if turn.blocked:
            return nodes.save_blocked_turn(turn)

    # SaveGame's duration is only known after its commit.
    message = conversation.messages.get(pk=turn.result['message']['id'])
    message.metadata['pipeline_debug'] = turn.debug_steps
    message.save(update_fields=['metadata'])

    return turn.result


def validate_workflow(workflow):
    """Reject unknown nodes and unsafe orderings before any model or script runs."""
    if not isinstance(workflow, dict) or workflow.get('version') != 1:
        raise ValueError('Workflow must be an object with version 1')
    steps = workflow.get('nodes')
    if not isinstance(steps, list) or not 3 <= len(steps) <= 32:
        raise ValueError('Workflow requires 3–32 nodes')
    types = []
    for step in steps:
        if not isinstance(step, dict) or step.get('type') not in NODE_HANDLERS:
            raise ValueError('Unknown workflow node')
        types.append(step['type'])
        condition = step.get('when')
        if condition is not None and (not isinstance(condition, dict) or not isinstance(condition.get('key'), str)):
            raise ValueError('Condition requires a state key and an optional equals value')
        if step['type'] in {'GenerateTurn', 'ValidateTurn', 'SaveGame'} and condition is not None:
            raise ValueError('Generation, validation, and saving cannot be conditional')
        if step['type'] == 'GateInventory':
            from .inventory import check_settings
            check_settings(step)
        if step['type'] == 'RunPython':
            from .python_worker import validate_script
            validate_script(step.get('code'))
        if step['type'] == 'ApplyRandomPrompt':
            probability = step.get('probability', 0)
            if not isinstance(probability, (float, int)) or not 0 <= probability <= 1:
                raise ValueError('Probability must be between zero and one')
        if step['type'] == 'ConcatenatePrompt' and step.get('target', 'system') not in {'system', 'user'}:
            raise ValueError('Prompt target must be system or user')
        if step['type'] == 'ExtractJSON' and step.get('mode', 'merge') not in {'merge', 'deterministic'}:
            raise ValueError('JSON mode must be merge or deterministic')
        if step['type'] == 'ApplyStateChanges':
            allowed = step.get('allowed_keys', [])
            if not isinstance(allowed, list) or not all(isinstance(key, str) for key in allowed):
                raise ValueError('allowed_keys must be a list of state field names')
    for singleton in ('ExtractJSON', 'ApplyStateChanges', 'ApplyDifficulty', 'GateInventory'):
        if types.count(singleton) > 1:
            raise ValueError(f'{singleton} may appear at most once')
    if types.count('GenerateTurn') != 1 or types.count('SaveGame') != 1 or types[-1] != 'SaveGame':
        raise ValueError('Workflow requires one GenerateTurn and one final SaveGame')
    if types.count('ValidateTurn') != 1 or types[-2] != 'ValidateTurn':
        raise ValueError('ValidateTurn must immediately precede SaveGame')
    generation = types.index('GenerateTurn')
    for index, kind in enumerate(types):
        if kind in {'ReWriteRefusal', 'ReWriteJudge', 'ExtractJSON', 'ApplyStateChanges'} and index <= generation:
            raise ValueError(f'{kind} must follow GenerateTurn')
        if kind in {'GateInventory', 'ApplyDifficulty', 'ApplyRandomPrompt', 'ConcatenatePrompt'} and index >= generation:
            raise ValueError(f'{kind} must precede GenerateTurn')
    if 'ExtractJSON' in types:
        extraction = types.index('ExtractJSON')
        if any(kind in {'ReWriteRefusal', 'ReWriteJudge'} for kind in types[extraction + 1:]):
            raise ValueError('ExtractJSON must follow all rewrites')
        if 'ApplyStateChanges' not in types or types.index('ApplyStateChanges') <= extraction:
            raise ValueError('ExtractJSON requires a subsequent ApplyStateChanges')
    elif 'ApplyStateChanges' in types:
        raise ValueError('ApplyStateChanges requires ExtractJSON')

    if 'GateInventory' in types:
        merge = next((step for step in steps if step['type'] == 'ApplyStateChanges'), None)
        if not merge or 'inventory' not in merge.get('allowed_keys', []):
            raise ValueError('GateInventory requires ExtractJSON and inventory state merging')
        if 'inventory_policy' in merge.get('allowed_keys', []):
            raise ValueError('inventory_policy is engine-owned')

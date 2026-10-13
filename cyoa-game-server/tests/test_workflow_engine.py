"""Workflow contracts: hidden state, script limits, routing, and atomic recovery."""
import json
from unittest.mock import Mock

import pytest

from game.engine.turn_execution import execute_turn, validate_workflow
from game.engine.python_steps import run_python
from game.engine.nodes import TurnUnavailable
from game.models import GameSession
from game.refusal_detector import process_potential_refusal
from game.judge_pipeline import run_judge_pipeline
from tests.conftest import ChatConversationFactory

STORY = 'Turn 1 of 10\nA storm approaches.\n1) Enter\n2) Wait'


def workflow(*steps):
    return {'version': 1, 'nodes': list(steps) + [{'type': 'ValidateTurn'}, {'type': 'SaveGame'}]}


@pytest.fixture
def adventure(user, configuration):
    configuration.enable_refusal_detection = False
    configuration.save()
    return ChatConversationFactory(user=user, metadata={'config_id': configuration.pk})


def execute(adventure, llm):
    return execute_turn(adventure, 'Go', call_llm=llm,
                        correct_refusal=process_potential_refusal, judge_turn=run_judge_pipeline)


def configure(adventure, spec):
    from game.models import Configuration
    Configuration.objects.filter(pk=adventure.metadata['config_id']).update(workflow=spec)


def test_python_transforms_json_and_seeded_randomness():
    code = "state['items'] = [x * 2 for x in range(3)]\nstate['roll'] = randint(1, 100)\nstate['action'] = input['action']"
    first = run_python(code, {}, {'action': 'Go'}, 42)
    assert first == run_python(code, {}, {'action': 'Go'}, 42)
    assert first['items'] == [0, 2, 4]
    assert first['action'] == 'Go'


@pytest.mark.parametrize('source', [
    'import requests', 'import ast', "open('/etc/passwd')", 'state.__class__',
    'eval("1")', '__import__("os")', "getattr(state, '__class__')", 'def run():\n    pass',
])
def test_python_rejects_capabilities(source):
    with pytest.raises(ValueError):
        run_python(source, {}, {}, 1)


def test_python_infinite_loop_is_stopped():
    with pytest.raises((ValueError, TimeoutError)):
        run_python('while True:\n    pass', {}, {}, 1)


@pytest.mark.parametrize('types', [
    ['GenerateTurn', 'SaveGame'],
    ['GenerateTurn', 'ValidateTurn', 'SaveGame', 'RunPython'],
    ['GenerateTurn', 'GenerateTurn', 'ValidateTurn', 'SaveGame'],
    ['GenerateTurn', 'ExtractJSON', 'ReWriteJudge', 'ApplyStateChanges', 'ValidateTurn', 'SaveGame'],
    ['Unknown', 'ValidateTurn', 'SaveGame'],
])
def test_invalid_order_is_rejected(types):
    with pytest.raises(ValueError):
        validate_workflow({'version': 1, 'nodes': [{'type': kind} for kind in types]})


@pytest.mark.django_db
def test_custom_state_persists_and_is_hidden_in_both_apis(adventure, auth_client):
    configure(adventure, workflow(
        {'type': 'RunPython', 'code': "state['secret'] = 'heat_seeking'"},
        {'type': 'ConcatenatePrompt'}, {'type': 'GenerateTurn'},
        {'type': 'ExtractJSON'}, {'type': 'ApplyStateChanges', 'allowed_keys': ['inventory']},
    ))
    llm = Mock(return_value=STORY + '\n```game-state\n{"inventory": ["torch"]}\n```')
    result = execute(adventure, llm)
    session = GameSession.objects.get(session_id=adventure.conversation_id)
    assert session.hidden_state == {'secret': 'heat_seeking', 'inventory': ['torch']}
    assert 'heat_seeking' in llm.call_args.kwargs['system_prompt']
    assert 'game-state' not in result['message']['content']
    assert 'secret' not in json.dumps(result)
    assert result['state']['inventory'] == ['torch']
    for path in [f'/chat/api/conversation/{adventure.conversation_id}',
                 f'/api/v1/chat/conversations/{adventure.conversation_id}']:
        response = auth_client.get(path)
        assert response.status_code == 200
        assert 'heat_seeking' not in response.content.decode()
        assert 'engine_snapshot' not in response.content.decode()
        if '/api/v1/' in path:
            assert response.json()['conversation']['state']['inventory'] == ['torch']


@pytest.mark.django_db
@pytest.mark.parametrize('block', ['{"secret":"changed"}', '{bad json}', '[]'])
def test_invalid_proposal_commits_nothing(adventure, block):
    configure(adventure, workflow(
        {'type': 'RunPython', 'code': "state['secret'] = 'fixed'"},
        {'type': 'GenerateTurn'}, {'type': 'ExtractJSON'},
        {'type': 'ApplyStateChanges', 'allowed_keys': ['inventory']},
    ))
    with pytest.raises(ValueError):
        execute(adventure, Mock(return_value=STORY + f'\n```game-state\n{block}\n```'))
    assert not adventure.messages.exists()
    assert not GameSession.objects.filter(session_id=adventure.conversation_id).exists()


@pytest.mark.django_db
def test_deterministic_state_can_discard_narrator_proposal(adventure):
    configure(adventure, workflow(
        {'type': 'RunPython', 'code': "state['secret'] = 'fixed'"},
        {'type': 'GenerateTurn'}, {'type': 'ExtractJSON', 'mode': 'deterministic'},
        {'type': 'ApplyStateChanges'},
    ))
    execute(adventure, Mock(return_value=STORY + '\n```game-state\n{"secret":"changed"}\n```'))
    assert GameSession.objects.get(session_id=adventure.conversation_id).hidden_state == {'secret': 'fixed'}


@pytest.mark.django_db
def test_conditions_and_forced_random_ending(adventure):
    configure(adventure, workflow(
        {'type': 'RunPython', 'code': "state['risk'] = 1\nstate['enabled'] = False"},
        {'type': 'RunPython', 'code': "state['wrong'] = True", 'when': {'key': 'enabled'}},
        {'type': 'ApplyRandomPrompt', 'probability_key': 'risk', 'ending': True, 'prompt': 'Fall through the ice.'},
        {'type': 'GenerateTurn'},
    ))
    llm = Mock(return_value='The ice breaks.\nGAME OVER')
    execute(adventure, llm)
    session = GameSession.objects.get(session_id=adventure.conversation_id)
    assert session.game_over
    assert 'wrong' not in session.hidden_state
    assert 'Fall through the ice.' in llm.call_args.kwargs['system_prompt']
    with pytest.raises(TurnUnavailable):
        execute(adventure, llm)


@pytest.mark.django_db
def test_required_ending_cannot_be_ignored(adventure):
    configure(adventure, workflow(
        {'type': 'ApplyRandomPrompt', 'probability': 1, 'ending': True}, {'type': 'GenerateTurn'},
    ))
    with pytest.raises(ValueError, match='Required ending'):
        execute(adventure, Mock(return_value=STORY))
    assert not adventure.messages.exists()


@pytest.mark.django_db
def test_workflow_pinning_and_rollback_restore_state(adventure, auth_client):
    spec = workflow({'type': 'RunPython', 'code': "state['visits'] = state.get('visits', 0) + 1"},
                    {'type': 'GenerateTurn'})
    configure(adventure, spec)
    first = execute(adventure, Mock(return_value=STORY))
    configure(adventure, workflow({'type': 'RunPython', 'code': "state['visits'] = 99"}, {'type': 'GenerateTurn'}))
    execute(adventure, Mock(return_value=STORY.replace('Turn 1', 'Turn 2')))
    assert GameSession.objects.get(session_id=adventure.conversation_id).hidden_state['visits'] == 2
    response = auth_client.post('/chat/api/rollback', json.dumps({
        'conversation_id': adventure.conversation_id, 'message_id': first['message']['id']
    }), content_type='application/json')
    assert response.status_code == 200
    assert 'engine_snapshot' not in response.content.decode()
    session = GameSession.objects.get(session_id=adventure.conversation_id)
    assert session.hidden_state['visits'] == 1
    assert session.workflow_snapshot == spec


@pytest.mark.django_db
def test_user_context_target_does_not_change_saved_action(adventure):
    configure(adventure, workflow(
        {'type': 'ConcatenatePrompt', 'target': 'user', 'prompt': 'Private context', 'include_state': False},
        {'type': 'GenerateTurn'},
    ))
    llm = Mock(return_value=STORY)
    execute(adventure, llm)
    assert 'Private context' in llm.call_args.kwargs['messages'][-1]['content']
    assert 'Private context' not in llm.call_args.kwargs['system_prompt']
    assert adventure.messages.filter(role='user').get().content == 'Go'


@pytest.mark.django_db
def test_refusal_repair_receives_state_without_rerunning_python(adventure, configuration):
    configuration.enable_refusal_detection = True
    from tests.conftest import LLMModelFactory, PromptFactory
    configuration.classifier_model = LLMModelFactory()
    configuration.classifier_prompt = PromptFactory(prompt_type='classifier')
    configuration.turn_correction_model = LLMModelFactory()
    configuration.turn_correction_prompt = PromptFactory(prompt_type='turn-correction')
    configuration.save()
    # Opening turn remains uncorrectable by design; exercise repair on turn two.
    execute(adventure, Mock(side_effect=[STORY, 'NO']))
    session = GameSession.objects.get(session_id=adventure.conversation_id)
    session.workflow_snapshot = workflow(
        {'type': 'RunPython', 'code': "state['visits'] = state.get('visits', 0) + 1"},
        {'type': 'ConcatenatePrompt'}, {'type': 'GenerateTurn'}, {'type': 'ReWriteRefusal'},
    )
    session.save()
    llm = Mock(side_effect=['I cannot continue.', 'YES', STORY.replace('Turn 1', 'Turn 2'), 'NO'])
    execute(adventure, llm)
    assert GameSession.objects.get(pk=session.pk).hidden_state['visits'] == 1
    assert 'visits' in llm.call_args_list[2].kwargs['system_prompt']
    assert llm.call_args_list[2].kwargs['llm_model'] == configuration.turn_correction_model


@pytest.mark.django_db
def test_shared_call_budget_and_stale_commit(adventure):
    from game.engine.nodes import load_turn, save_game, validate_turn
    first = load_turn(adventure, 'Go', Mock(), Mock(), Mock())
    first.calls = 16
    with pytest.raises(TimeoutError):
        first.model_call(messages=[])
    first = load_turn(adventure, 'Go', Mock(), Mock(), Mock())
    configure(adventure, workflow({'type': 'GenerateTurn'}))
    execute(adventure, Mock(return_value=STORY))
    first.candidate = STORY
    validate_turn(first, {})
    with pytest.raises(TurnUnavailable):
        save_game(first, {})
    assert adventure.messages.count() == 2


@pytest.mark.django_db
def test_failed_validation_has_a_trace_but_no_saved_turn(adventure):
    from game.models import AuditLog
    configure(adventure, workflow({'type': 'GenerateTurn'}))
    with pytest.raises(ValueError, match='exactly two choices'):
        execute(adventure, Mock(return_value='Story\n1) A\n2) B\n3) C'))
    assert not adventure.messages.exists()
    audit = AuditLog.objects.get(details__type='workflow_error')
    assert audit.details['node'] == 'ValidateTurn'
    assert audit.details['trace'][-1]['status'] == 'failed'


def test_invalid_python_syntax_is_a_configuration_error():
    with pytest.raises(ValueError, match='syntax'):
        validate_workflow(workflow({'type': 'RunPython', 'code': 'if :'}, {'type': 'GenerateTurn'}))


@pytest.mark.django_db
def test_admin_can_save_workflow_and_reject_invalid_workflow(admin_client, configuration, game_ending_prompt, mock_ollama_models):
    spec = workflow({'type': 'GenerateTurn'})
    payload = {
        'action': 'save', 'name': configuration.name,
        'adventure_prompt': configuration.adventure_prompt_id,
        'storyteller_model': configuration.storyteller_model_id,
        'game_ending_prompt': game_ending_prompt.pk,
        'total_turns': 10, 'phase1_turns': 3, 'phase2_turns': 3,
        'phase3_turns': 3, 'phase4_turns': 1, 'workflow': json.dumps(spec),
    }
    path = f'/admin/configurations/{configuration.pk}/'
    assert admin_client.post(path, payload).status_code == 302
    configuration.refresh_from_db()
    assert configuration.workflow == spec
    payload['workflow'] = '{broken json}'
    assert admin_client.post(path, payload).status_code == 200
    configuration.refresh_from_db()
    assert configuration.workflow == spec


@pytest.mark.django_db
@pytest.mark.parametrize('label', ['json', ''])
def test_standard_json_label_is_accepted_without_extra_call(adventure, label):
    configure(adventure, workflow({'type': 'GenerateTurn'}, {'type': 'ExtractJSON'},
                                {'type': 'ApplyStateChanges', 'allowed_keys': ['inventory']}))
    llm = Mock(return_value=STORY + '\n```' + label + '\n{"inventory": ["brass key"]}\n```')
    result = execute(adventure, llm)
    assert llm.call_count == 1
    assert result['message']['content'] == STORY
    assert GameSession.objects.get(session_id=adventure.conversation_id).hidden_state['inventory'] == ['brass key']


@pytest.mark.django_db
def test_missing_state_block_is_repaired_without_rewriting_story(adventure):
    configure(adventure, workflow({'type': 'GenerateTurn'}, {'type': 'ExtractJSON'},
                                {'type': 'ApplyStateChanges', 'allowed_keys': ['inventory']}))
    llm = Mock(side_effect=[STORY, '```game-state\n{"inventory": []}\n```'])
    result = execute(adventure, llm)
    assert llm.call_count == 2
    assert result['message']['content'] == STORY
    assert 'RepairStateJSON' in [node['type'] for node in adventure.messages.get(role='assistant').metadata['workflow_trace']]


@pytest.mark.django_db
def test_state_repair_does_not_inherit_narration_contract(adventure):
    configure(adventure, workflow({'type': 'ConcatenatePrompt', 'prompt': 'SECRET NARRATOR DIRECTION'},
                                {'type': 'GenerateTurn'}, {'type': 'ExtractJSON'},
                                {'type': 'ApplyStateChanges', 'allowed_keys': ['inventory']}))
    llm = Mock(side_effect=[STORY, 'Here is the extracted state.\n```json\n{"inventory": []}\n```'])
    result = execute(adventure, llm)
    assert 'SECRET NARRATOR DIRECTION' not in llm.call_args_list[1].kwargs['system_prompt']
    assert result['message']['content'] == STORY


@pytest.mark.django_db
def test_plain_labeled_state_is_extracted_without_extra_call(adventure):
    configure(adventure, workflow({'type': 'GenerateTurn'}, {'type': 'ExtractJSON'},
                                {'type': 'ApplyStateChanges', 'allowed_keys': ['inventory']}))
    llm = Mock(return_value=STORY + '\ngame-state: {"inventory": ["key"]}')
    result = execute(adventure, llm)
    assert llm.call_count == 1
    assert result['message']['content'] == STORY
    assert GameSession.objects.get(session_id=adventure.conversation_id).hidden_state['inventory'] == ['key']

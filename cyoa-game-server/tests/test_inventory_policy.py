"""Adventure-specific loot rates, cooldowns, and bounded narrative reconciliation."""
from unittest.mock import Mock

import pytest

from game.engine import inventory
from game.engine.turn_execution import execute_turn, validate_workflow
from game.judge_pipeline import run_judge_pipeline
from game.refusal_detector import process_potential_refusal
from game.models import GameSession, AuditLog
from game.openrouter_utils import MeteredText
from tests.conftest import ChatConversationFactory

STORY = 'Turn 1 of 10\nThe room is cold.\n1) Search\n2) Leave'


def spec(probability=1, cooldown=2):
    return {'version': 1, 'nodes': [
        {'type': 'GateInventory', 'probability': probability, 'cooldown_turns': cooldown, 'verify_narrative': False},
        {'type': 'ConcatenatePrompt'}, {'type': 'GenerateTurn'},
        {'type': 'ExtractJSON'}, {'type': 'ApplyStateChanges', 'allowed_keys': ['inventory']},
        {'type': 'ValidateTurn'}, {'type': 'SaveGame'},
    ]}


def test_cooldown_counts_complete_turns_after_actual_award():
    settings = {'probability': 1, 'cooldown_turns': 2}
    state = {'inventory_policy': {'last_grant_turn': 1}}
    assert not inventory.plan_award(state, settings, 2, 0)['allowed_this_turn']
    assert not inventory.plan_award(state, settings, 3, 0)['allowed_this_turn']
    assert inventory.plan_award(state, settings, 4, 0)['allowed_this_turn']
    assert not inventory.plan_award({}, {'probability': 0}, 1, 0)['allowed_this_turn']


def test_loss_and_consumption_are_allowed_without_an_award():
    policy = inventory.plan_award({}, {'probability': 0}, 2, 0.5)
    assert inventory.additions(['torch', 'salt'], ['torch'], policy) == set()
    with pytest.raises(ValueError, match='No new items'):
        inventory.additions(['torch'], ['torch', 'gold bar'], policy)


def test_duplicate_aliases_do_not_bypass_item_limits():
    policy = inventory.plan_award({}, {'probability': 1}, 2, 0)
    with pytest.raises(ValueError, match='unique'):
        inventory.additions([], ['Brass key', ' brass   KEY '], policy)
    with pytest.raises(ValueError, match='Too many'):
        inventory.additions([], ['key', 'torch'], policy)


@pytest.mark.parametrize('settings', [{'probability': -1}, {'cooldown_turns': -1}, {'cooldown_turns': 1.5}, {'max_new_items': 0}])
def test_bad_policy_settings_are_rejected(settings):
    with pytest.raises(ValueError):
        inventory.check_settings(settings)


@pytest.mark.django_db
def test_award_then_cooldown_and_repair_without_reroll(user, configuration):
    configuration.enable_refusal_detection = False
    configuration.workflow = spec()
    configuration.save()
    conv = ChatConversationFactory(user=user, metadata={'config_id': configuration.pk})
    def execute(llm):
        return execute_turn(conv, 'Search', call_llm=llm,
                            correct_refusal=process_potential_refusal, judge_turn=run_judge_pipeline)
    execute(Mock(return_value=STORY + '\n```json\n{"inventory":["key"]}\n```'))
    session = GameSession.objects.get(session_id=conv.conversation_id)
    assert session.hidden_state['inventory_policy']['last_grant_turn'] == 1
    llm = Mock(side_effect=[
        STORY.replace('Turn 1', 'Turn 2') + '\n```json\n{"inventory":["key","gold bar"]}\n```',
        STORY.replace('Turn 1', 'Turn 2') + '\n```game-state\n{"inventory":["key"]}\n```',
    ])
    execute(llm)
    assert llm.call_count == 2
    session.refresh_from_db()
    assert session.hidden_state['inventory'] == ['key']
    assert session.hidden_state['inventory_policy']['last_grant_turn'] == 1
    assert not session.hidden_state['inventory_policy']['allowed_this_turn']
    assert 'RepairInventoryAward' in [node['type'] for node in conv.messages.last().metadata['workflow_trace']]


@pytest.mark.django_db
def test_unused_permission_does_not_start_cooldown(user, configuration):
    configuration.enable_refusal_detection = False
    configuration.workflow = spec()
    configuration.save()
    conv = ChatConversationFactory(user=user, metadata={'config_id': configuration.pk})
    execute_turn(conv, 'Wait', call_llm=Mock(return_value=STORY + '\n```json\n{}\n```'),
                 correct_refusal=process_potential_refusal, judge_turn=run_judge_pipeline)
    assert GameSession.objects.get(session_id=conv.conversation_id).hidden_state['inventory_policy']['last_grant_turn'] is None


def test_narrator_cannot_change_award_policy():
    workflow = spec()
    workflow['nodes'][4]['allowed_keys'].append('inventory_policy')
    with pytest.raises(ValueError, match='engine-owned'):
        validate_workflow(workflow)


@pytest.mark.django_db
def test_terminal_turn_can_award_charred_remains(user, configuration):
    configuration.enable_refusal_detection = False
    configuration.workflow = spec()
    configuration.save()
    conv = ChatConversationFactory(user=user, metadata={'config_id': configuration.pk})
    llm = Mock(side_effect=[
        'The ceiling falls.\nGAME OVER\n```json\n{"inventory":["charred remains"]}\n```',
        'The ceiling falls.\nGAME OVER\n```json\n{"inventory":[]}\n```',
    ])
    execute_turn(conv, 'Run', call_llm=llm, correct_refusal=process_potential_refusal, judge_turn=run_judge_pipeline)
    session = GameSession.objects.get(session_id=conv.conversation_id)
    assert session.game_over
    assert session.hidden_state['inventory'] == ['charred remains']
    assert llm.call_count == 1


@pytest.mark.django_db
def test_unrecorded_narrative_item_is_repaired(user, configuration):
    configuration.enable_refusal_detection = False
    configuration.workflow = spec(probability=0)
    configuration.workflow['nodes'][0]['verify_narrative'] = True
    configuration.save()
    conv = ChatConversationFactory(user=user, metadata={'config_id': configuration.pk})
    llm = Mock(side_effect=[
        'Turn 1 of 10\nYou pocket an ornate box.\n1) Stay\n2) Go\n```json\n{}\n```',
        'FAIL\nThe box was acquired but is absent from inventory.',
        'Turn 1 of 10\nThe box crumbles before you can take it.\n1) Stay\n2) Go\n```json\n{}\n```',
        'PASS',
    ])
    result = execute_turn(conv, 'Steal', call_llm=llm, correct_refusal=process_potential_refusal, judge_turn=run_judge_pipeline)
    assert 'crumbles' in result['message']['content']
    assert GameSession.objects.get(session_id=conv.conversation_id).hidden_state.get('inventory', []) == []
    assert llm.call_count == 4


@pytest.mark.django_db
def test_requested_taking_bypasses_gift_gate_and_does_not_start_cooldown(user, configuration):
    configuration.enable_refusal_detection = False
    configuration.workflow = spec(probability=0)
    configuration.save()
    conv = ChatConversationFactory(user=user, metadata={'config_id': configuration.pk})
    llm = Mock(return_value=MeteredText(STORY + '\n```json\n{"inventory":["gold bar"],"_requested_items":["gold bar"]}\n```', {'id': 'gen-test', 'usage': {'cost': 0.0001}}))
    execute_turn(conv, 'Pocket the gold bar', call_llm=llm, correct_refusal=process_potential_refusal, judge_turn=run_judge_pipeline)
    state = GameSession.objects.get(session_id=conv.conversation_id).hidden_state
    assert state['inventory'] == ['gold bar']
    assert state['inventory_policy']['last_grant_turn'] is None
    assert '_requested_items' not in state
    request = AuditLog.objects.latest('id').details['model_requests'][0]
    assert request['generation_id'] == 'gen-test'
    assert request['usage']['cost'] == 0.0001
    assert llm.call_count == 1


def test_requested_items_do_not_exempt_unrelated_gifts():
    policy = inventory.plan_award({}, {'probability': 0}, 2, 0.5)
    with pytest.raises(ValueError, match='spontaneously'):
        inventory.additions([], ['gold bar', 'bonus key'], policy, ['gold bar'])

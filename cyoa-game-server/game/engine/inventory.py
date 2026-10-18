"""Optional, adventure-specific item-award probability and cooldown."""


def check_settings(step):
    if type(step.get('verify_narrative', True)) is not bool:
        raise ValueError('Inventory verify_narrative must be boolean')
    probability = step.get('probability', 0.25)
    cooldown = step.get('cooldown_turns', 2)
    maximum = step.get('max_new_items', 1)
    if not isinstance(probability, (int, float)) or not 0 <= probability <= 1:
        raise ValueError('Inventory probability must be between zero and one')
    if type(cooldown) is not int or not 0 <= cooldown <= 100:
        raise ValueError('Inventory cooldown_turns must be an integer from 0 to 100')
    if type(maximum) is not int or not 1 <= maximum <= 20:
        raise ValueError('Inventory max_new_items must be an integer from 1 to 20')


def plan_award(state, step, turn_number, roll):
    check_settings(step)
    previous = state.get('inventory_policy', {}).get('last_grant_turn')
    next_eligible = previous + step.get('cooldown_turns', 2) + 1 if previous is not None else 1
    return {
        'verify_narrative': step.get('verify_narrative', True),
        'probability': step.get('probability', 0.25),
        'cooldown_turns': step.get('cooldown_turns', 2),
        'max_new_items': step.get('max_new_items', 1),
        'last_grant_turn': previous,
        'next_eligible_turn': next_eligible,
        'allowed_this_turn': turn_number >= next_eligible and roll < step.get('probability', 0.25),
        'roll': roll,
    }


def item_names(items):
    if not isinstance(items, list) or any(not isinstance(item, str) or not item.strip() for item in items):
        raise ValueError('Inventory must be a list of nonempty item names')
    normalized = [' '.join(item.split()).casefold() for item in items]
    if len(set(normalized)) != len(normalized):
        raise ValueError('Inventory item names must be unique')
    return set(normalized)


def additions(before, after, policy, requested=()):
    new = item_names(after) - item_names(before)
    requested_names = item_names(list(requested))
    if not requested_names <= new:
        raise ValueError('Requested acquisitions must be new items present in inventory')
    new -= requested_names
    if new and not policy['allowed_this_turn']:
        raise ValueError('No new items may be spontaneously awarded this turn: probability or cooldown denied the award')
    if len(new) > policy['max_new_items']:
        raise ValueError('Too many new items awarded this turn')
    return new

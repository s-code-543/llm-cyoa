"""Narrative format helpers shared by the engine and HTTP adapters."""
import re
import json


def clean_narrative_metadata(text):
    """Drop standalone acquisition bookkeeping accidentally emitted outside JSON."""
    text = re.sub(r'^\s*_requested_items\s*:[^\n]*(?:\n|$)', '', text,
                  flags=re.MULTILINE).strip()
    trailing = trailing_state_response(text)
    return trailing[0] if trailing else text


def trailing_state_response(text):
    """Recognize a complete trailing ledger without accepting arbitrary story JSON."""
    for match in re.finditer(r'\{', text):
        try:
            value, consumed = json.JSONDecoder(parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value))).raw_decode(text[match.start():])
        except ValueError:
            continue
        if (isinstance(value, dict)
                and {'inventory', 'inventory_policy', '_requested_items', 'turns_played'} & value.keys()
                and not text[match.start() + consumed:].strip()):
            return text[:match.start()].rstrip(), value
    return None


def normalize_turn_header(text, current, maximum):
    """The engine owns turn numbering, including malformed model placeholders."""
    return re.sub(r'(?im)^(\s*(?:\*{1,2}|#{1,6}\s*)?)Turn\s+(?:\d+|N|X)\s*(?:of|/)\s*(?:\d+|N|Y)',
                  lambda match: f'{match.group(1)}Turn {current} of {maximum}', text, count=1)


def is_story_ending(text):
    """Recognize explicit terminal markers, never incidental mentions in prose."""
    return bool(re.search(
        r'^\s*(?:\*{1,2}|#{1,6}\s*)?(?:GAME OVER|THE END|VICTORY|DEFEAT)'
        r'(?:[.!])?(?:\*{1,2})?\s*$', text, re.IGNORECASE | re.MULTILINE
    ))


ENDING_INSTRUCTION = (
    "\n\nIf the protagonist dies, loses definitively, wins, or reaches any natural "
    "ending, end immediately with GAME OVER or THE END on its own line and no "
    "choices. These endings may happen before the final scheduled turn."
)


def extract_game_state(text):
    """
    Extract turn info and choices from LLM response.
    Returns dict with turn_current, turn_max, choice1, choice2.
    """
    state = {
        'turn_current': 0,
        'turn_max': 20,
        'choice1': '',
        'choice2': '',
        'inventory': []
    }

    # Extract "Turn X of Y" or "Turn X/Y"
    turn_match = re.search(r'Turn\s+(\d+)\s*(?:of|/)\s*(\d+)', text, re.IGNORECASE)
    if turn_match:
        state['turn_current'] = int(turn_match.group(1))
        state['turn_max'] = int(turn_match.group(2))

    # Extract choices - comprehensive regex to handle many variations:
    # - Separators: ) . ] - :
    # - Indentation: any leading whitespace
    # - Bold/italic wrapping: **1)** or **1.** or *1)* etc.
    # - Examples: "1)", "1.", "1-", "1:", "**1)**", "  1.", etc.
    lines = text.split('\n')
    current_choice = None
    choice_texts = {}

    for line in lines:
        # Pattern explanation:
        # ^\s*           - optional leading whitespace (indentation)
        # \*{0,2}        - optional markdown bold (0-2 asterisks before number)
        # (\d+)          - capture the choice number
        # \*{0,2}        - optional markdown bold (0-2 asterisks after number)
        # \s*            - optional whitespace
        # [.)\]:-]       - separator: ) . ] - :
        # \*{0,2}        - optional markdown bold (0-2 asterisks after separator)
        # \s*            - optional whitespace
        # (.+)           - capture the choice text
        choice_match = re.match(r'^\s*\*{0,2}\s*(\d+)\s*\*{0,2}\s*[.)\]:-]\s*\*{0,2}\s*(.+)', line)
        if choice_match:
            choice_num = int(choice_match.group(1))
            choice_text = choice_match.group(2).strip()
            # Clean up any remaining markdown formatting from choice text
            choice_text = re.sub(r'^\*+|\*+$', '', choice_text).strip()
            if choice_num in [1, 2]:
                current_choice = choice_num
                choice_texts[choice_num] = choice_text
        elif current_choice and line.strip() and line[:1].isspace() and not re.match(r'^\s*\*{0,2}\s*\d+\s*\*{0,2}\s*[.)\]:-]', line):
            # Continuation of current choice (multi-line)
            choice_texts[current_choice] += ' ' + line.strip()
        else:
            current_choice = None

    # Assign to state
    if 1 in choice_texts:
        state['choice1'] = choice_texts[1]
    if 2 in choice_texts:
        state['choice2'] = choice_texts[2]

    # Debug output
    print(f"[EXTRACT_STATE] Turn: {state['turn_current']}/{state['turn_max']}")
    print(f"[EXTRACT_STATE] Choice 1: {state['choice1'][:50] if state['choice1'] else 'NOT FOUND'}")
    print(f"[EXTRACT_STATE] Choice 2: {state['choice2'][:50] if state['choice2'] else 'NOT FOUND'}")

    return state



def public_metadata(metadata):
    """Never expose hidden state or raw model attempts through player endpoints."""
    result = {key: metadata[key] for key in ('is_error', 'game_over', 'turn_number') if key in metadata}
    refusal = metadata.get('refusal_info')
    result['refusal_info'] = {key: bool(refusal.get(key)) for key in (
        'was_refusal', 'was_corrected', 'turn_1_refusal', 'all_attempts_failed'
    )} if refusal else None
    judge = metadata.get('judge_info')
    result['judge_info'] = {'was_modified': bool(judge.get('was_modified'))} if judge else None
    return result


def parse_state_response(candidate):
    """Accept a single fenced object or an explicit plain game-state: object."""
    fences = list(re.finditer(r'```(?:game-state|json)?[ \t]*\r?\n(.*?)\r?\n```',
                              candidate, re.DOTALL | re.IGNORECASE))
    labels = list(re.finditer(r'^[ \t]*game-state[ \t]*:[ \t]*', candidate, re.MULTILINE | re.IGNORECASE))
    if not fences and not labels:
        trailing = trailing_state_response(candidate)
        if trailing:
            return trailing
    if len(fences) + len(labels) != 1:
        raise ValueError('Expected exactly one game-state JSON block')
    reject_constant = lambda value: (_ for _ in ()).throw(ValueError(value))
    if fences:
        match = fences[0]
        proposal = json.loads(match.group(1), parse_constant=reject_constant)
        start, end = match.span()
    else:
        match = labels[0]
        remainder = candidate[match.end():]
        whitespace = len(remainder) - len(remainder.lstrip())
        proposal, consumed = json.JSONDecoder(parse_constant=reject_constant).raw_decode(remainder.lstrip())
        start, end = match.start(), match.end() + whitespace + consumed
    if not isinstance(proposal, dict):
        raise ValueError('Proposed game state must be an object')
    return (candidate[:start] + candidate[end:]).strip(), proposal


def public_content(content, metadata):
    """Hide explicitly marked state metadata from older saved model responses."""
    workflow = metadata.get('engine_snapshot', {}).get('workflow', {})
    if not any(node.get('type') == 'ExtractJSON' for node in workflow.get('nodes', [])):
        return content
    content = clean_narrative_metadata(content)
    try:
        return parse_state_response(content)[0]
    except ValueError:
        return content

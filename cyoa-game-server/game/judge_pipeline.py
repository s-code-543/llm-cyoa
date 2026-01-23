"""
Judge pipeline for evaluating and optionally rewriting CYOA turns.
"""
from typing import Dict, Any
from .llm_router import call_llm


def _parse_boolean_response(text: str, default: bool = False) -> bool:
    if not text:
        return default
    upper = text.strip().upper()
    if upper.startswith('YES') or upper.startswith('PASS') or ' YES' in upper:
        return True
    if upper.startswith('NO') or upper.startswith('FAIL') or ' NO' in upper:
        return False
    return default


def run_judge_pipeline(messages, story_turn: str, config) -> Dict[str, Any]:
    """
    Run configured judge steps in order. Returns dict with final_turn and step details.
    """
    result = {
        'final_turn': story_turn,
        'was_modified': False,
        'steps': []
    }

    if not config:
        return result

    judge_steps = config.judge_steps.filter(enabled=True).order_by('order', 'id')
    if not judge_steps.exists():
        return result

    current_turn = story_turn

    for step in judge_steps:
        step_result = {
            'step_id': step.id,
            'name': step.name,
            'enabled': step.enabled,
            'judge_pass': None,
            'judge_response': '',
            'rewrite_response': '',
            'compare_pass': None,
            'compare_response': '',
            'used_rewrite': False,
            'final_used': 'original'
        }

        try:
            judge_response = call_llm(
                messages=[{'role': 'user', 'content': current_turn}],
                system_prompt=step.judge_prompt.prompt_text,
                llm_model=step.judge_model,
                timeout=step.judge_timeout
            )
            step_result['judge_response'] = judge_response
            judge_pass = _parse_boolean_response(judge_response, default=True)
            step_result['judge_pass'] = judge_pass

            if judge_pass:
                step_result['final_used'] = 'original'
                result['steps'].append(step_result)
                continue

            rewrite_instruction = step.rewrite_instruction.strip() or "Fix the difficulty of this turn to make it playable."
            rewrite_messages = list(messages) + [
                {'role': 'user', 'content': rewrite_instruction}
            ]
            rewrite_response = call_llm(
                messages=rewrite_messages,
                system_prompt=step.rewrite_prompt.prompt_text,
                llm_model=step.rewrite_model,
                timeout=step.rewrite_timeout
            )
            step_result['rewrite_response'] = rewrite_response

            compare_question = (step.compare_question or "Is the revised turn better than the original?").strip()
            compare_payload = (
                "ORIGINAL TURN:\n"
                f"{current_turn}\n\n"
                "REVISED TURN:\n"
                f"{rewrite_response}\n\n"
                f"{compare_question} Answer YES or NO."
            )
            compare_response = call_llm(
                messages=[{'role': 'user', 'content': compare_payload}],
                system_prompt=step.compare_prompt.prompt_text,
                llm_model=step.compare_model,
                timeout=step.compare_timeout
            )
            step_result['compare_response'] = compare_response
            compare_pass = _parse_boolean_response(compare_response, default=False)
            step_result['compare_pass'] = compare_pass

            if compare_pass:
                current_turn = rewrite_response
                step_result['used_rewrite'] = True
                step_result['final_used'] = 'rewrite'
                result['was_modified'] = True
            else:
                step_result['final_used'] = 'original'

            result['steps'].append(step_result)

        except Exception as exc:
            step_result['error'] = str(exc)
            step_result['final_used'] = 'original'
            result['steps'].append(step_result)

    result['final_turn'] = current_turn
    return result

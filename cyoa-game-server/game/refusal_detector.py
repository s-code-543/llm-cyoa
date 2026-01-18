"""
Refusal detection and correction system for CYOA game.

This module handles:
1. Detecting when the storyteller refuses to generate a valid turn
2. Stripping refusal content from the message chain
3. Calling the judge to generate a replacement turn
"""
from .llm_router import call_llm


def detect_refusal(story_turn, classifier_model, classifier_prompt_text, timeout=10):
    """
    Use a classifier model to determine if a story turn is a refusal.
    
    Args:
        story_turn: The storyteller's response text
        classifier_model: Model to use for classification (e.g., "gemma3:270m")
        classifier_prompt_text: System prompt explaining how to classify
        timeout: Classification timeout in seconds
    
    Returns:
        tuple: (is_refusal: bool, classifier_response: str)
    """
    if not classifier_model or not classifier_prompt_text:
        print("[REFUSAL] No classifier configured, skipping detection")
        return False, ""
    
    # Build classification message
    messages = [{
        "role": "user",
        "content": f"Classify this response:\n\n{story_turn}"
    }]
    
    try:
        print(f"[REFUSAL] Checking with {classifier_model}")
        
        classifier_response = call_llm(
            messages=messages,
            system_prompt=classifier_prompt_text,
            model=classifier_model,
            timeout=timeout
        )
        
        # Check if response indicates refusal
        # Looking for YES/REFUSAL/TRUE or similar affirmative answers
        response_lower = classifier_response.strip().lower()
        is_refusal = any(keyword in response_lower for keyword in [
            'yes', 'refusal', 'true', 'refusing', 'refused'
        ])
        
        if is_refusal:
            print(f"[REFUSAL] ⚠️  Detected refusal: {classifier_response[:100]}")
        else:
            print(f"[REFUSAL] ✓ Valid turn: {classifier_response[:100]}")
        
        return is_refusal, classifier_response
    
    except Exception as e:
        print(f"[REFUSAL] Classification error: {e}")
        # On error, assume it's not a refusal (fail-safe)
        return False, f"Error: {str(e)}"


def strip_refusal_from_messages(messages):
    """
    Remove the last assistant message (the refusal) from the message chain.
    
    Args:
        messages: List of message dicts with 'role' and 'content'
    
    Returns:
        List of messages with the last assistant message removed
    """
    if not messages:
        return messages
    
    # Simply remove the last message (which should be the refusal from assistant)
    if messages and messages[-1].get('role') == 'assistant':
        filtered = messages[:-1]
        print(f"[REFUSAL] Stripped last assistant message: {len(filtered)} messages remaining")
        return filtered
    
    # If last message wasn't from assistant, return as-is
    return messages


def generate_corrected_turn(messages, turn_correction_prompt_text, turn_correction_model, timeout=30):
    """
    Use the turn correction prompt to generate a valid turn.
    
    Args:
        messages: Message chain with refusal stripped
        turn_correction_prompt_text: Turn correction prompt (used as-is)
        turn_correction_model: LLMModel instance to use for correction
        timeout: Generation timeout in seconds
    
    Returns:
        str: Generated corrected turn
    """
    try:
        print(f"[REFUSAL] Generating correction with {turn_correction_model.name}")
        
        corrected_turn = call_llm(
            messages=messages,
            system_prompt=turn_correction_prompt_text,
            llm_model=turn_correction_model,
            timeout=timeout
        )
        
        print(f"[REFUSAL] ✓ Generated corrected turn: {len(corrected_turn)} chars")
        return corrected_turn
    
    except Exception as e:
        print(f"[REFUSAL] Error generating correction: {e}")
        raise


def process_potential_refusal(
    messages,
    story_turn,
    config,
    user_message
):
    """
    Complete refusal detection and correction pipeline.
    
    Args:
        messages: Full message history including the refusal
        story_turn: The storyteller's response (potential refusal)
        config: Configuration object with classifier/judge settings
        user_message: The user's last message content
    
    Returns:
        dict: {
            'final_turn': str,           # The final turn to use
            'was_refusal': bool,          # Whether a refusal was detected
            'classifier_response': str,   # Classifier's raw response
            'was_corrected': bool         # Whether correction was applied
        }
    """
    result = {
        'final_turn': story_turn,
        'was_refusal': False,
        'classifier_response': '',
        'was_corrected': False
    }
    
    # Skip if refusal detection is disabled
    if not config.enable_refusal_detection:
        print("[REFUSAL] Detection disabled in config")
        return result
    
    # Check for classifier configuration
    if not config.classifier_model or not config.classifier_prompt:
        print("[REFUSAL] No classifier configured, skipping")
        return result
    
    # Step 1: Detect refusal
    is_refusal, classifier_response = detect_refusal(
        story_turn=story_turn,
        classifier_model=config.classifier_model,
        classifier_prompt_text=config.classifier_prompt.prompt_text,
        timeout=config.classifier_timeout
    )
    
    result['was_refusal'] = is_refusal
    result['classifier_response'] = classifier_response
    
    # If not a refusal, return original turn
    if not is_refusal:
        return result
    
    # Step 2: Strip the refusal from messages
    cleaned_messages = strip_refusal_from_messages(messages)
    
    # Step 3: Generate corrected turn with turn correction prompt
    try:
        corrected_turn = generate_corrected_turn(
            messages=cleaned_messages,
            turn_correction_prompt_text=config.turn_correction_prompt.prompt_text,
            turn_correction_model=config.turn_correction_model,
            timeout=config.turn_correction_timeout
        )
        
        result['final_turn'] = corrected_turn
        result['was_corrected'] = True
        
        print(f"[REFUSAL] ✅ Successfully corrected refusal")
        
    except Exception as e:
        print(f"[REFUSAL] ❌ Failed to correct, using original: {e}")
        # Fall back to original turn if correction fails
    
    return result

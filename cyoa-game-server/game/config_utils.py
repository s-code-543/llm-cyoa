"""
Configuration utilities.
"""
from .models import Configuration


def get_active_configuration():
    """
    Retrieve the most recently updated configuration from database.
    Used as a fallback when no specific configuration is requested.
    
    Returns:
        Configuration instance or None
    """
    try:
        # Fallback to the most recently updated configuration since implicit 'active' is removed
        config = Configuration.objects.order_by('-updated_at').first()
        if not config:
            print("[WARNING] No configurations found in database")
        return config
    except Exception as e:
        print(f"[ERROR] Failed to load configuration from database: {e}")
        return None


def apply_pacing_template(prompt_text, config):
    """
    Replace template variables in prompt text with values from configuration.
    
    Args:
        prompt_text: The prompt text containing template variables
        config: Configuration instance with pacing values
    
    Returns:
        String with template variables replaced
    """
    if not config:
        return prompt_text
    
    pacing = config.get_pacing_dict()
    result = prompt_text
    
    for key, value in pacing.items():
        placeholder = f"{{{key}}}"
        result = result.replace(placeholder, str(value))
    
    return result


def get_conversation_configuration(conversation):
    """Resolve the configuration used by the existing story generation flow."""
    config_id = (conversation.metadata or {}).get('config_id')
    if config_id:
        config = Configuration.objects.filter(pk=config_id).first()
        if config:
            return config
    return get_active_configuration()


def conversation_tts_enabled(conversation):
    """Expose effective playback availability without exposing credentials."""
    from .models import TTSSettings
    from .tts_views import OPENAI_API_KEY

    config = get_conversation_configuration(conversation)
    return bool(config and config.enable_tts and OPENAI_API_KEY and TTSSettings.get_settings().enabled)


def configuration_models_available(config):
    """All model roles needed by this saved adventure must still be usable."""
    if not config:
        return False
    models = [config.storyteller_model]
    if config.enable_refusal_detection:
        if config.classifier_prompt_id or config.classifier_model_id:
            models.append(config.classifier_model)
        if config.turn_correction_prompt_id or config.turn_correction_model_id:
            models.append(config.turn_correction_model)
    if config.enable_image_generation:
        models.append(config.image_model)
    for step in config.judge_steps.filter(enabled=True):
        models.extend([step.rewrite_model, step.compare_model])
        if step.classifier_prompt_id:
            models.append(step.classifier_model)
    return all(model and model.is_available and model.provider.is_active for model in models)

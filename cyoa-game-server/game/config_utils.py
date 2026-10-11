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

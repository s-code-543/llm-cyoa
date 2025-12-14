"""
Anthropic API utilities for calling Claude models.
"""
import requests
from django.conf import settings


def call_anthropic(messages, system_prompt=None, model="claude-haiku-4-5"):
    """
    Call Anthropic API with the given messages.
    
    Args:
        messages: List of message dicts with 'role' and 'content'
        system_prompt: Optional system prompt string
        model: Claude model to use (default: claude-haiku-4-5)
    
    Returns:
        String response from Claude
    """
    # Process messages into Anthropic format
    processed_messages = []
    for message in messages:
        if isinstance(message.get("content"), list):
            # Handle multipart content (text + images potentially)
            processed_content = []
            for item in message["content"]:
                if item["type"] == "text":
                    processed_content.append({"type": "text", "text": item["text"]})
            processed_messages.append({
                "role": message["role"],
                "content": processed_content
            })
        else:
            # Simple text content
            processed_messages.append({
                "role": message["role"],
                "content": [{"type": "text", "text": message.get("content", "")}]
            })

    payload = {
        "model": model,
        "messages": processed_messages,
        "max_tokens": 4096,
        "temperature": 0.8,
    }

    if system_prompt:
        payload["system"] = system_prompt

    headers = {
        "x-api-key": settings.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    url = "https://api.anthropic.com/v1/messages"

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=(3.05, 60))
        
        if response.status_code != 200:
            raise Exception(f"HTTP Error {response.status_code}: {response.text}")

        res = response.json()
        return res["content"][0]["text"] if "content" in res and res["content"] else ""
    
    except requests.exceptions.RequestException as e:
        print(f"Anthropic API request failed: {e}")
        raise

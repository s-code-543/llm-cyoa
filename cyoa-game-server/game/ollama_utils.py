"""
Ollama API utilities for calling local LLM models.
"""
import requests
import os


# Ollama server URL - use localhost when running outside Docker, ollama when inside
OLLAMA_BASE_URL = os.getenv('OLLAMA_URL', 'http://localhost:11434')


def check_ollama_status():
    """
    Check if Ollama is responsive and what models are loaded.
    
    Returns:
        dict with 'available' (bool) and 'loaded_models' (list)
    """
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/ps", timeout=2)
        if response.status_code == 200:
            data = response.json()
            loaded_models = [m.get("name", "") for m in data.get("models", [])]
            return {"available": True, "loaded_models": loaded_models}
        return {"available": False, "loaded_models": []}
    except Exception as e:
        print(f"[OLLAMA] Status check failed: {e}")
        return {"available": False, "loaded_models": []}


def get_ollama_models():
    """
    Discover available models from the Ollama server.
    
    Returns:
        List of model dicts with 'id' and 'name' keys
    """
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        
        if response.status_code != 200:
            print(f"Failed to get Ollama models: {response.status_code}")
            return []
        
        data = response.json()
        models = []
        
        for model in data.get("models", []):
            model_name = model.get("name", "")
            models.append({
                "id": model_name,
                "name": model_name,
                "size": model.get("size", 0),
                "modified": model.get("modified_at", "")
            })
        
        return models
    
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to Ollama: {e}")
        return []


def call_ollama(messages, system_prompt=None, model="qwen3:4b", timeout=30):
    """
    Call Ollama API with the given messages.
    
    Args:
        messages: List of message dicts with 'role' and 'content'
        system_prompt: Optional system prompt string
        model: Ollama model to use (default: qwen3:4b)
        timeout: Read timeout in seconds (default: 30)
    
    Returns:
        String response from the model
    """
    # Remove "gameserver-ollama/" or "ollama/" prefix if present
    if model.startswith("gameserver-ollama/"):
        model = model[18:]
    elif model.startswith("ollama/"):
        model = model[7:]
    elif model.startswith("gameserver-"):
        model = model[11:]
    
    # Convert messages to Ollama format
    ollama_messages = []
    
    # Add system message if provided
    if system_prompt:
        ollama_messages.append({
            "role": "system",
            "content": system_prompt
        })
    
    # Add user/assistant messages
    for message in messages:
        if isinstance(message.get("content"), list):
            # Extract text from multipart content
            text_parts = [item["text"] for item in message["content"] if item["type"] == "text"]
            content = " ".join(text_parts)
        else:
            content = message.get("content", "")
        
        ollama_messages.append({
            "role": message["role"],
            "content": content
        })
    
    payload = {
        "model": model,
        "messages": ollama_messages,
        "stream": False,
        "options": {
            "temperature": 0.7,
            "top_p": 0.9,  # Slightly higher for more creative variety
            "top_k": 40,   # Increased from 20 for better creative writing
            "repeat_penalty": 1.1,  # Slightly higher to prevent repetitive phrasing
        }
    }
    
    try:
        print(f"[OLLAMA] {model} | timeout={timeout}s")
        
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json=payload,
            timeout=(3.05, timeout)  # configurable read timeout
        )
        
        if response.status_code != 200:
            error_msg = f"HTTP {response.status_code}: {response.text}"
            print(f"[OLLAMA] Error: {error_msg}")
            raise Exception(error_msg)
        
        res = response.json()
        content = res.get("message", {}).get("content", "")
        thinking = res.get("message", {}).get("thinking", "")
        
        # Qwen models sometimes only output to 'thinking' field instead of 'content'
        if len(content) == 0 and len(thinking) > 0:
            print(f"[OLLAMA] Warning: Model outputting to 'thinking' field only - check prompt design")
            return ""
        
        if len(content) == 0:
            print(f"[OLLAMA] Error: Empty response from {model}")
            print(f"[OLLAMA] Full response: {res}")
        
        return content
    
    except requests.exceptions.Timeout as e:
        print(f"[OLLAMA] Timeout after {timeout}s - model may be overloaded or too slow")
        print(f"[OLLAMA] Suggestion: Increase timeout in config or reduce concurrent requests")
        raise
    except requests.exceptions.RequestException as e:
        print(f"[OLLAMA] Request failed: {e}")
        raise

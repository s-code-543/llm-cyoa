"""
Ollama API utilities for calling local LLM models.
"""
import requests


# Ollama server runs in docker-compose network
OLLAMA_BASE_URL = "http://ollama:11434"


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
                "id": f"gameserver-ollama/{model_name}",
                "name": f"gameserver-{model_name}",
                "size": model.get("size", 0),
                "modified": model.get("modified_at", "")
            })
        
        return models
    
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to Ollama: {e}")
        return []


def call_ollama(messages, system_prompt=None, model="qwen3:30b"):
    """
    Call Ollama API with the given messages.
    
    Args:
        messages: List of message dicts with 'role' and 'content'
        system_prompt: Optional system prompt string
        model: Ollama model to use (default: qwen3:30b)
    
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
            "top_p": 0.8,
            "top_k": 20,
            "repeat_penalty": 1.05,
            "num_predict": 1200
        }
    }
    
    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json=payload,
            timeout=(3.05, 120)
        )
        
        if response.status_code != 200:
            raise Exception(f"HTTP Error {response.status_code}: {response.text}")
        
        res = response.json()
        return res.get("message", {}).get("content", "")
    
    except requests.exceptions.RequestException as e:
        print(f"Ollama API request failed: {e}")
        raise

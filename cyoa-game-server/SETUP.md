# CYOA Game Server Setup

## Architecture

The server is modular with separate utilities for different backends:

- **views.py** - Main orchestration logic (chat completions endpoint)
- **anthropic_utils.py** - Claude API integration
- **ollama_utils.py** - Ollama local LLM integration
- **file_utils.py** - Generic file/prompt loading
- **models_views.py** - Model discovery endpoint
- **test_views.py** - Test endpoints (no API calls)

## Docker Network Connection

Both `open-webui` and `cyoa-game-server` are in the same Docker Compose network, so they can communicate using service names.

**From Open WebUI, use this internal URL:**
```
http://cyoa-game-server:8000/v1
```

Note: Use port `8000` (internal container port), NOT `8001` (which is only for external access from your host machine).

## Setting Up in Open WebUI

### Option 1: Add as OpenAI-Compatible Connection (Recommended)

1. Go to **Settings** → **Connections** (or **Admin Panel** → **Settings** → **Connections**)
2. Click **Add Connection** or **+ OpenAI API**
3. Fill in:
   - **Name:** `CYOA Game Server`
   - **API Base URL:** `http://cyoa-game-server:8000/v1`
   - **API Key:** `any-value-here` (not validated, but required by the form)
4. Save

The server will show up with two models:
- `cyoa-test` - Test mode (no API calls)
- `cyoa-dual-claude` - Production (dual-LLM with Claude)

### Option 2: Custom Model Pipe (Alternative)

Create a new pipe in Open WebUI:

```python
import requests

class Pipe:
    def __init__(self):
        self.type = "manifold"
        self.name = "cyoa/"
    
    def pipes(self):
        return [
            {"id": "cyoa-test", "name": "CYOA Test"},
            {"id": "cyoa-dual-claude", "name": "CYOA Dual Claude"}
        ]
    
    def pipe(self, body: dict):
        response = requests.post(
            "http://cyoa-game-server:8000/v1/chat/completions",
            json=body,
            timeout=120
        )
        return response.json()
```

## Testing the Connection

### From your host machine (outside Docker):
```bash
# Test server is running
curl http://localhost:8001/v1/test

# List available models
curl http://localhost:8001/v1/models

# Test chat (no API calls)
curl -X POST http://localhost:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "cyoa-test",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

### From inside Docker network (e.g., from open-webui container):
```bash
# Access the container
docker exec -it open-webui /bin/bash

# Then test
curl http://cyoa-game-server:8000/v1/models
```

## Available Models

The server now supports multiple backends:

### 1. **cyoa-test**
Returns hardcoded pirate-themed response without making any API calls. Use this to test the Open WebUI integration.

### 2. **cyoa-dual-claude** 
Production mode using Claude:
- Calls Claude Haiku 4.5 as storyteller
- Calls Claude Haiku 4.5 as judge (validates game balance)
- Returns only the final, approved story turn

### 3. **Ollama Models**
Any model running in your Ollama container will be auto-discovered and listed with the `ollama/` prefix:
- `ollama/llama3.2` - Llama 3.2
- `ollama/mistral` - Mistral 7B
- `ollama/qwen2.5:24b` - Qwen 2.5 24B (recommended for testing)
- etc.

To use Ollama models, just select them from the models list. The server will automatically route to the Ollama backend.

## Choosing Backend Model

You can specify which backend model to use with the `backend_model` parameter in the request body:

```json
{
  "model": "cyoa-dual-claude",
  "backend_model": "ollama/qwen2.5:24b",
  "messages": [...]
}
```

This allows you to test with cheap local models before using Claude API calls.

## Remote Debugging

The server runs with debugpy on port 5678. To attach from VS Code:

1. Add to `.vscode/launch.json`:
```json
{
  "name": "Attach to Django in Docker",
  "type": "debugpy",
  "request": "attach",
  "connect": {
    "host": "localhost",
    "port": 5678
  },
  "pathMappings": [
    {
      "localRoot": "${workspaceFolder}/cyoa-game-server",
      "remoteRoot": "/app"
    }
  ]
}
```

2. Start the container: `docker-compose up cyoa-game-server`
3. In VS Code: Run → Start Debugging → Select "Attach to Django in Docker"
4. Set breakpoints in `game/views.py`

## Customizing the Judge

Edit `game/judge_prompt.txt` to change how the judge evaluates story turns. The server reads this file on each request, so you can modify it without restarting.

## Testing with Ollama

Before burning Claude API calls, test your game logic with a local Ollama model:

1. Pull a small, fast model (if not already available):
   ```bash
   docker exec ollama ollama pull qwen2.5:24b
   # or
   docker exec ollama ollama pull mistral
   ```

2. The model will automatically appear in the `/v1/models` list

3. Use it by setting `backend_model`:
   ```bash
   curl -X POST http://localhost:8001/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{
       "model": "cyoa-dual-claude",
       "backend_model": "ollama/qwen2.5:24b",
       "messages": [{"role": "user", "content": "Start adventure"}]
     }'
   ```

4. Attach debugger, set breakpoints, and iterate on game logic without API costs!

# CYOA Game Server - File Structure

## Core Files

### views.py
Main orchestration - handles chat completions endpoint and dual-LLM flow.
- `chat_completions(request)` - Main endpoint that orchestrates storyteller → judge flow
- `call_llm(messages, system_prompt, model)` - Universal router to appropriate backend

### anthropic_utils.py
Claude/Anthropic API integration.
- `call_anthropic(messages, system_prompt, model)` - Calls Claude API
- Handles message formatting, API key, error handling

### ollama_utils.py
Local Ollama LLM integration.
- `get_ollama_models()` - Auto-discover models from Ollama container
- `call_ollama(messages, system_prompt, model)` - Calls Ollama API
- Connects via docker network: `http://ollama:11434`

### file_utils.py
Generic utilities for loading text files.
- `load_prompt_file(filename)` - Load any text file from game/ directory

### models_views.py
Model discovery endpoint.
- `list_models(request)` - Returns list of available models (Claude + Ollama)

### test_views.py
Test endpoints that don't consume API calls.
- `test_endpoint(request)` - Returns hardcoded response for integration testing

## Prompt Files

### judge_prompt.txt
System prompt for the judge LLM that evaluates story turns for game balance.
Edit this to change judging criteria.

### test_prompt.txt
Hardcoded response used by test mode to verify connectivity.

## Configuration

### settings.py
Django settings including:
- `ANTHROPIC_API_KEY` - From environment variable

### urls.py
URL routing:
- `/v1/chat/completions` → views.chat_completions
- `/v1/models` → models_views.list_models
- `/v1/test` → test_views.test_endpoint

## Workflow

1. Open WebUI sends request to `/v1/chat/completions`
2. `chat_completions()` checks for test mode
3. If production, extracts messages and system prompt
4. Calls `call_llm()` with storyteller role
5. `call_llm()` routes to Anthropic or Ollama based on model name
6. Result goes to judge via second `call_llm()` call
7. Final approved turn returned to Open WebUI

## Adding New Backends

To add a new LLM backend (e.g., OpenAI, Cohere):

1. Create `{provider}_utils.py` with `call_{provider}()` function
2. Update `call_llm()` in views.py to route to new backend
3. Update `list_models()` to include new models
4. That's it!

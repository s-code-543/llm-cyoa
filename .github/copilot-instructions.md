# CYOA Game Server — AI Agent Instructions

⚠️ **READ THIS FIRST - MANDATORY WORKFLOW:**
1. **NEVER create virtual environments** - Use ONLY the existing `cyoa-py312` conda environment
2. **Install dependencies**: `conda run -n cyoa-py312 pip install <package>`
3. **After code changes**: Rebuild Docker (`docker-compose -f docker-compose.mac.yml up --build -d`)
4. **After features**: Run tests (`cd cyoa-game-server && conda run -n cyoa-py312 ./run_tests.sh`)

## Architecture Overview
This is a Django-based Choose Your Own Adventure game server with LLM-powered storytelling, multi-stage content quality control, and speech integration.

**Key Components:**
- **Django server** (`cyoa-game-server/`) - Main application running in Docker
- **LLM Router** (`llm_router.py`) - Unified interface supporting Ollama (local), Anthropic, OpenAI, OpenRouter
- **Judge Pipeline** (`judge_pipeline.py`) - Multi-step quality control with classifier → rewriter → comparator phases
- **Refusal Detector** (`refusal_detector.py`) - Detects and corrects policy refusals from storyteller models
- **STT/TTS** (`stt_views.py`, `tts_views.py`) - Speech-to-text (Whisper.cpp) and text-to-speech (OpenAI) APIs
- **Admin Interface** (`admin_views.py`) - Manage prompts, configurations, models, and view audit logs

## Runtime Environment (CRITICAL)
- **Server runs in Docker** via `docker-compose.mac.yml` - NEVER suggest running Django on host as primary path
- **Host Python (conda env `cyoa-py312`)** is ONLY for: tests, linters, one-off scripts, Django management commands
- **Whisper.cpp** runs natively on macOS (LaunchAgent), accessed from containers at `http://host.docker.internal:10300`
- **Ollama** runs natively on macOS, accessed from containers at `http://host.docker.internal:11434`
- **STRICT RULE**: Use the existing `cyoa-py312` conda environment. NEVER create new virtual environments.

## Data Flow: Story Generation
1. User sends message → `chat_api_send_message` in `chat_views.py`
2. Configuration loads prompts + models from database (`Configuration` → `Prompt`, `LLMModel`)
3. **Death roll**: `difficulty_utils.py` calculates probability → may trigger game-ending prompt
4. **Storyteller LLM**: `llm_router.call_llm()` generates story turn using adventure prompt
5. **Refusal Detection** (optional): `refusal_detector.detect_refusal()` checks if storyteller refused
   - If refusal: strips bad content, calls judge to generate replacement turn
6. **Judge Pipeline** (optional): `judge_pipeline.run_judge_pipeline()` runs configured steps:
   - Each step: Classifier (needs fix?) → Rewriter (generate improved) → Comparator (is better?)
   - Supports iterative retries if comparator rejects rewrite
7. **Audit Log**: All corrections/modifications logged to `AuditLog` model
8. Response returned with extracted game state (turn count, choices, inventory)

## Configuration System
Central to the app: `Configuration` model ties together:
- Adventure prompt (storytelling system prompt)
- Storyteller model (which LLM generates the story)
- Turn correction prompts (for refusals)
- Game-ending prompts (death/failure scenes)
- Judge steps (quality control pipeline with classifier/rewriter/comparator prompts)
- Difficulty profile (death probability curve)

View/edit via admin UI at `/admin/config/`.

## Security Patterns (ENFORCED)
- **CSRF**: ALL POST endpoints require CSRF tokens. Frontend sends `X-CSRFToken` header (retrieved from `<meta name="csrf-token">`).
- **Directory Traversal**: File operations use `.resolve().is_relative_to()` checks (see `tts_views.py` lines 65-75).
- **Authentication**: Two modes:
  - DEBUG: `debug_login_bypass` decorator allows unauthenticated access in dev
  - PRODUCTION: Optional Cloudflare Access JWT validation in `cloudflare_auth.py`
- **Staff-only Admin**: `debug_login_bypass` returns 403 for non-staff users

## Testing (pytest + pytest-django)
**Run tests**: `cd cyoa-game-server && conda run -n cyoa-py312 ./run_tests.sh`

**Key patterns** (see `tests/conftest.py`):
- **Factories**: Use `PromptFactory`, `ConfigurationFactory`, `LLMModelFactory`, etc. for test data
- **LLM Mocking**: `mock_call_llm` fixture auto-mocks all LLM calls with realistic responses
- **External Service Mocks**: `mock_ollama_models`, `mock_anthropic_connection`, `mock_whisper_api`, etc.
- **Sample Data**: Import `SAMPLE_VALID_TURN`, `SAMPLE_REFUSAL_TURN` from `conftest.py`

## Development Commands
```bash
# HOST: Run tests (conda env cyoa-py312)
cd cyoa-game-server && conda run -n cyoa-py312 ./run_tests.sh

# HOST: Run specific test
conda run -n cyoa-py312 pytest -xvs tests/test_chat_send.py::TestRefusalDetection

# HOST: Install dependency for tests/dev
conda run -n cyoa-py312 pip install <package>

# DOCKER: Rebuild and restart server
docker-compose -f docker-compose.mac.yml up --build -d

# DOCKER: View logs
docker logs -f cyoa-game-server

# DOCKER: Run Django management command
docker exec -it cyoa-game-server python manage.py <command>
```

## Dependency Management
- **Runtime deps**: Add to `requirements.txt` → rebuild Docker image
- **Test/dev deps**: Install into `cyoa-py312` conda env, optionally add to requirements.txt for reproducibility
- Container reaches host services at `http://host.docker.internal:<port>`

## Key Files Reference
- `models.py`: Database schema (Prompt, Configuration, AuditLog, GameSession, etc.)
- `llm_router.py`: Universal LLM caller routing to provider-specific utils
- `judge_pipeline.py`: Multi-phase quality control (classifier/rewriter/comparator)
- `refusal_detector.py`: Content policy refusal detection and correction
- `difficulty_utils.py`: Death probability calculations and pacing
- `chat_views.py`: Main game API endpoints
- `admin_views.py`: Admin UI for managing prompts/configs/models
- `cloudflare_auth.py`: JWT authentication for Cloudflare Access (Zero Trust)
- `tests/conftest.py`: Pytest fixtures, factories, and mocks

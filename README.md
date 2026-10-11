# LLM CYOA

Django powers the adventure engine, user sessions, model/provider configuration and admin UI. The new React + TypeScript chat is available alongside the original Django/Alpine chat. Provider API keys stay on the server.

## Local development

Prerequisites: Docker Desktop (running), Git. Node is optional on the host; the stack runs Vite in a Node container. OpenRouter storytelling needs no Ollama or OpenWebUI installation. Whisper is only needed for microphone transcription, and OpenAI TTS is optional.

From the repository root:

```sh
docker compose -f compose.dev.yml up -d --build
docker compose -f compose.dev.yml exec web python manage.py load_prompts
docker compose -f compose.dev.yml exec web python manage.py createsuperuser
```

Open http://localhost:8001 and sign in. In `/admin/`, configure your provider/key, import a model, and save an adventure configuration. The original chat remains `/chat/`; the React preview is `/chat/react/`. Existing conversations can be opened by changing `/chat/` to `/chat/react/` and preserving `?conversation_id=...`.

The dev stack binds only to 127.0.0.1:8001. It uses the `llm-cyoa-dev` Compose project with separate database/media volumes and no tunnel or shared Docker network. It preserves data from the initial temporary development stack using the same project/volume names. Source mounts and Vite HMR make most edits immediately visible; rebuild after Python dependency changes. A fresh stack has no user/provider/model/configuration until you create them. `load_prompts` updates prompt records, including existing versions; run it deliberately.

```sh
docker compose -f compose.dev.yml logs -f web frontend gateway
docker compose -f compose.dev.yml down
```

`down` preserves data. Avoid `down -v` unless deliberately deleting the development database/media. Leave the existing `docker-compose.mac.yml` and `docker-compose.nvidia.yml` home deployments alone; do not run those to develop locally. Port 8000 may belong to another app; this project uses 8001.

Optional environment values are listed in `.env.example`; copy it to the ignored `.env` if needed. OpenRouter keys are entered in the local admin, not the frontend environment. TTS needs a separate `OPENAI_API_KEY`, global TTS enabled, and the adventure's `Enable text-to-speech` switch. The React preview's first milestone is text and rollback; speech controls remain available in the original chat. Native Whisper endpoint defaults to `http://host.docker.internal:10300/v1/audio/transcriptions`. See README-MAC.md for the older native Whisper setup; its shared-network/tunnel startup steps are not needed here.

## Tests and builds

Backend tests use a disposable container with no network or development volumes. Do not run the suite against the app's media volume: the existing test cleanup fixture deletes recordings.

```sh
./scripts/test-backend.sh -q
./scripts/test-backend.sh tests/test_chat_api.py -q
```

Frontend tests and production assets, through Docker:

```sh
docker compose -f compose.dev.yml exec frontend npm test
docker compose -f compose.dev.yml exec frontend npm run build
```

Or with a current Node release installed locally:

```sh
cd frontend
npm ci
npm test
npm run build
```

Backend API tests mock the provider; frontend component tests use a mock API. Routine checks make no paid generation requests. Browser verification can reuse saved conversations without calling an LLM.

## Production configuration

`compose.prod.yml` is a separate configuration, not a migration of the home deployment. It builds frontend assets into a Django image, runs Gunicorn with DEBUG off, serves built static assets through WhiteNoise, uses separate production volumes and publishes HTTP on loopback port 8002. It includes no Vite, source mounts, debug port or tunnel. Required environment values fail validation if omitted.

```sh
docker compose --env-file /path/to/production.env -f compose.prod.yml build
docker compose --env-file /path/to/production.env -f compose.prod.yml up -d
```

Set a unique `DJANGO_SECRET_KEY`, explicit `DJANGO_ALLOWED_HOSTS`, and HTTPS `DJANGO_CSRF_TRUSTED_ORIGINS`. Put a trusted HTTPS proxy or tunnel in front of loopback HTTP; secure session/CSRF cookies require HTTPS. Django trusts `X-Forwarded-Proto`, so only the trusted proxy should reach the app. Cloudflare Access can be enabled with the documented env values; a tunnel alone is not authentication. Configure database/media backups before any real deployment. This configuration has not been deployed to the hosted copy.

## Structure and next work

- `frontend/`: React chat, typed API client, component tests and Vite build.
- `cyoa-game-server/game/chat_api.py`: versioned API adapter, state serialization and request deduplication.
- `cyoa-game-server/game/chat_views.py`: legacy turn orchestration and UI APIs.
- `cyoa-game-server/game/`: provider routing, refusal/judge pipeline, models, speech APIs and admin templates.
- `cyoa_prompts/`: versioned prompt files loaded into the database.
- `deploy/`: local gateway and production image configuration.

See [React migration plan](docs/react-chat-plan.md) and [chat API contract](docs/chat-api.md). Audio integration and final cutover follow the text-chat checkpoint. Engine/refusal-pipeline reorganization remains a separate later change.

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

Open http://localhost:8001 and sign in. The whole app is a React single-page app: `/` is the home page, `/chat` is the game, and administrators get an Administration menu (`/manage`) for configurations, prompts, providers, models, difficulty profiles, voice settings and the audit log. Users and groups are managed in Django's admin at `/django-admin/`. Old `/admin/...` links redirect to the matching `/manage/...` page.

The dev stack binds only to 127.0.0.1:8001. It uses the `llm-cyoa-dev` Compose project with separate database/media volumes and no tunnel or shared Docker network. It preserves data from the initial temporary development stack using the same project/volume names. Source mounts and Vite HMR make most edits immediately visible; rebuild after Python dependency changes. A fresh stack has no user/provider/model/configuration until you create them. `load_prompts` updates prompt records, including existing versions; run it deliberately.

```sh
docker compose -f compose.dev.yml logs -f web frontend gateway
docker compose -f compose.dev.yml down
```

`down` preserves data. Avoid `down -v` unless deliberately deleting the development database/media. Leave the existing `docker-compose.mac.yml` and `docker-compose.nvidia.yml` home deployments alone; do not run those to develop locally. Port 8000 may belong to another app; this project uses 8001.

Optional environment values are listed in `.env.example`; copy it to the ignored `.env` if needed. OpenRouter keys are entered in the local admin, not the frontend environment. TTS needs a separate `OPENAI_API_KEY`, global TTS enabled, and the adventure's `Enable text-to-speech` switch. The React chat supports text and rollback; TTS playback controls are pending and are not currently available in the UI. Native Whisper endpoint defaults to `http://host.docker.internal:10300/v1/audio/transcriptions`. See README-MAC.md for the older native Whisper setup; its shared-network/tunnel startup steps are not needed here.

## Updating an existing Mac home deployment

The tracked `compose.home-prod.yml` overlay upgrades the existing
`docker-compose.mac.yml` deployment to the React production image while retaining
its `cyoa-game-server` container name, shared network, database and Cloudflare tunnel.
This updater targets that existing home deployment; the separate `compose.prod.yml`
stack uses different service names and volumes and is not managed by this script.
The overlay requires Docker Compose 2.24.4 or newer for `!override`.

From a clean `main` checkout with the home deployment already running, its existing
`.env` credentials and `stargate-shared` network configured:

```sh
./scripts/update-production.py --check
./scripts/update-production.py
```

The updater compares `origin/main` with the revision label on the running container,
so manually pulling Git changes does not skip deployment. Legacy images without a
revision label are rebuilt once. It builds an isolated `origin/main` image with the
full commit revision label before stopping the app. It then
backs up the stopped container's `/app/db` and `/app/media`, including Docker volume
contents, under `backups/<timestamp>/`. Media is compressed as `media.tar.gz`.
Backups also contain release metadata, the prior overlay, and a private
`rollback.json` with the effective previous Compose configuration and credentials.
Keep these backups private. The updater does not delete old backups or images.

The app is recreated separately from starting it. If creation or launch fails and
Docker confirms the replacement container never started, the updater recreates the
previous image with its saved configuration. Build failures leave the app running;
backup failures restart the original container. If the replacement has started, or
Docker cannot establish its state, migrations may have modified the database and
recovery is deliberately manual: stop the failed app, restore the matching database
backup, then run the saved configuration and image together:

```sh
docker compose -p llm-cyoa -f backups/<timestamp>/rollback.json up -d --no-build --no-deps cyoa-game-server
```

Use the actual deployment project name if it differs from `llm-cyoa`. Restore the
complete backed-up database directory while the app is stopped, including SQLite
sidecar files; do not copy a database over a running service. Restore `media.tar.gz`
to the effective media mount if needed. Review `release.json` for the previous
commit/image. Restoring data discards writes made since that backup.

On success, the updater sets the local `home-production` image tag without editing
the tracked overlay, and checks the local page, frontend assets, Django configuration
and migration state. Verify a signed-in session at the public URL afterward. The
tunnel is left running. Use `--force` to rebuild an unchanged commit. The script
requires Python 3, Git and running Docker Desktop. For manual Compose operations,
include both `-f docker-compose.mac.yml -f compose.home-prod.yml`.

Updater regression tests run without contacting Docker or the deployed app:

```sh
python3 -m unittest discover -s scripts/tests -v
```

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

`compose.prod.yml` is a separate configuration, not a migration of the home deployment. It builds frontend assets into a Django image, runs Gunicorn with DEBUG off, serves built static assets through WhiteNoise, uses separate production volumes and publishes HTTP on loopback port 8002. It includes no Vite, application source mounts, debug port or tunnel. The host `cyoa_prompts/` directory is mounted writable so the administrator's Save to disk action persists versioned prompt files there. Required environment values fail validation if omitted.

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

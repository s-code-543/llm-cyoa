# React chat migration plan

Status: proposed implementation sequence, 2026-10-11. React implementation has not started.

## Scope and architecture

Replace the player chat experience first. Keep Django, SQLite, server-side LLM calls, authentication, Cloudflare Access integration, and the existing Django admin templates. The home page and login can remain Django pages during this migration. Preserve existing conversations and URLs. Keep engine/refusal-pipeline reorganization as a separate effort so frontend parity can be measured against current behavior.

Use React + TypeScript with Vite in a new frontend/ directory. Django remains the backend and session authority. This is a bounded authenticated app surface with no current SEO or server-rendering requirement, so a client application is appropriate. Do not introduce a second application server in production. A Django shell template mounts React; production assets come from a Vite manifest and the existing static-serving layer. Bundle CSS and dependencies rather than relying on CDNs.

In development, use the same browser origin for login, admin, APIs and chat through a local gateway. Route frontend assets and HMR to Vite, and Django paths to the backend. This avoids parallel cookie and CSRF policies. Explicitly configure the HMR WebSocket route. Keep the standalone legacy development copy usable while adding this integration.

Sources checked: https://react.dev/learn/build-a-react-app-from-scratch and https://vite.dev/guide/backend-integration.html . React describes the additional routing/data-fetching responsibilities of a standalone client; Vite documents traditional-backend integration using build manifests.

## 1. Establish a reproducible development baseline

- Commit a standalone dev Compose configuration, .env.example and root README, replacing the temporary /tmp configuration. Preserve project-specific DB/media volumes and loopback-only access; never start the home tunnel.
- Separate production settings/startup from dev: honor DEBUG/hosts/CSRF settings; use a production WSGI server and static/media handling; omit debugpy and source mounts in production. Do not deploy these changes to the hosted copy during development.
- Record baseline failures: two Ollama connection tests patch the utility module instead of the view's imported function. Fix mocks independently of engine behavior.
- Keep narrator rendering fix and per-adventure optional TTS as small preceding changes. Existing configurations migrate to TTS off; effective availability also depends on the global service and API key.

Exit: one documented local start command; separate disposable test command; fresh database bootstrap; existing configuration/data survive rebuilds.

## 2. Define the chat API contract

Inventory and document existing endpoints before changing them: new conversation, send, load/list/delete, rollback, STT upload/transcribe/status/discard, TTS generate/audio/status. Add a versioned API adapter for React while preserving legacy responses. Django REST Framework is not required merely to serve this client; reconsider if the API scope grows.

Return authoritative conversation state on both load and send: conversation/config identity, ordered messages with stable IDs, turn number/max, choices, inventory, game completion/blocking, and media capabilities/reasons. Currently reload parses prose again in the browser; stop duplicating that logic in the new client. Refusal/error responses must use consistent fields across live send and history reload. Do not expose provider credentials or private model context to the browser.

Use explicit JSON errors/status codes for expired sessions, validation, provider timeout, and provider failure. Preserve session cookies, CSRF protection and per-user ownership checks. Add request IDs and phase timings, linked to conversation/message/audit IDs; log response lengths and provider status, not authorization headers. Use existing audit records for full turn inspection.

Design turn submission deduplication before adding retries: a client-generated request ID must map to the same saved turn, including after browser disconnect. A timeout is not proof that a turn failed. Concurrent submissions require a server-side guard; the current synchronous workflow is a first milestone limitation. Do not automatically resend a paid generation request.

Exit: documented request/response types with backend contract tests, including ownership, disabled media, session expiry, blocked/game-ending turns, and rollback state.

## 3. Build the text chat vertical slice alongside legacy

Add an opt-in React route such as /chat/react/ while retaining /chat/ during validation. Reuse query parameters for conversation/config selection. Django renders a small shell with CSRF/bootstrap data; React owns its DOM completely. Do not mix Alpine and React inside the chat root.

Suggested layout:

    frontend/src/api/            typed client, errors, contracts
    frontend/src/features/chat/  page, transcript, composer, choices, state panel
    frontend/src/features/audio/ recorder/playback adapters and state machines
    frontend/src/components/    shared presentational components

Use TanStack Query for conversation server data and a small reducer for local interaction state. Keep composer draft and recording/playback state separate from persisted messages. Render Markdown through a maintained renderer with raw HTML disabled. The server remains authoritative for turn parsing, death rolls, corrections and game completion.

First slice: load existing adventure, render transcript, submit typed action, show waiting/error states, choose an action, preserve drafts after errors, and restore on reload. Mounting/reloading must never create duplicate conversations. Send is an explicit mutation, not a mount effect; React development checks must not trigger duplicate paid requests.

Exit: the current saved adventure renders correctly in React; a mocked-provider browser flow sends and reloads a turn; no duplicate POSTs; keyboard and narrow-screen layouts work.

## 4. Complete chat parity

- Conversation naming/list navigation and new-adventure selection through the existing home page.
- Rollback confirmation, transcript truncation, state refresh and audio-cache invalidation.
- Inventory, turn/choice display, blocked refusals, game endings and recoverable errors.
- Optional manual TTS, then STT recording/upload/transcription and voice conversation mode.
- Encapsulate existing audio utilities behind adapters initially; remove global DOM coupling incrementally. Model audio transitions explicitly (idle, recording, transcribing, submitting, generating audio, playing, error). TTS off must still allow microphone input. Release streams, revoke object URLs and cancel playback on unmount/conversation changes.
- Preserve PWA behavior deliberately: cache versioning, exclude authenticated API/private data, and ensure old service workers cannot keep serving stale chat bundles.

Exit: browser parity checklist passes for text, rollback, media-disabled, media-success/failure, expired session, provider timeout, reload, mobile and keyboard paths. Mock provider/audio services in routine tests; run paid/live smoke tests only deliberately.

## 5. Cut over and remove legacy chat

Make React the default /chat/ only after parity and production asset-build checks pass. Keep a temporary fallback route/feature switch for one review cycle. Verify direct conversation links, login redirects and admin links. Remove legacy Alpine chat code once fallback is retired; keep Django admin templates.

Use small reviewable commits/PRs per milestone. Work on codex/* branches, never commit on main, and never merge our own PRs. No hosted rollout without a separate deployment decision.

## Later engine work

React will improve UI structure but does not make the story engine more extensible. After chat/API behavior is covered, extract turn orchestration from chat_views.py into a service with explicit inputs/results. Unify refusal handling and judge stages behind a pipeline interface, separating classifiers, rewrites, comparisons, retry policy and audit events. Preserve current behavior first, then change policies intentionally. Streaming/background jobs follow that service boundary; do not add them during the initial text chat migration.

## First implementation milestone

Finish optional TTS and baseline fixes, then durable dev/prod configuration and the authoritative conversation-state contract. Next deliver a React text-chat slice. This gives us a working checkpoint before audio or pipeline changes.

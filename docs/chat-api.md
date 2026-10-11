# React player API v1

All paths below begin `/api/v1/chat/`. Session authentication is required (JSON 401 on expiry). Every POST requires Django's CSRF token. Responses are `Cache-Control: no-store`. No provider keys or raw judge/classifier context is returned.

| Method/path | Input | Result |
| --- | --- | --- |
| GET bootstrap | — | configurations with a storyteller model: id/name |
| GET conversations | — | current user's recent conversation ids/titles |
| POST conversations | config_id, request_id (UUID) | conversation snapshot; repeated identical creation returns same adventure |
| GET conversations/:id | — | owned conversation snapshot |
| POST conversations/:id/turns | message, request_id (UUID) | updated snapshot, request_id, elapsed_ms |
| POST conversations/:id/rollback | message_id, request_id (UUID) | updated snapshot, request_id, elapsed_ms |

Snapshot: `id`, `title`, `configuration` (id/name), ordered `messages` (id, role, content, created_at, is_error), `state` (turn, max_turns, choices, inventory, blocked, game_over), `capabilities.tts`, `pending_request_id`. State parsing happens on the server. Inventory uses the existing comma-separated `Inventory:` convention; richer structured engine output is later work.

Errors use `{ "error": { "code": "...", "message": "..." } }`. Mutation errors may also include a snapshot. Statuses: 400 invalid input, 401 session expiry, 404 unowned/missing adventure, 409 pending/conflicting/finished action, 502 provider failure, 504 provider timeout. Django's CSRF middleware may return HTML 403; the client handles this as an expired security token. No automatic POST retries.

A durable ChatSubmission row uniquely identifies a request within its conversation. A conditional DB constraint allows only one pending v1 mutation per conversation. Replaying the same request returns its recorded status with the current snapshot; a changed payload using the same ID gets 409. Completed/failed submissions never call the provider again. The legacy UI refuses mutations while a v1 action is pending; legacy-to-legacy concurrency is unchanged. Use one UI at a time for mutation tests.

A server crash can leave a submission pending with an uncertain generation result. It is intentionally not expired/retried automatically: inspect messages, audit log and server logs first. An operator may mark that specific submission failed only after confirming no worker is still processing it. Background jobs and a reconciliation UI are follow-up work. Provider errors in the existing engine may leave the attempted user action in history; the client preserves its draft and asks the player to reload and inspect before trying again.

The wrapper logs operation, conversation ID, request ID, total duration and status. Existing provider/pipeline logs show stages and response lengths; richer per-stage timing is deferred to the engine-service extraction.

Legacy endpoints remain in place for the original page:

- `/chat/api/new`, `/chat/api/send`, `/chat/api/conversation/:id`, `/chat/api/conversations`, `/chat/api/rollback`, `/chat/api/delete/:id`.
- `/api/stt/upload`, `/api/stt/transcribe`, `/api/stt/recording/:id`, `/api/stt/discard`.
- `/api/tts/generate` (requires conversation_id owned by the user and TTS enabled), `/api/tts/audio/:id`, `/api/tts/status/:id`.

STT/TTS retain their existing contracts in this text milestone. Audio asset ownership/retention and cancellation behavior must be reviewed before React speech parity/cutover; no raw media endpoint changes are implied by v1.

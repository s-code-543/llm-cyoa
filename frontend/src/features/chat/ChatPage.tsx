import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Transcript } from "./Transcript";
import { ActionComposer } from "./ActionComposer";
import {
  ApiError,
  request,
  type Configuration,
  type Conversation,
  type Envelope,
  type Message,
} from "../../api/chat";

const initial = new URLSearchParams(window.location.search);
export function ChatPage() {
  const cache = useQueryClient();
  const [id, setId] = useState(initial.get("conversation_id"));
  const [config, setConfig] = useState(initial.get("config") ?? "");
  const draftKey = `cyoa:react:draft:${id ?? "new"}`;
  const [draft, setDraft] = useState(
    () => localStorage.getItem(draftKey) ?? "",
  );
  const [needsReview, setNeedsReview] = useState(false);
  const [notice, setNotice] = useState("");
  const [rollbackTarget, setRollbackTarget] = useState<Message | null>(null);
  // Guard synchronously: a second click can arrive before React paints the pending state.
  const submitting = useRef(false);
  const bootstrap = useQuery({
    queryKey: ["bootstrap"],
    queryFn: () => request<{ configurations: Configuration[] }>("bootstrap"),
  });
  const conversation = useQuery({
    queryKey: ["conversation", id],
    enabled: Boolean(id),
    queryFn: () => request<Envelope>(`conversations/${id}`),
    refetchInterval: (query) =>
      query.state.data?.conversation.pending_request_id ? 2000 : false,
  });
  const game = conversation.data?.conversation;
  useEffect(() => {
    localStorage.setItem(draftKey, draft);
  }, [draftKey, draft]);
  useEffect(() => {
    const onBack = () => {
      const next = new URLSearchParams(window.location.search).get(
        "conversation_id",
      );
      setId(next);
      setDraft(localStorage.getItem(`cyoa:react:draft:${next ?? "new"}`) ?? "");
      setNotice("");
    };
    window.addEventListener("popstate", onBack);
    return () => window.removeEventListener("popstate", onBack);
  }, []);
  function accept(data: Envelope) {
    cache.setQueryData(["conversation", data.conversation.id], data);
  }
  function failed(error: Error) {
    if (error instanceof ApiError && error.conversation)
      accept({ conversation: error.conversation });
    setNotice(error.message);
    if (!(error instanceof ApiError) || error.status >= 500)
      setNeedsReview(true);
  }
  const create = useMutation({
    mutationFn: () => {
      const key = `cyoa:react:create:${config}`;
      const requestId = localStorage.getItem(key) ?? crypto.randomUUID();
      localStorage.setItem(key, requestId);
      return request<Envelope>("conversations", {
        config_id: Number(config),
        request_id: requestId,
      });
    },
    onSuccess(data) {
      localStorage.removeItem(`cyoa:react:create:${config}`);
      accept(data);
      setId(data.conversation.id);
      setDraft("");
      setNotice("");
      window.history.pushState(
        {},
        "",
        `/chat/react/?conversation_id=${data.conversation.id}`,
      );
    },
    onError: failed,
    onSettled() {
      submitting.current = false;
    },
  });
  const send = useMutation({
    mutationFn: (message: string) =>
      request<Envelope>(`conversations/${id}/turns`, {
        message,
        request_id: crypto.randomUUID(),
      }),
    onSuccess(data) {
      accept(data);
      setDraft("");
      setNotice("");
    },
    onError: failed,
    onSettled() {
      submitting.current = false;
    },
  });
  const rollback = useMutation({
    mutationFn: (messageId: number) =>
      request<Envelope>(`conversations/${id}/rollback`, {
        message_id: messageId,
        request_id: crypto.randomUUID(),
      }),
    onSuccess(data) {
      accept(data);
      setNotice("");
      setRollbackTarget(null);
    },
    onError: failed,
    onSettled() {
      submitting.current = false;
    },
  });
  const busy =
    create.isPending ||
    send.isPending ||
    rollback.isPending ||
    Boolean(game?.pending_request_id) ||
    needsReview;
  const finished = game?.state.blocked || game?.state.game_over;
  function submit(message: string) {
    if (!message.trim() || busy || finished || submitting.current) return;
    submitting.current = true;
    setNotice("");
    send.mutate(message);
  }
  const error =
    notice || conversation.error?.message || bootstrap.error?.message;
  const signedOut = [
    conversation.error,
    bootstrap.error,
    send.error,
    create.error,
  ].some(
    (e) => e instanceof ApiError && (e.status === 401 || e.status === 403),
  );
  return (
    <div className="app">
      <header className="masthead">
        <a className="wordmark" href="/">
          CYOA
        </a>
        <nav>
          <a href="/">Adventures</a>
        </nav>
      </header>
      <main className="workspace">
        <aside className="journal">
          <h1>{game?.title ?? "Your next adventure"}</h1>
          {game && (
            <>
              <div className="turn">
                <span>CHAPTER</span>
                <strong>
                  {game.state.turn.toString().padStart(2, "0")}{" "}
                  <small>/ {game.state.max_turns}</small>
                </strong>
                <progress
                  max={game.state.max_turns}
                  value={game.state.turn}
                  aria-label="Adventure progress"
                />
              </div>
              <div className="inventory">
                <h2>Inventory</h2>
                {game.state.inventory.length ? (
                  <ul>
                    {game.state.inventory.map((item, i) => (
                      <li key={i}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <p>Nothing collected yet.</p>
                )}
              </div>
              <a className="new-adventure" href="/chat/react/">
                ＋ New adventure
              </a>
            </>
          )}
        </aside>
        <section className="story-panel" aria-label="Adventure">
          <div className="story-heading">
            <span className="eyebrow">
              {game ? "THE ADVENTURE" : "BEGIN A STORY"}
            </span>
            <span className="connection">
              <i />
              {busy ? "Working" : "Ready"}
            </span>
          </div>
          {!id && (
            <div className="welcome">
              <span className="ornament">✦</span>
              <h2>
                A world waiting
                <br />
                for your first move.
              </h2>
              <p>
                Select an adventure. Start with the opening button or write your
                own first action.
              </p>
              <label htmlFor="configuration">Adventure</label>
              <select
                id="configuration"
                value={config}
                onChange={(e) => {
                  setConfig(e.target.value);
                }}
              >
                <option value="">Choose an adventure…</option>
                {bootstrap.data?.configurations.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
              <button
                className="primary"
                disabled={!config || busy}
                onClick={() => {
                  if (submitting.current) return;
                  submitting.current = true;
                  create.mutate();
                }}
              >
                {create.isPending ? "Opening…" : "Open adventure →"}
              </button>
            </div>
          )}
          {id && conversation.isPending && (
            <p className="empty" role="status">
              Opening your adventure…
            </p>
          )}
          {game && (
            <>
              <Transcript
                messages={game.messages}
                busy={busy}
                waiting={send.isPending}
                onRollback={setRollbackTarget}
              />
              {game.pending_request_id && (
                <p className="status" role="status">
                  An action is still running. Checking for its saved result…
                </p>
              )}
              {finished && (
                <div className="status">
                  {game.state.blocked
                    ? "The narrator could not continue. Start another adventure or roll back to an earlier turn."
                    : "This adventure has ended. Start a new one, or revisit an earlier turn."}
                </div>
              )}
              <ActionComposer
                opening={game.messages.length === 0}
                choices={game.state.choices}
                busy={busy}
                finished={Boolean(finished)}
                draft={draft}
                onDraft={setDraft}
                onSubmit={submit}
              />
            </>
          )}
          {error && (
            <div className="error-banner" role="alert">
              <p>{error}</p>
              {signedOut ? (
                <a
                  href={`/admin/login/?next=${encodeURIComponent(window.location.pathname + window.location.search)}`}
                >
                  Sign in again →
                </a>
              ) : (
                id && (
                  <button
                    className="text-button"
                    onClick={() => {
                      setNotice("");
                      void conversation.refetch().then((result) => {
                        if (result.isSuccess) setNeedsReview(false);
                      });
                    }}
                  >
                    Reload saved adventure
                  </button>
                )
              )}
              {!id && needsReview && (
                <button
                  className="text-button"
                  onClick={() => window.location.reload()}
                >
                  Reload and try opening again
                </button>
              )}
            </div>
          )}
        </section>
      </main>
      {rollbackTarget && (
        <div className="modal-backdrop">
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="rollback-title"
            className="modal"
          >
            <h2 id="rollback-title">Take another path?</h2>
            <p>
              This removes all messages after this narrator turn. Your adventure
              will continue from here.
            </p>
            <div>
              <button
                autoFocus
                onClick={() => setRollbackTarget(null)}
                disabled={busy}
              >
                Keep playing
              </button>
              <button
                className="primary"
                disabled={busy}
                onClick={() => {
                  if (submitting.current) return;
                  submitting.current = true;
                  rollback.mutate(rollbackTarget.id);
                }}
              >
                Roll back
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

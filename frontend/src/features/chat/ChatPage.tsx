import { Toggle } from "../../components/Toggle";
import { useEffect, useRef, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Chip,
  Modal,
  ProgressBar,
  Radio,
  RadioGroup,
} from "@heroui/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { DebugPanel } from "./DebugPanel";
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

export function ChatPage() {
  const [initial] = useState(() => new URLSearchParams(window.location.search));
  const cache = useQueryClient();
  const [id, setId] = useState(initial.get("conversation_id"));
  const [config, setConfig] = useState(initial.get("config") ?? "");
  const draftKey = `cyoa:react:draft:${id ?? "new"}`;
  const [draft, setDraft] = useState(
    () => localStorage.getItem(draftKey) ?? "",
  );
  const [needsReview, setNeedsReview] = useState(false);
  const [notice, setNotice] = useState("");
  const [debugEnabled, setDebugEnabled] = useState(
    () =>
      initial.get("debug") === "true" ||
      localStorage.getItem("cyoa:debug") === "true",
  );
  const [debugTarget, setDebugTarget] = useState<number | "failure" | null>(
    null,
  );
  const [inventoryOpen, setInventoryOpen] = useState(false);
  const [rollbackTarget, setRollbackTarget] = useState<Message | null>(null);
  // Guard synchronously: a second click can arrive before React paints the pending state.
  const submitting = useRef(false);
  const bootstrap = useQuery({
    queryKey: ["bootstrap"],
    queryFn: () =>
      request<{ configurations: Configuration[]; debug_allowed?: boolean }>(
        "bootstrap",
      ),
  });
  const conversation = useQuery({
    queryKey: ["conversation", id],
    enabled: Boolean(id),
    queryFn: () => request<Envelope>(`conversations/${id}`),
    refetchInterval: (query) =>
      query.state.data?.conversation.pending_request_id ? 2000 : false,
  });
  const debugAllowed = Boolean(bootstrap.data?.debug_allowed);
  useEffect(() => {
    setDebugTarget(null);
  }, [id]);
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
        `/chat?conversation_id=${data.conversation.id}`,
      );
    },
    onError: failed,
    onSettled() {
      submitting.current = false;
    },
  });
  const autoCreated = useRef(false);
  useEffect(() => {
    if (id || autoCreated.current) return;
    autoCreated.current = true;
    if (config) {
      submitting.current = true;
      create.mutate();
    } else {
      window.location.replace("/");
    }
  }, []);
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
  const readOnly = Boolean(game?.read_only);
  const finished = game?.state.blocked || game?.state.game_over;
  function submit(message: string) {
    if (!message.trim() || readOnly || busy || finished || submitting.current)
      return;
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
    <div>
      <main
        className={`mx-auto flex min-h-[calc(100dvh-3.75rem)] max-w-7xl flex-col gap-1.5 px-2 pt-1.5 lg:grid lg:min-h-0 lg:grid-cols-[300px_minmax(0,1fr)] lg:items-start lg:gap-8 lg:px-4 lg:py-8 `}
      >
        <aside className="flex flex-col gap-1.5 lg:sticky lg:top-24 lg:gap-4">
          <Card
            className={`gap-0 bg-linear-to-br from-brand to-brand-coral text-white max-lg:rounded-2xl max-lg:py-2 ${game ? "max-lg:hidden" : ""}`}
          >
            <Card.Header>
              <p className="hidden text-xs font-bold tracking-[0.2em] opacity-80 lg:block">
                {game
                  ? readOnly
                    ? "INSPECTING CHAT"
                    : "NOW PLAYING"
                  : "BEGIN A STORY"}
              </p>
              <h1 className="font-story text-lg leading-tight [overflow-wrap:anywhere] lg:mt-1 lg:text-3xl">
                {game?.title ?? "Your next adventure"}
              </h1>
            </Card.Header>
          </Card>
          {game && (
            <>
              <Card className="max-lg:gap-0 max-lg:rounded-2xl max-lg:py-1.5">
                <Card.Content className="gap-1 max-lg:px-3 lg:gap-3">
                  <div className="flex items-baseline justify-between gap-2">
                    <p className="min-w-0 flex-1 truncate font-story text-sm font-bold lg:hidden">
                      {game.title}
                    </p>
                    <span className="text-xs font-bold tracking-[0.2em] text-muted max-lg:hidden">
                      CHAPTER
                    </span>
                    <strong className="font-story text-lg text-grape lg:text-3xl">
                      {game.state.turn.toString().padStart(2, "0")}
                      <small className="text-sm text-muted lg:text-base">
                        {" "}
                        / {game.state.max_turns}
                      </small>
                    </strong>
                  </div>
                  <ProgressBar
                    aria-label="Adventure progress"
                    minValue={0}
                    maxValue={game.state.max_turns}
                    value={game.state.turn}
                    color="accent"
                    size="sm"
                  >
                    <ProgressBar.Track>
                      <ProgressBar.Fill />
                    </ProgressBar.Track>
                  </ProgressBar>
                </Card.Content>
              </Card>
              <Card className="max-lg:gap-0 max-lg:rounded-2xl max-lg:py-0">
                <button
                  type="button"
                  className="flex items-center justify-between px-3 py-1.5 text-left text-sm font-bold lg:hidden"
                  aria-expanded={inventoryOpen}
                  onClick={() => setInventoryOpen((open) => !open)}
                >
                  <span>🎒 Inventory ({game.state.inventory.length})</span>
                  <span aria-hidden>{inventoryOpen ? "▴" : "▾"}</span>
                </button>
                <Card.Header className="hidden lg:flex">
                  <Card.Title className="text-base">🎒 Inventory</Card.Title>
                </Card.Header>
                <Card.Content
                  className={inventoryOpen ? "max-lg:pb-3" : "max-lg:hidden"}
                >
                  {game.state.inventory.length ? (
                    <ul className="flex flex-wrap gap-2">
                      {game.state.inventory.map((item, i) => (
                        <li key={i}>
                          <Chip
                            color={
                              (
                                [
                                  "accent",
                                  "success",
                                  "warning",
                                  "danger",
                                ] as const
                              )[i % 4]
                            }
                          >
                            {item}
                          </Chip>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-sm text-muted">Nothing collected yet.</p>
                  )}
                </Card.Content>
              </Card>
              <a
                href="/"
                className="hidden rounded-full border-2 border-dashed border-grape/40 px-4 py-3 text-center text-sm font-bold text-grape transition hover:bg-grape-soft lg:block"
              >
                ＋ New adventure
              </a>
            </>
          )}
          {debugAllowed && (
            <Toggle
              checked={debugEnabled}
              onChange={(checked) => {
                setDebugEnabled(checked);
                localStorage.setItem("cyoa:debug", String(checked));
                if (!checked) setDebugTarget(null);
              }}
            >
              Debug mode
            </Toggle>
          )}
          {debugAllowed && debugEnabled && game && (
            <button
              type="button"
              className="p-2 text-sm underline"
              onClick={() => setDebugTarget("failure")}
            >
              Inspect latest failed attempt
            </button>
          )}
        </aside>
        <section
          className="flex min-w-0 flex-1 flex-col gap-3 lg:gap-6"
          aria-label="Adventure"
        >
          <div
            className={`items-center justify-between ${game ? "hidden lg:flex" : "flex"}`}
          >
            <span className="text-xs font-bold tracking-[0.2em] text-grape">
              {game ? "THE ADVENTURE" : "BEGIN A STORY"}
            </span>
            <Chip color={busy ? "warning" : "success"} size="sm">
              {busy ? "Working" : "Ready"}
            </Chip>
          </div>
          {!id && create.isPending && (
            <p className="text-muted" role="status">
              Opening your adventure…
            </p>
          )}
          {id && conversation.isPending && (
            <p className="text-muted" role="status">
              Opening your adventure…
            </p>
          )}
          {game && (
            <>
              {readOnly && (
                <Alert status="accent" role="status">
                  <Alert.Content>
                    <Alert.Description>
                      Inspecting {game.owner}’s chat. This view is read-only.
                    </Alert.Description>
                    <div className="mt-2 flex gap-3">
                      <a href="/manage/chats" className="underline">
                        All chats
                      </a>
                      <button
                        type="button"
                        className="underline"
                        disabled={conversation.isFetching}
                        onClick={() => {
                          void conversation.refetch();
                          void cache.invalidateQueries({
                            queryKey: ["turn-debug", id],
                          });
                        }}
                      >
                        Refresh chat
                      </button>
                    </div>
                  </Alert.Content>
                </Alert>
              )}
              <Transcript
                messages={game.messages}
                busy={busy}
                waiting={send.isPending}
                onRollback={setRollbackTarget}
                readOnly={readOnly}
                debugEnabled={debugAllowed && debugEnabled}
                onDebug={(message) => setDebugTarget(message.id)}
              />
              {game.pending_request_id && (
                <Alert status="warning" role="status">
                  <Alert.Content>
                    <Alert.Description>
                      An action is still running. Checking for its saved result…
                    </Alert.Description>
                  </Alert.Content>
                </Alert>
              )}
              {finished && !readOnly && (
                <Alert status="accent">
                  <Alert.Content>
                    <Alert.Description>
                      {game.state.blocked
                        ? "The narrator could not continue. Start another adventure or roll back to an earlier turn."
                        : "This adventure has ended. Start a new one, or revisit an earlier turn."}
                    </Alert.Description>
                  </Alert.Content>
                </Alert>
              )}
              {!readOnly && (
                <ActionComposer
                  opening={game.messages.length === 0}
                  choices={game.state.choices}
                  busy={busy}
                  finished={Boolean(finished)}
                  draft={draft}
                  onDraft={setDraft}
                  onSubmit={submit}
                />
              )}
            </>
          )}
          {error && (
            <Alert status="danger" role="alert">
              <Alert.Content>
                <Alert.Description>{error}</Alert.Description>
                <div className="mt-2 flex gap-2">
                  {signedOut ? (
                    <a
                      className="font-bold underline"
                      href={`/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`}
                    >
                      Sign in again →
                    </a>
                  ) : (
                    id && (
                      <Button
                        size="sm"
                        variant="secondary"
                        onPress={() => {
                          setNotice("");
                          void conversation.refetch().then((result) => {
                            if (result.isSuccess) setNeedsReview(false);
                          });
                        }}
                      >
                        Reload saved adventure
                      </Button>
                    )
                  )}
                  {!id && needsReview && (
                    <Button
                      size="sm"
                      variant="secondary"
                      onPress={() => window.location.reload()}
                    >
                      Reload and try opening again
                    </Button>
                  )}
                </div>
              </Alert.Content>
            </Alert>
          )}
        </section>
        {debugAllowed && debugEnabled && debugTarget !== null && id && (
          <DebugPanel
            key={`${id}:${debugTarget}`}
            conversationId={id}
            messageId={debugTarget}
            onClose={() => setDebugTarget(null)}
          />
        )}
      </main>
      <Modal
        isOpen={Boolean(rollbackTarget)}
        onOpenChange={(open) => {
          if (!open && !busy) setRollbackTarget(null);
        }}
      >
        <Modal.Backdrop>
          <Modal.Container>
            <Modal.Dialog className="sm:max-w-md">
              {rollbackTarget && (
                <>
                  <Modal.Header>
                    <Modal.Heading>Take another path?</Modal.Heading>
                  </Modal.Header>
                  <Modal.Body>
                    <p>
                      This removes all messages after this narrator turn. Your
                      adventure will continue from here.
                    </p>
                  </Modal.Body>
                  <Modal.Footer>
                    <Button
                      variant="secondary"
                      isDisabled={busy}
                      onPress={() => setRollbackTarget(null)}
                    >
                      Keep playing
                    </Button>
                    <Button
                      variant="primary"
                      isDisabled={busy}
                      onPress={() => {
                        if (submitting.current) return;
                        submitting.current = true;
                        rollback.mutate(rollbackTarget.id);
                      }}
                    >
                      Roll back
                    </Button>
                  </Modal.Footer>
                </>
              )}
            </Modal.Dialog>
          </Modal.Container>
        </Modal.Backdrop>
      </Modal>
    </div>
  );
}

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
        `/chat?conversation_id=${data.conversation.id}`,
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
    <div>
      <main className="mx-auto grid max-w-7xl items-start gap-8 px-4 py-8 lg:grid-cols-[300px_minmax(0,1fr)]">
        <aside className="flex flex-col gap-4 lg:sticky lg:top-24">
          <Card className="text-white bg-linear-to-br from-brand to-brand-coral text-white">
            <Card.Header>
              <p className="text-xs font-bold tracking-[0.2em] opacity-80">
                {game ? "NOW PLAYING" : "BEGIN A STORY"}
              </p>
              <h1 className="mt-1 font-story text-3xl leading-tight [overflow-wrap:anywhere]">
                {game?.title ?? "Your next adventure"}
              </h1>
            </Card.Header>
          </Card>
          {game && (
            <>
              <Card>
                <Card.Content className="gap-3">
                  <div className="flex items-baseline justify-between">
                    <span className="text-xs font-bold tracking-[0.2em] text-muted">
                      CHAPTER
                    </span>
                    <strong className="font-story text-3xl text-grape">
                      {game.state.turn.toString().padStart(2, "0")}
                      <small className="text-base text-muted">
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
                  >
                    <ProgressBar.Track>
                      <ProgressBar.Fill />
                    </ProgressBar.Track>
                  </ProgressBar>
                </Card.Content>
              </Card>
              <Card>
                <Card.Header>
                  <Card.Title className="text-base">🎒 Inventory</Card.Title>
                </Card.Header>
                <Card.Content>
                  {game.state.inventory.length ? (
                    <ul className="flex flex-wrap gap-2">
                      {game.state.inventory.map((item, i) => (
                        <li key={i}>
                          <Chip
                            color={(["accent", "success", "warning", "danger"] as const)[i % 4]}
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
                href="/chat"
                className="rounded-full border-2 border-dashed border-grape/40 px-4 py-3 text-center text-sm font-bold text-grape transition hover:bg-grape-soft"
              >
                ＋ New adventure
              </a>
            </>
          )}
        </aside>
        <section className="flex min-w-0 flex-col gap-6" aria-label="Adventure">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold tracking-[0.2em] text-grape">
              {game ? "THE ADVENTURE" : "BEGIN A STORY"}
            </span>
            <Chip color={busy ? "warning" : "success"} size="sm">
              {busy ? "Working" : "Ready"}
            </Chip>
          </div>
          {!id && (
            <Card className="p-2">
              <Card.Header className="items-center text-center">
                <span className="text-4xl text-sun">✦</span>
                <Card.Title className="font-story text-3xl">
                  A world waiting for your first move.
                </Card.Title>
                <Card.Description>
                  Pick an adventure, then open it and make your first move.
                </Card.Description>
              </Card.Header>
              <Card.Content className="gap-5">
                <RadioGroup
                  aria-label="Adventure"
                  value={config}
                  onChange={setConfig}
                  className="grid gap-3 sm:grid-cols-2"
                >
                  {bootstrap.data?.configurations.map((c, i) => (
                    <Radio
                      key={c.id}
                      value={String(c.id)}
                      className={`rounded-2xl border-2 p-4 transition data-[selected=true]:border-grape data-[selected=true]:shadow-lg ${
                        ["bg-grape-soft", "bg-coral-soft", "bg-mint-soft", "bg-sun-soft"][i % 4]
                      } border-transparent`}
                    >
                      <Radio.Content>
                        <Radio.Control>
                          <Radio.Indicator />
                        </Radio.Control>
                        <span className="font-bold">{c.name}</span>
                      </Radio.Content>
                    </Radio>
                  ))}
                </RadioGroup>
                <Button
                  variant="primary"
                  size="lg"
                  className="self-center text-white bg-linear-to-r from-brand to-brand-coral px-8"
                  isDisabled={!config || busy}
                  onPress={() => {
                    if (submitting.current) return;
                    submitting.current = true;
                    create.mutate();
                  }}
                >
                  {create.isPending ? "Opening…" : "Open adventure →"}
                </Button>
              </Card.Content>
            </Card>
          )}
          {id && conversation.isPending && (
            <p className="text-muted" role="status">
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
                <Alert status="warning" role="status">
                  <Alert.Content>
                    <Alert.Description>
                      An action is still running. Checking for its saved result…
                    </Alert.Description>
                  </Alert.Content>
                </Alert>
              )}
              {finished && (
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

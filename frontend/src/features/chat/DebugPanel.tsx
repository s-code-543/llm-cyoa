import { useQuery } from "@tanstack/react-query";
import { request } from "../../api/chat";
type Step = {
  index: number;
  type: string;
  status: string;
  elapsed_ms?: number;
  error?: string;
  reason?: string;
  input: unknown;
  output: unknown;
  configuration: unknown;
  model_requests: unknown[];
};
export function DebugPanel({
  conversationId,
  messageId,
  onClose,
}: {
  conversationId: string;
  messageId: number | "failure";
  onClose: () => void;
}) {
  const query = useQuery({
    queryKey: ["turn-debug", conversationId, messageId],
    queryFn: () =>
      request<{ steps: Step[] | null; status: string; error?: string }>(
        `conversations/${conversationId}/debug${messageId === "failure" ? "" : `?message_id=${messageId}`}`,
      ),
  });
  const data = query.data;
  return (
    <aside
      aria-label="Pipeline debug"
      className="min-w-0 rounded-2xl border border-grape/20 bg-surface p-4 lg:sticky lg:top-24 lg:max-h-[calc(100dvh-7rem)] lg:overflow-y-auto"
    >
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-bold">Pipeline debug</h2>
        <button type="button" onClick={onClose} className="underline">
          Close debug panel
        </button>
      </div>
      <p className="my-2 text-sm text-muted">
        {messageId === "failure"
          ? "Latest failed attempt"
          : `Narrator response #${messageId}`}
      </p>
      {query.isPending && <p role="status">Loading pipeline…</p>}
      {query.error && (
        <div role="alert">
          <p>{query.error.message}</p>
          <button onClick={() => void query.refetch()}>Retry</button>
        </div>
      )}
      {data && (
        <>
          <p className="mb-3 text-sm">
            {data.status} · {data.steps?.length ?? 0} steps
          </p>
          {data.error && (
            <p role="alert" className="text-danger">
              {data.error}
            </p>
          )}
          {!data.steps?.length && (
            <p>
              No detailed trace was recorded. Detailed traces are available for
              turns run after this update.
            </p>
          )}
          {data.steps?.map((step) => (
            <details
              key={step.index}
              className="mb-3 rounded-xl border border-grape/20 p-3"
              open={step.status === "failed"}
            >
              <summary className="cursor-pointer text-sm font-bold">
                {step.index + 1}. {step.type} · {step.status}
                {step.elapsed_ms !== undefined && ` · ${step.elapsed_ms} ms`}
              </summary>
              {step.error && <p className="my-2 text-danger">{step.error}</p>}
              {step.reason && <p>{step.reason}</p>}
              {(
                [
                  ["Configuration", step.configuration],
                  ["Input", step.input],
                  ["Output", step.output],
                  ["Model calls", step.model_requests],
                ] as const
              ).map(([label, value]) => (
                <details key={label} className="mt-3">
                  <summary className="cursor-pointer text-sm">{label}</summary>
                  <pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-grape/5 p-3 text-xs">
                    {JSON.stringify(value, null, 2)}
                  </pre>
                </details>
              ))}
            </details>
          ))}
        </>
      )}
    </aside>
  );
}

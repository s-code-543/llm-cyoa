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
function TraceValue({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (typeof value === "string") {
    return (
      <pre className="trace-text">
        <code>{value || "(empty string)"}</code>
      </pre>
    );
  }
  if (value === null || typeof value !== "object") {
    return (
      <code className="trace-scalar">
        {value === undefined ? "Not recorded" : JSON.stringify(value)}
      </code>
    );
  }
  const entries = Object.entries(value);
  if (!entries.length)
    return (
      <p className="trace-empty">
        {Array.isArray(value) ? "No entries" : "No fields"}
      </p>
    );
  return (
    <div className="trace-fields">
      {entries.map(([key, child]) => {
        const nested = child !== null && typeof child === "object";
        const label = Array.isArray(value) ? `Item ${Number(key) + 1}` : key;
        return (
          <div key={key} className="trace-field">
            {nested ? (
              <details open={depth < 1}>
                <summary>
                  {label}
                  <span className="trace-count">
                    {Object.keys(child).length}{" "}
                    {Array.isArray(child) ? "items" : "fields"}
                  </span>
                </summary>
                <TraceValue value={child} depth={depth + 1} />
              </details>
            ) : (
              <>
                <div className="trace-key">{label}</div>
                <TraceValue value={child} depth={depth + 1} />
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}

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
    <aside aria-label="Pipeline debug" className="pipeline-debug">
      <div className="trace-heading">
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
              className="trace-step"
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
                  <div className="trace-section">
                    <TraceValue value={value} />
                  </div>
                  <details className="trace-raw">
                    <summary>Raw JSON</summary>
                    <pre className="trace-text">
                      <code>{JSON.stringify(value, null, 2)}</code>
                    </pre>
                  </details>
                </details>
              ))}
            </details>
          ))}
        </>
      )}
    </aside>
  );
}

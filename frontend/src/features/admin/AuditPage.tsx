import { useState } from "react";
import { Link, useParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { clearAudit, getAudit, getAuditEntry, type AuditSummary } from "../../api/admin";

const when = (iso: string) => new Date(iso).toLocaleString();

export function AuditTable({ logs }: { logs: AuditSummary[] }) {
  if (!logs.length) return <p className="empty">No audit entries.</p>;
  return (
    <table className="table">
      <thead>
        <tr><th>When</th><th>Result</th><th>Original text</th></tr>
      </thead>
      <tbody>
        {logs.map((log) => (
          <tr key={log.id}>
            <td><Link to={`/manage/audit/${log.id}`}>{when(log.timestamp)}</Link></td>
            <td>
              <span className={`badge ${log.was_refusal ? "refusal" : log.was_modified ? "modified" : ""}`}>
                {log.was_refusal ? "Refusal" : log.was_modified ? "Modified" : "Unchanged"}
              </span>
            </td>
            <td>{log.preview}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function AuditPage() {
  const cache = useQueryClient();
  const [modifiedOnly, setModifiedOnly] = useState(false);
  const audit = useQuery({
    queryKey: ["admin", "audit", modifiedOnly],
    queryFn: () => getAudit(modifiedOnly),
  });
  const clear = useMutation({
    mutationFn: clearAudit,
    onSuccess: () => cache.invalidateQueries({ queryKey: ["admin"] }),
  });
  return (
    <>
      <h1>Audit log</h1>
      <div className="toolbar">
        <label>
          <input
            type="checkbox"
            checked={modifiedOnly}
            onChange={(event) => setModifiedOnly(event.target.checked)}
          />{" "}
          Modified only
        </label>
        <button
          type="button"
          className="danger"
          disabled={clear.isPending}
          onClick={() => {
            if (window.confirm("Delete every audit log entry? This cannot be undone."))
              clear.mutate();
          }}
        >
          Clear log
        </button>
      </div>
      {clear.error && <p role="alert">{clear.error.message}</p>}
      {audit.isPending && <p className="empty" role="status">Loading…</p>}
      {audit.error && <p className="empty" role="alert">{audit.error.message}</p>}
      {audit.data && <AuditTable logs={audit.data.logs} />}
    </>
  );
}

export function AuditDetailPage() {
  const id = Number(useParams().id);
  const entry = useQuery({ queryKey: ["admin", "audit", "entry", id], queryFn: () => getAuditEntry(id) });
  if (entry.isPending) return <p className="empty" role="status">Loading…</p>;
  if (entry.error) return <p className="empty" role="alert">{entry.error.message}</p>;
  const log = entry.data;
  return (
    <>
      <p><Link to="/manage/audit">← Back to audit log</Link></p>
      <h1>Audit entry #{log.id}</h1>
      <p>{when(log.timestamp)} · {log.was_refusal ? "Refusal" : log.was_modified ? "Modified" : "Unchanged"}</p>
      <h2>Original</h2>
      <pre className="textblock">{log.original_text}</pre>
      <h2>Final</h2>
      <pre className="textblock">{log.refined_text}</pre>
      {log.classifier_response && (
        <>
          <h2>Classifier response</h2>
          <pre className="textblock">{log.classifier_response}</pre>
        </>
      )}
      <p>Judge prompt: {log.prompt_used ?? "—"}</p>
      <p>Correction prompt: {log.correction_prompt_used ?? "—"}</p>
      <h2>Details</h2>
      <pre className="textblock">{JSON.stringify(log.details, null, 2)}</pre>
    </>
  );
}

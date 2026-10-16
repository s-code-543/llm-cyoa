import { useState } from "react";
import { Link, useParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  browseModels,
  deleteModel,
  getModels,
  importModels,
  removeModels,
  syncModels,
} from "../../api/admin";
import { Failure, Loading } from "./ui";

export function ModelListPage() {
  const cache = useQueryClient();
  const models = useQuery({ queryKey: ["admin", "models"], queryFn: getModels });
  const [search, setSearch] = useState("");
  const [provider, setProvider] = useState("");
  const remove = useMutation({
    mutationFn: deleteModel,
    onSuccess: () => cache.invalidateQueries({ queryKey: ["admin", "models"] }),
  });
  if (models.isPending) return <Loading />;
  if (models.error) return <Failure error={models.error} />;
  const needle = search.trim().toLowerCase();
  const rows = models.data.models.filter(
    (m) =>
      (!provider || String(m.provider_id) === provider) &&
      (!needle || `${m.name} ${m.model_identifier}`.toLowerCase().includes(needle)),
  );
  return (
    <>
      <h1>Models</h1>
      <div className="toolbar">
        <input aria-label="Search models" placeholder="Search" value={search} onChange={(e) => setSearch(e.target.value)} />
        <select aria-label="Provider" value={provider} onChange={(e) => setProvider(e.target.value)}>
          <option value="">All providers</option>
          {models.data.providers.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <Link to="/manage/providers">Import from a provider →</Link>
      </div>
      <Failure error={remove.error} />
      {rows.length === 0 ? (
        <p className="empty">No models match.</p>
      ) : (
        <table className="table">
          <thead><tr><th>Name</th><th>Identifier</th><th>Provider</th><th /></tr></thead>
          <tbody>
            {rows.map((m) => (
              <tr key={m.id}>
                <td>{m.name}{m.image_generation ? " · Image generation" : ""}{m.is_available ? "" : " (unavailable)"}</td>
                <td>{m.model_identifier}</td>
                <td>{m.provider_name}</td>
                <td>
                  <button
                    type="button"
                    className="danger"
                    onClick={() => window.confirm(`Delete ${m.name}?`) && remove.mutate(m.id)}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}

export function ModelBrowserPage() {
  const id = Number(useParams().id);
  const cache = useQueryClient();
  const remote = useQuery({ queryKey: ["admin", "browse", id], queryFn: () => browseModels(id) });
  const [selected, setSelected] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [notice, setNotice] = useState("");
  const refresh = (result: { message: string }) => {
    setNotice(result.message);
    setSelected([]);
    cache.invalidateQueries({ queryKey: ["admin"] });
  };
  const doImport = useMutation({ mutationFn: () => importModels(id, selected), onSuccess: refresh });
  const doRemove = useMutation({ mutationFn: () => removeModels(id, selected), onSuccess: refresh });
  const doSync = useMutation({ mutationFn: () => syncModels(id), onSuccess: refresh });
  if (remote.isPending) return <Loading />;
  if (remote.error) return <Failure error={remote.error} />;
  const needle = search.trim().toLowerCase();
  const shown = remote.data.models.filter((m) => !needle || `${m.name} ${m.id}`.toLowerCase().includes(needle));
  const toggle = (modelId: string) =>
    setSelected((cur) => (cur.includes(modelId) ? cur.filter((x) => x !== modelId) : [...cur, modelId]));
  const busy = doImport.isPending || doRemove.isPending || doSync.isPending;
  return (
    <>
      <h1>Models from {remote.data.provider.name}</h1>
      <div className="toolbar">
        <input aria-label="Search available models" placeholder="Search" value={search} onChange={(e) => setSearch(e.target.value)} />
        <button type="button" disabled={busy || !selected.length} onClick={() => doImport.mutate()}>Import selected</button>
        <button type="button" disabled={busy || !selected.length} onClick={() => doRemove.mutate()}>Remove selected</button>
        <button type="button" disabled={busy} onClick={() => doSync.mutate()}>Sync with provider</button>
      </div>
      {notice && <p role="status">{notice}</p>}
      <Failure error={doImport.error ?? doRemove.error ?? doSync.error} />
      {shown.length === 0 ? (
        <p className="empty">No models available from this provider.</p>
      ) : (
        <ul className="plain">
          {shown.map((m) => (
            <li key={m.id}>
              <label>
                <input type="checkbox" checked={selected.includes(m.id)} onChange={() => toggle(m.id)} />{" "}
                <strong>{m.name}</strong>{m.image_generation ? " · Image generation" : ""} <code>{m.id}</code>{m.imported ? " ✓ imported" : ""}
              </label>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

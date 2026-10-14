import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createProvider,
  deleteProvider,
  getProviders,
  testProvider,
  updateProvider,
  type Provider,
} from "../../api/admin";
import { Failure, Field, Loading, fieldErrors } from "./ui";

const key = ["admin", "providers"];

export function ProviderListPage() {
  const providers = useQuery({ queryKey: key, queryFn: getProviders });
  if (providers.isPending) return <Loading />;
  if (providers.error) return <Failure error={providers.error} />;
  return (
    <>
      <h1>Providers</h1>
      <p><Link to="/manage/providers/new">Add provider</Link></p>
      <table className="table">
        <thead>
          <tr><th>Name</th><th>Type</th><th>Key</th><th>Models</th><th>Last test</th><th /></tr>
        </thead>
        <tbody>
          {providers.data.providers.map((p) => (
            <tr key={p.id}>
              <td>{p.name}</td>
              <td>{p.provider_type}</td>
              <td>{p.has_api_key ? `••••${p.api_key_hint}` : "none"}</td>
              <td>{p.model_count}</td>
              <td>{p.test_status || "never"}</td>
              <td>
                <Link to={`/manage/providers/${p.id}`}>Edit</Link>{" · "}
                <Link to={`/manage/providers/${p.id}/models`}>Browse models</Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function ProviderForm({ provider, types }: { provider?: Provider; types: { value: string; label: string }[] }) {
  const navigate = useNavigate();
  const cache = useQueryClient();
  const [name, setName] = useState(provider?.name ?? "");
  const [type, setType] = useState(provider?.provider_type ?? "openrouter");
  const [baseUrl, setBaseUrl] = useState(provider?.base_url ?? "");
  const [apiKey, setApiKey] = useState("");
  const [clear, setClear] = useState(false);
  const [notice, setNotice] = useState("");
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);

  const input = { name, provider_type: type, base_url: baseUrl, api_key: apiKey, clear_api_key: clear };
  const save = useMutation({
    mutationFn: () => (provider ? updateProvider(provider.id, input) : createProvider(input)),
    onSuccess: (saved) => {
      cache.invalidateQueries({ queryKey: key });
      setApiKey("");
      setClear(false);
      if (provider) setNotice("Saved");
      else navigate(`/manage/providers/${saved.id}`);
    },
  });
  const test = useMutation({
    mutationFn: () =>
      testProvider({ provider_id: provider?.id, provider_type: type, base_url: baseUrl, api_key: apiKey }),
    onSuccess: (result) => {
      setTestResult(result);
      cache.invalidateQueries({ queryKey: key });
    },
  });
  const remove = useMutation({
    mutationFn: () => deleteProvider(provider!.id),
    onSuccess: () => {
      cache.invalidateQueries({ queryKey: key });
      cache.invalidateQueries({ queryKey: ["admin", "models"] });
      navigate("/manage/providers");
    },
  });
  const errors = fieldErrors(save.error);
  const failure = test.error ?? remove.error ?? (Object.keys(errors).length ? null : save.error);

  return (
    <form
      className="form"
      onSubmit={(event) => {
        event.preventDefault();
        setNotice("");
        save.mutate();
      }}
    >
      <Field label="Name" error={errors.name}>
        <input value={name} onChange={(e) => setName(e.target.value)} required />
      </Field>
      <Field label="Type" error={errors.provider_type}>
        <select value={type} onChange={(e) => setType(e.target.value)}>
          {types.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
        </select>
      </Field>
      <Field label="Base URL">
        <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="Only needed for Ollama" />
      </Field>
      <Field label="API key">
        <input
          type="password"
          autoComplete="off"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder={provider?.has_api_key ? `Stored (ends ${provider.api_key_hint}); leave blank to keep` : ""}
        />
      </Field>
      {provider?.has_api_key && (
        <label>
          <input type="checkbox" checked={clear} onChange={(e) => setClear(e.target.checked)} /> Remove stored key
        </label>
      )}
      {notice && <p role="status">{notice}</p>}
      {testResult && (
        <p role={testResult.success ? "status" : "alert"}>
          {testResult.success ? "Connection OK: " : "Connection failed: "}{testResult.message}
        </p>
      )}
      <Failure error={failure} />
      <div className="toolbar">
        <button type="submit" disabled={save.isPending}>{provider ? "Save changes" : "Create provider"}</button>
        <button type="button" disabled={test.isPending} onClick={() => test.mutate()}>Test connection</button>
        {provider && (
          <button
            type="button"
            className="danger"
            onClick={() => window.confirm(`Delete ${provider.name}?`) && remove.mutate()}
          >
            Delete
          </button>
        )}
      </div>
    </form>
  );
}

export function ProviderNewPage() {
  const providers = useQuery({ queryKey: key, queryFn: getProviders });
  if (providers.isPending) return <Loading />;
  return (
    <>
      <h1>Add provider</h1>
      <ProviderForm types={providers.data?.types ?? []} />
    </>
  );
}

export function ProviderEditPage() {
  const id = Number(useParams().id);
  const providers = useQuery({ queryKey: key, queryFn: getProviders });
  if (providers.isPending) return <Loading />;
  const provider = providers.data?.providers.find((p) => p.id === id);
  if (!provider) return <p className="empty" role="alert">Provider not found.</p>;
  return (
    <>
      <h1>{provider.name}</h1>
      <ProviderForm key={`${provider.id}-${provider.last_tested}`} provider={provider} types={providers.data!.types} />
    </>
  );
}

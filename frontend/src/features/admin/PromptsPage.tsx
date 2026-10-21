import { SectionSpy } from "../../components/SectionSpy";
import { Accordion, Button, Card, buttonVariants } from "@heroui/react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createPrompt,
  createPromptVersion,
  getPrompt,
  getPrompts,
  savePromptToDisk,
  updatePrompt,
  type PromptDetail,
  type PromptSummary,
} from "../../api/admin";

export function PromptListPage() {
  const navigate = useNavigate();
  const prompts = useQuery({
    queryKey: ["admin", "prompts"],
    queryFn: getPrompts,
  });
  if (prompts.isPending)
    return (
      <p className="empty" role="status">
        Loading…
      </p>
    );
  if (prompts.error)
    return (
      <p className="empty" role="alert">
        {prompts.error.message}
      </p>
    );
  const { types, prompts: all } = prompts.data;
  const populatedTypes = types.filter((type) =>
    all.some((prompt) => prompt.type === type.value),
  );
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>Prompts</h1>
          <p className="text-muted">
            Edit current prompts and browse revision history.
          </p>
        </div>
        <Button onPress={() => navigate("/manage/prompts/new")}>
          New prompt
        </Button>
      </div>
      <SectionSpy
        title="Prompts"
        sections={populatedTypes.map((type) => ({
          id: `prompt-section-${type.value}`,
          label: type.label,
        }))}
      />
      {populatedTypes.map((type) => {
        const byName = new Map<string, PromptSummary[]>();
        all
          .filter((p) => p.type === type.value)
          .forEach((p) =>
            byName.set(p.name, [...(byName.get(p.name) ?? []), p]),
          );
        if (!byName.size) return null;
        return (
          <section key={type.value} aria-label={type.label}>
            <h2
              id={`prompt-section-${type.value}`}
              className="scroll-mt-24"
              tabIndex={-1}
            >
              {type.label}
            </h2>
            <div className="prompt-grid">
              {[...byName].map(([name, versions]) => {
                const sorted = [...versions].sort(
                  (a, b) => b.version - a.version,
                );
                const current = sorted[0];
                return (
                  <Card key={name} className="admin-panel">
                    <Card.Content>
                      <div className="page-heading">
                        <div>
                          <h3 className="text-lg font-semibold break-words">
                            {name}
                          </h3>
                          <span className="badge">
                            Current · v{current.version}
                          </span>
                        </div>
                        <Button
                          size="sm"
                          onPress={() =>
                            navigate(`/manage/prompts/${current.id}`)
                          }
                        >
                          Edit current
                        </Button>
                      </div>
                      <p className="text-muted mt-3">
                        {current.description || "No description provided."}
                      </p>
                      {sorted.length > 1 && (
                        <Accordion className="mt-4">
                          <Accordion.Item id={`history-${current.id}`}>
                            <Accordion.Heading>
                              <Accordion.Trigger>
                                Previous revisions ({sorted.length - 1})
                                <Accordion.Indicator />
                              </Accordion.Trigger>
                            </Accordion.Heading>
                            <Accordion.Panel>
                              <Accordion.Body>
                                <ul className="revision-list">
                                  {sorted.slice(1).map((p) => (
                                    <li key={p.id}>
                                      <Link to={`/manage/prompts/${p.id}`}>
                                        <strong>v{p.version}</strong>
                                        <span>
                                          {p.description || "No description"}
                                        </span>
                                        <span aria-hidden>→</span>
                                      </Link>
                                    </li>
                                  ))}
                                </ul>
                              </Accordion.Body>
                            </Accordion.Panel>
                          </Accordion.Item>
                        </Accordion>
                      )}
                    </Card.Content>
                  </Card>
                );
              })}
            </div>
          </section>
        );
      })}
    </>
  );
}

function PromptForm({ prompt }: { prompt?: PromptDetail }) {
  const navigate = useNavigate();
  const cache = useQueryClient();
  const types = useQuery({
    queryKey: ["admin", "prompts"],
    queryFn: getPrompts,
  });
  const [type, setType] = useState("adventure");
  const [name, setName] = useState("");
  const [description, setDescription] = useState(prompt?.description ?? "");
  const [text, setText] = useState(prompt?.prompt_text ?? "");
  const [notice, setNotice] = useState("");

  const done = (saved: PromptDetail, message: string, go = false) => {
    cache.setQueryData(["admin", "prompt", saved.id], saved);
    cache.invalidateQueries({ queryKey: ["admin", "prompts"] });
    setNotice(message);
    if (go) navigate(`/manage/prompts/${saved.id}`);
  };
  const input = { description, prompt_text: text };
  const save = useMutation({
    mutationFn: () => updatePrompt(prompt!.id, input),
    onSuccess: (saved) => done(saved, `Saved ${saved.name} v${saved.version}`),
  });
  const version = useMutation({
    mutationFn: () => createPromptVersion(prompt!.id, input),
    onSuccess: (saved) => done(saved, `Created v${saved.version}`, true),
  });
  const create = useMutation({
    mutationFn: () => createPrompt({ ...input, type, name }),
    onSuccess: (saved) => done(saved, `Created ${saved.name}`, true),
  });
  const disk = useMutation({
    mutationFn: () => savePromptToDisk(prompt!.id),
    onSuccess: (result) => done(result.prompt, result.message),
  });
  const failure = [save, version, create, disk].find((m) => m.error)?.error;
  const busy =
    save.isPending || version.isPending || create.isPending || disk.isPending;

  return (
    <form
      className="form"
      onSubmit={(event) => {
        event.preventDefault();
        (prompt ? save : create).mutate();
      }}
    >
      {!prompt && (
        <>
          <label>
            Type
            <select value={type} onChange={(e) => setType(e.target.value)}>
              {(types.data?.types ?? []).map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Name
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </label>
        </>
      )}
      <label>
        Description
        <input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </label>
      <label>
        Prompt text
        <textarea
          rows={20}
          value={text}
          onChange={(e) => setText(e.target.value)}
          required
        />
      </label>
      {notice && <p role="status">{notice}</p>}
      {failure && <p role="alert">{failure.message}</p>}
      <div className="toolbar">
        <button type="submit" disabled={busy}>
          {prompt ? "Save changes" : "Create prompt"}
        </button>
        {prompt && (
          <>
            <button
              type="button"
              disabled={busy}
              onClick={() => version.mutate()}
            >
              Save as new version
            </button>
            <button type="button" disabled={busy} onClick={() => disk.mutate()}>
              Save to disk
            </button>
          </>
        )}
      </div>
    </form>
  );
}

export function PromptEditPage() {
  const id = Number(useParams().id);
  const prompt = useQuery({
    queryKey: ["admin", "prompt", id],
    queryFn: () => getPrompt(id),
  });
  const navigate = useNavigate();
  if (prompt.isPending)
    return (
      <p className="empty" role="status">
        Loading…
      </p>
    );
  if (prompt.error)
    return (
      <p className="empty" role="alert">
        {prompt.error.message}
      </p>
    );
  const p = prompt.data;
  return (
    <>
      <p>
        <Link to="/manage/prompts">← Back to prompts</Link>
      </p>
      <h1>{p.name}</h1>
      <p>
        Type: {p.type}
        {p.file_path && ` · File: ${p.file_path}`}
      </p>
      <label>
        Version{" "}
        <select
          value={p.id}
          onChange={(e) => navigate(`/manage/prompts/${e.target.value}`)}
        >
          {p.versions.map((v) => (
            <option key={v.id} value={v.id}>
              v{v.version}
              {v.description && ` – ${v.description}`}
            </option>
          ))}
        </select>
      </label>
      <PromptForm key={p.id} prompt={p} />
    </>
  );
}

export function PromptNewPage() {
  return (
    <>
      <p>
        <Link to="/manage/prompts">← Back to prompts</Link>
      </p>
      <h1>New prompt</h1>
      <PromptForm />
    </>
  );
}

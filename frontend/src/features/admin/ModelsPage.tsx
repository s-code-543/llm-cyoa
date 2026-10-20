import { Button, Chip, CloseButton } from "@heroui/react";
import { ModelCatalogBrowser } from "./ModelCatalogBrowser";
import { ModelSelect } from "./ModelSelect";
import { defaultModelFilters, existingModelFilters } from "./modelCatalog";
import { useState } from "react";
import { Link, useParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  browseModels,
  refreshModelCosts,
  validateModels,
  deleteUnavailableModels,
  deleteModel,
  getModels,
  importModels,
  removeModels,
  syncModels,
} from "../../api/admin";
import { Failure, Loading } from "./ui";

export function ModelListPage() {
  const cache = useQueryClient();
  const models = useQuery({
    queryKey: ["admin", "models"],
    queryFn: getModels,
  });
  const [provider, setProvider] = useState("");
  const refresh = () => cache.invalidateQueries({ queryKey: ["admin"] });
  const validation = useMutation({
    mutationFn: validateModels,
    onSuccess: refresh,
  });
  const cleanup = useMutation({
    mutationFn: deleteUnavailableModels,
    onSuccess: () => {
      validation.reset();
      refresh();
    },
  });
  const costs = useMutation({
    mutationFn: refreshModelCosts,
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: deleteModel,
    onSuccess: () => cache.invalidateQueries({ queryKey: ["admin", "models"] }),
  });
  if (models.isPending) return <Loading />;
  if (models.error) return <Failure error={models.error} />;
  return (
    <>
      <h1>Models</h1>
      <section
        id="model-maintenance"
        aria-label="Validation and costs"
        tabIndex={-1}
      >
        <div className="toolbar model-toolbar items-center">
          <Button
            className="h-auto min-h-10 md:h-10"
            type="button"
            isDisabled={validation.isPending || cleanup.isPending}
            onPress={() => {
              cleanup.reset();
              validation.mutate();
            }}
          >
            {validation.isPending ? "Validating models…" : "Validate models"}
          </Button>
          <Button
            className="h-auto min-h-10 md:h-10"
            type="button"
            isDisabled={costs.isPending}
            onPress={() => costs.mutate()}
          >
            {costs.isPending
              ? "Refreshing costs…"
              : "Refresh costs from providers"}
          </Button>
        </div>
        <p>
          Provider rates in USD. Token prices are per 1M tokens; actual charges
          depend on usage and routing.
        </p>
        {costs.data && <p role="status">{costs.data.message}</p>}
        {costs.data?.failures.map((failure) => (
          <p role="alert" key={failure}>
            {failure}
          </p>
        ))}
        <Failure error={validation.error ?? cleanup.error ?? costs.error} />
        {cleanup.data && <p role="status">{cleanup.data.message}</p>}
        {validation.data && (
          <section aria-label="Model validation results">
            {validation.data.failures.map((failure) => (
              <p role="alert" key={failure}>
                {failure}
              </p>
            ))}
            {validation.data.unavailable.length ? (
              <>
                <p>
                  These models are no longer available. Adventures requiring
                  them cannot be started.
                </p>
                <ul>
                  {validation.data.unavailable.map((model) => (
                    <li key={model.id}>{model.name}</li>
                  ))}
                </ul>
                <Button
                  type="button"
                  className="danger"
                  isDisabled={cleanup.isPending}
                  onPress={() => {
                    if (
                      window.confirm(
                        "Delete these unavailable models? Saved configurations will be kept and must be updated before their adventures can start.",
                      )
                    )
                      cleanup.mutate(
                        validation.data.unavailable.map((model) => model.id),
                      );
                  }}
                >
                  Delete unavailable models
                </Button>
              </>
            ) : (
              <p role="status">
                {validation.data.failures.length
                  ? "No unavailable models found among providers checked successfully."
                  : "All models are available."}
              </p>
            )}
          </section>
        )}
      </section>
      <ModelCatalogBrowser
        models={models.data.models.filter(
          (model) => !provider || String(model.provider_id) === provider,
        )}
        filterModels={models.data.models}
        initialFilters={existingModelFilters}
        toolbar={
          <>
            <ModelSelect
              label="Provider"
              hideLabel
              value={provider}
              onChange={setProvider}
              options={[
                { value: "", label: "All providers" },
                ...models.data.providers.map((p) => ({
                  value: String(p.id),
                  label: p.name,
                })),
              ]}
            />
            <Link to="/manage/providers">Import from a provider →</Link>
          </>
        }
        beforeResults={<Failure error={remove.error} />}
        showProvider
        renderName={(m) => (
          <>
            {m.name}
            {m.image_generation ? " · Image generation" : ""}
            {m.is_available ? "" : " (unavailable)"}
          </>
        )}
        renderAction={(m) => (
          <Button
            variant="danger-soft"
            onPress={() => {
              if (window.confirm(`Delete ${m.name}?`)) remove.mutate(m.id);
            }}
          >
            Delete
          </Button>
        )}
      />
    </>
  );
}

export function ModelBrowserPage() {
  const id = Number(useParams().id);
  const cache = useQueryClient();
  const remote = useQuery({
    queryKey: ["admin", "browse", id],
    queryFn: () => browseModels(id),
  });
  const [selected, setSelected] = useState<string[]>([]);
  const [notice, setNotice] = useState("");
  const refresh = (result: {
    message: string;
    pricing_warnings?: string[];
  }) => {
    setNotice([result.message, ...(result.pricing_warnings ?? [])].join(" "));
    setSelected([]);
    cache.invalidateQueries({ queryKey: ["admin"] });
  };
  const doImport = useMutation({
    mutationFn: () => importModels(id, selected),
    onSuccess: refresh,
  });
  const doRemove = useMutation({
    mutationFn: () => removeModels(id, selected),
    onSuccess: refresh,
  });
  const doSync = useMutation({
    mutationFn: () => syncModels(id),
    onSuccess: refresh,
  });
  if (remote.isPending) return <Loading />;
  if (remote.error) return <Failure error={remote.error} />;
  const toggle = (modelId: string) =>
    setSelected((cur) =>
      cur.includes(modelId)
        ? cur.filter((x) => x !== modelId)
        : [...cur, modelId],
    );
  const busy =
    doImport.isPending ||
    doRemove.isPending ||
    doSync.isPending ||
    remote.isFetching;
  return (
    <>
      <h1>Models from {remote.data.provider.name}</h1>
      <p>
        Live provider rates in USD. Token prices are per 1M tokens; actual
        charges depend on usage and routing.
      </p>
      <p>
        Sync updates all imported models from this provider and deletes those no
        longer available. It does not import new models or use the current
        selection.
      </p>
      <ModelCatalogBrowser
        models={remote.data.models}
        initialFilters={defaultModelFilters}
        importing
        toolbar={
          <>
            <Button
              className="h-auto min-h-10 md:h-10"
              type="button"
              isDisabled={busy || !selected.length}
              onPress={() => doImport.mutate()}
            >
              Import selected
            </Button>
            <Button
              className="h-auto min-h-10 md:h-10"
              type="button"
              isDisabled={busy || !selected.length}
              onPress={() => doRemove.mutate()}
            >
              Remove selected
            </Button>
            <Button
              className="h-auto min-h-10 md:h-10"
              type="button"
              isDisabled={busy}
              onPress={() => {
                void remote.refetch().then((result) => {
                  if (!result.error) setSelected([]);
                });
              }}
            >
              {remote.isFetching
                ? "Refreshing costs…"
                : "Refresh models and costs"}
            </Button>
            <Button
              className="h-auto min-h-10 md:h-10"
              type="button"
              isDisabled={busy}
              onPress={() => {
                if (
                  window.confirm(
                    "Sync all models already imported from this provider? This refreshes their prices and metadata and deletes any no longer in the catalog. Saved configurations using deleted models will need repair. New models are not imported.",
                  )
                )
                  doSync.mutate();
              }}
            >
              Sync imported models
            </Button>
          </>
        }
        afterToolbar={
          <>
            {selected.length > 0 && (
              <section aria-label="Selected models" className="toolbar">
                <span>{selected.length} selected</span>
                {selected.map((modelId) => {
                  const model = remote.data.models.find(
                    (m) => m.id === modelId,
                  );
                  return (
                    <Chip key={modelId} color="accent" className="gap-2">
                      <Chip.Label>{model?.name ?? modelId}</Chip.Label>
                      <CloseButton
                        isDisabled={busy}
                        aria-label={`Deselect ${model?.name ?? modelId}`}
                        onPress={() => toggle(modelId)}
                      />
                    </Chip>
                  );
                })}
              </section>
            )}
            {remote.data.pricing_warnings?.map((warning) => (
              <p role="alert" key={warning}>
                {warning}
              </p>
            ))}
            {notice && <p role="status">{notice}</p>}
            <Failure error={doImport.error ?? doRemove.error ?? doSync.error} />
          </>
        }
        renderName={(m) => (
          <label className="model-checkbox">
            <input
              type="checkbox"
              checked={selected.includes(m.id)}
              disabled={busy}
              onChange={() => toggle(m.id)}
              aria-label={`Select ${m.name}`}
            />
            <span>
              <strong>{m.name}</strong>
              {m.image_generation ? " · Image generation" : ""}
              {m.imported ? " ✓ imported" : ""}
            </span>
          </label>
        )}
      />
    </>
  );
}

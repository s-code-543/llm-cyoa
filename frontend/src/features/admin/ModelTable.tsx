import { Disclosure, Table } from "@heroui/react";
import { useEffect, useState, type ReactNode } from "react";
import { ModelCosts } from "./ModelCosts";
import {
  modelSortDescriptor,
  modelSortValue,
  type CatalogModel,
  parametersOf,
  outputsOf,
} from "./modelCatalog";

export type RowModel = CatalogModel & {
  description?: string;
  provider_name?: string;
  is_available?: boolean;
  pricing_updated_at?: string | null;
};
function useCompactModels() {
  const query = "(max-width: 767px)";
  const [compact, setCompact] = useState(
    () => window.matchMedia?.(query).matches ?? false,
  );
  useEffect(() => {
    const media = window.matchMedia?.(query);
    if (!media) return;
    const update = () => setCompact(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  return compact;
}

export function ModelTable<T extends RowModel>({
  models,
  sort,
  onSort,
  renderName,
  renderAction,
  showProvider = false,
  showImageCosts = false,
}: {
  models: T[];
  sort: string;
  onSort: (sort: string) => void;
  renderName: (model: T) => ReactNode;
  renderAction?: (model: T) => ReactNode;
  showProvider?: boolean;
  showImageCosts?: boolean;
}) {
  const compact = useCompactModels();
  const columns = [
    { id: "name", label: "Model", sortable: true },
    ...(showProvider ? [{ id: "provider", label: "Provider" }] : []),
    { id: "context", label: "Context (tokens)", sortable: true },
    { id: "input", label: "Input cost ($ / 1M)", sortable: true },
    { id: "output", label: "Output cost ($ / 1M)", sortable: true },
    ...(showImageCosts
      ? [
          {
            id: "image",
            label: "Image cost ($ / 1M image tokens)",
            sortable: true,
          },
        ]
      : []),
    { id: "newest", label: "Released", sortable: true },
    ...(renderAction ? [{ id: "actions", label: "Actions" }] : []),
  ];
  function cell(model: T, column: string) {
    switch (column) {
      case "name":
        return (
          <div className="model-name-cell">
            {renderName(model)}
            <code>{model.model_identifier ?? model.id}</code>
          </div>
        );
      case "identifier":
        return <code>{model.model_identifier ?? model.id}</code>;
      case "provider":
        return model.provider_name;
      case "context":
        return model.context_length
          ? `${model.context_length.toLocaleString()}${compact ? " tokens" : ""}`
          : "Unknown";
      case "input":
        return (
          <ModelCosts
            pricing={model.pricing}
            section="prompt"
            compact={!compact}
          />
        );
      case "output":
        return (
          <ModelCosts
            pricing={model.pricing}
            section="completion"
            compact={!compact}
          />
        );
      case "image":
        return (
          <ModelCosts
            pricing={model.pricing}
            section="image_token"
            compact={!compact}
          />
        );
      case "newest":
        return model.created
          ? new Date(model.created * 1000).toLocaleDateString()
          : "Unknown";
      case "actions":
        return renderAction?.(model);
    }
  }
  if (compact) {
    return (
      <section className="model-drawers" aria-label="Models">
        {models.map((model) => (
          <Disclosure key={model.id} className="model-card">
            <div className="model-card-heading">
              <div className="model-card-name">
                {renderName(model)}
                {showProvider && <small>{model.provider_name}</small>}
              </div>
              <Disclosure.Heading>
                <Disclosure.Trigger aria-label={`Details for ${model.name}`}>
                  Details
                  <Disclosure.Indicator />
                </Disclosure.Trigger>
              </Disclosure.Heading>
            </div>
            <div className="model-card-prices">
              {cell(model, "input")}
              {cell(model, "output")}
            </div>
            <Disclosure.Content>
              <Disclosure.Body>
                {model.description && (
                  <p className="model-card-description">{model.description}</p>
                )}
                <dl className="model-card-details">
                  <div>
                    <dt>Identifier</dt>
                    <dd>{cell(model, "identifier")}</dd>
                  </div>
                  <div>
                    <dt>Context</dt>
                    <dd>{cell(model, "context")}</dd>
                  </div>
                  {columns.some((column) => column.id === "image") && (
                    <div>
                      <dt>Image cost</dt>
                      <dd>{cell(model, "image")}</dd>
                    </div>
                  )}
                  <div>
                    <dt>Released</dt>
                    <dd>{cell(model, "newest")}</dd>
                  </div>
                  <div>
                    <dt>Input types</dt>
                    <dd>
                      {(model.architecture?.input_modalities ?? ["text"]).join(
                        ", ",
                      )}
                    </dd>
                  </div>
                  <div>
                    <dt>Output types</dt>
                    <dd>{outputsOf(model).join(", ")}</dd>
                  </div>
                  <div>
                    <dt>Capabilities</dt>
                    <dd>{parametersOf(model).join(", ") || "Not supplied"}</dd>
                  </div>
                </dl>
                {renderAction && (
                  <div className="model-card-actions">
                    {renderAction(model)}
                  </div>
                )}
              </Disclosure.Body>
            </Disclosure.Content>
          </Disclosure>
        ))}
      </section>
    );
  }
  return (
    <Table className="model-table">
      <Table.ScrollContainer>
        <Table.Content
          aria-label="Models"
          sortDescriptor={modelSortDescriptor(sort)}
          onSortChange={(next) =>
            onSort(modelSortValue(String(next.column), next.direction))
          }
        >
          <Table.Header columns={columns}>
            {(column) => (
              <Table.Column
                id={column.id}
                textValue={column.label}
                isRowHeader={column.id === "name"}
                allowsSorting={column.sortable}
              >
                {({ sortDirection }) =>
                  column.sortable ? (
                    <Table.SortableColumnHeader sortDirection={sortDirection}>
                      {column.label}
                    </Table.SortableColumnHeader>
                  ) : (
                    column.label
                  )
                }
              </Table.Column>
            )}
          </Table.Header>
          <Table.Body
            items={models}
            dependencies={[
              renderName,
              renderAction,
              showImageCosts,
              showProvider,
            ]}
          >
            {(model) => (
              <Table.Row id={model.id} columns={columns}>
                {(column) => <Table.Cell>{cell(model, column.id)}</Table.Cell>}
              </Table.Row>
            )}
          </Table.Body>
        </Table.Content>
      </Table.ScrollContainer>
    </Table>
  );
}

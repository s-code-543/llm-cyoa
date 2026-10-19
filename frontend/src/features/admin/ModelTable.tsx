import { Table } from "@heroui/react";
import type { ReactNode } from "react";
import { ModelCosts } from "./ModelCosts";
import {
  modelSortDescriptor,
  modelSortValue,
  type CatalogModel,
} from "./modelCatalog";

type RowModel = CatalogModel & {
  provider_name?: string;
  is_available?: boolean;
  pricing_updated_at?: string | null;
};
export function ModelTable<T extends RowModel>({
  models,
  sort,
  onSort,
  renderName,
  renderAction,
  showProvider = false,
}: {
  models: T[];
  sort: string;
  onSort: (sort: string) => void;
  renderName: (model: T) => ReactNode;
  renderAction?: (model: T) => ReactNode;
  showProvider?: boolean;
}) {
  const columns = [
    { id: "name", label: "Model", sortable: true },
    { id: "identifier", label: "Identifier" },
    ...(showProvider ? [{ id: "provider", label: "Provider" }] : []),
    { id: "context", label: "Context", sortable: true },
    { id: "input", label: "Input cost (USD / 1M tokens)", sortable: true },
    { id: "output", label: "Output cost (USD / 1M tokens)", sortable: true },
    { id: "newest", label: "Released", sortable: true },
    { id: "other", label: "Other costs (USD)" },
    ...(renderAction ? [{ id: "actions", label: "Actions" }] : []),
  ];
  function cell(model: T, column: string) {
    switch (column) {
      case "name":
        return renderName(model);
      case "identifier":
        return <code>{model.model_identifier ?? model.id}</code>;
      case "provider":
        return model.provider_name;
      case "context":
        return model.context_length
          ? `${model.context_length.toLocaleString()} tokens`
          : "Unknown";
      case "input":
        return <ModelCosts pricing={model.pricing} section="prompt" />;
      case "output":
        return <ModelCosts pricing={model.pricing} section="completion" />;
      case "newest":
        return model.created
          ? new Date(model.created * 1000).toLocaleDateString()
          : "Unknown";
      case "other":
        return (
          <ModelCosts
            pricing={model.pricing}
            section="other"
            updatedAt={model.pricing_updated_at}
          />
        );
      case "actions":
        return renderAction?.(model);
    }
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
          <Table.Body items={models} dependencies={[renderName, renderAction]}>
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

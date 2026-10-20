import { Input } from "@heroui/react";
import { useState, type ReactNode } from "react";
import { ModelFilterControls } from "./ModelFilterControls";
import { ModelTable, type RowModel } from "./ModelTable";
import { filterModels, type ModelFilterValues } from "./modelCatalog";

export function ModelCatalogBrowser<T extends RowModel>({
  models,
  filterModels: filterOptions = models,
  initialFilters,
  importing = false,
  toolbar,
  afterToolbar,
  beforeResults,
  showProvider,
  renderName,
  renderAction,
}: {
  models: T[];
  filterModels?: T[];
  initialFilters: ModelFilterValues;
  importing?: boolean;
  toolbar?: ReactNode;
  afterToolbar?: ReactNode;
  beforeResults?: ReactNode;
  showProvider?: boolean;
  renderName: (model: T) => ReactNode;
  renderAction?: (model: T) => ReactNode;
}) {
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState(initialFilters);
  const needle = search.trim().toLowerCase();
  const shown = filterModels(
    models.filter(
      (model) =>
        !needle ||
        `${model.name} ${model.model_identifier ?? model.id}`
          .toLowerCase()
          .includes(needle),
    ),
    filters,
  );
  return (
    <>
      <ModelFilterControls
        models={filterOptions}
        value={filters}
        onChange={setFilters}
        importing={importing}
      />
      <div className="toolbar model-toolbar items-center">
        <Input
          className="h-10 min-h-10"
          aria-label={importing ? "Search available models" : "Search models"}
          placeholder="Search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        {toolbar}
      </div>
      {afterToolbar}
      <p>
        {shown.length} of {models.length} models match.
      </p>
      {beforeResults}
      {shown.length === 0 ? (
        <p className="empty">
          {importing
            ? "No models match these filters. Clear the input cost limit to include all prices."
            : "No models match."}
        </p>
      ) : (
        <ModelTable
          models={shown}
          showImageCosts={filters.output === "image"}
          sort={filters.sort}
          onSort={(sort) => setFilters({ ...filters, sort })}
          showProvider={showProvider}
          renderName={renderName}
          renderAction={renderAction}
        />
      )}
    </>
  );
}

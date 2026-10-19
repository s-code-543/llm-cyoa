import type { ModelMetadata, ModelPricing } from "../../api/admin";

export type CatalogModel = ModelMetadata & {
  id: string | number;
  model_identifier?: string;
  name: string;
  pricing?: ModelPricing;
  image_generation?: boolean;
};
export const defaultModelFilters = {
  maxInput: "100",
  maxOutput: "",
  includeUnknown: false,
  excludeFree: false,
  publisher: "",
  input: "text",
  output: "text",
  capability: "",
  minContext: "",
  sort: "input-asc",
};
export type ModelFilterValues = typeof defaultModelFilters;
export const publisherOf = (model: CatalogModel) => {
  const id = model.model_identifier ?? String(model.id);
  return id.includes("/") ? id.split("/")[0] : "";
};
export const parametersOf = (model: CatalogModel) =>
  Array.isArray(model.supported_parameters)
    ? model.supported_parameters
    : Object.keys(model.supported_parameters ?? {});
export const outputsOf = (model: CatalogModel) =>
  model.architecture?.output_modalities ??
  (model.image_generation ? ["image"] : ["text"]);
export function tokenCost(model: CatalogModel, key: "prompt" | "completion") {
  const value = model.pricing?.[key];
  if (
    (typeof value !== "string" && typeof value !== "number") ||
    String(value).trim() === ""
  )
    return null;
  const cost = Number(value) * 1_000_000;
  return Number.isFinite(cost) && cost >= 0 ? cost : null;
}
function underLimit(
  cost: number | null,
  cents: string,
  includeUnknown: boolean,
) {
  if (!cents.trim()) return true;
  return cost === null ? includeUnknown : cost <= Number(cents) / 100;
}
export function filterModels<T extends CatalogModel>(
  models: T[],
  filters: ModelFilterValues,
): T[] {
  return models
    .filter(
      (m) =>
        (!filters.excludeFree || !isFreeModel(m)) &&
        underLimit(
          tokenCost(m, "prompt"),
          filters.maxInput,
          filters.includeUnknown,
        ) &&
        underLimit(
          tokenCost(m, "completion"),
          filters.maxOutput,
          filters.includeUnknown,
        ) &&
        (!filters.publisher || publisherOf(m) === filters.publisher) &&
        (!filters.input ||
          (m.architecture?.input_modalities ?? ["text"]).includes(
            filters.input,
          )) &&
        (!filters.output || outputsOf(m).includes(filters.output)) &&
        (!filters.capability || parametersOf(m).includes(filters.capability)) &&
        (!filters.minContext ||
          (m.context_length ?? 0) >= Number(filters.minContext)),
    )
    .sort((a, b) => {
      let result = 0;
      if (
        filters.sort.startsWith("input-") ||
        filters.sort.startsWith("output-")
      ) {
        const key = filters.sort.startsWith("input-") ? "prompt" : "completion";
        const left = tokenCost(a, key),
          right = tokenCost(b, key);
        if (left === null || right === null)
          return left === right
            ? a.name.localeCompare(b.name)
            : left === null
              ? 1
              : -1;
        result = (left - right) * (filters.sort.endsWith("desc") ? -1 : 1);
      } else if (filters.sort.startsWith("context"))
        result =
          ((b.context_length ?? 0) - (a.context_length ?? 0)) *
          (filters.sort.endsWith("asc") ? -1 : 1);
      else if (filters.sort.startsWith("newest"))
        result =
          ((b.created ?? 0) - (a.created ?? 0)) *
          (filters.sort.endsWith("asc") ? -1 : 1);
      return (
        result ||
        a.name.localeCompare(b.name) * (filters.sort === "name-desc" ? -1 : 1)
      );
    });
}

function isFreeModel(model: CatalogModel) {
  if (tokenCost(model, "prompt") !== 0 || tokenCost(model, "completion") !== 0)
    return false;
  return Object.values(model.pricing ?? {}).every((value) =>
    Array.isArray(value)
      ? value.length === 0
      : (typeof value === "string" || typeof value === "number") &&
        String(value).trim() !== "" &&
        Number(value) === 0,
  );
}

export function modelSortDescriptor(sort: string): {
  column: string;
  direction: "ascending" | "descending";
} {
  if (sort.startsWith("input-") || sort.startsWith("output-"))
    return {
      column: sort.split("-")[0],
      direction: sort.endsWith("desc") ? "descending" : "ascending",
    };
  return {
    column: sort.startsWith("context")
      ? "context"
      : sort.startsWith("newest")
        ? "newest"
        : "name",
    direction:
      sort === "name-desc" || sort === "context" || sort === "newest"
        ? "descending"
        : "ascending",
  };
}
export function modelSortValue(
  column: string,
  direction: "ascending" | "descending",
) {
  if (column === "name")
    return direction === "ascending" ? "name" : "name-desc";
  if (column === "context" || column === "newest")
    return direction === "descending" ? column : `${column}-asc`;
  return `${column}-${direction === "descending" ? "desc" : "asc"}`;
}

import { test, expect } from "vitest";
import {
  defaultModelFilters,
  filterModels,
  tokenCost,
  type CatalogModel,
} from "./modelCatalog";
const models: CatalogModel[] = [
  {
    id: "openai/expensive",
    name: "Expensive",
    pricing: { prompt: "0.000002", completion: "0.000003" },
    context_length: 200000,
    created: 3,
  },
  {
    id: "qwen/boundary",
    name: "Boundary",
    pricing: { prompt: "0.000001", completion: "0.000004" },
    context_length: 128000,
    created: 2,
    architecture: {
      input_modalities: ["text", "image"],
      output_modalities: ["text"],
    },
    supported_parameters: ["tools"],
  },
  {
    id: "qwen/free",
    name: "Free",
    pricing: { prompt: "0", completion: "0" },
    context_length: 64000,
    created: 1,
  },
  {
    id: "image/unknown",
    name: "Unknown",
    pricing: {},
    image_generation: true,
    supported_parameters: { aspect_ratio: {} },
  },
];
test("default threshold includes free and exactly 100 cents/M but excludes expensive and unknown rates", () => {
  expect(filterModels(models, defaultModelFilters).map((m) => m.name)).toEqual([
    "Free",
    "Boundary",
  ]);
  expect(
    tokenCost({ id: 1, name: "Invalid", pricing: { prompt: "-1" } }, "prompt"),
  ).toBeNull();
  expect(
    tokenCost({ id: 1, name: "Invalid", pricing: { prompt: "" } }, "prompt"),
  ).toBeNull();
});
test("sorts costs numerically in both directions with unknown rates last", () => {
  expect(
    filterModels(models, {
      ...defaultModelFilters,
      maxInput: "",
      output: "",
      sort: "input-desc",
    }).map((m) => m.name),
  ).toEqual(["Expensive", "Boundary", "Free", "Unknown"]);
  expect(
    filterModels(models, {
      ...defaultModelFilters,
      maxInput: "",
      output: "",
      sort: "output-asc",
    }).map((m) => m.name),
  ).toEqual(["Free", "Expensive", "Boundary", "Unknown"]);
  expect(
    filterModels(models, { ...defaultModelFilters, maxOutput: "300" }).map(
      (m) => m.name,
    ),
  ).toEqual(["Free"]);
});
test("combines publisher, modalities, capabilities and context filters", () => {
  const filters = {
    ...defaultModelFilters,
    publisher: "qwen",
    input: "image",
    output: "text",
    capability: "tools",
    minContext: "100000",
  };
  expect(filterModels(models, filters).map((m) => m.name)).toEqual([
    "Boundary",
  ]);
  expect(filterModels(models, { ...filters, minContext: "200000" })).toEqual(
    [],
  );
  expect(
    filterModels(models, {
      ...defaultModelFilters,
      includeUnknown: true,
      output: "image",
      capability: "aspect_ratio",
    }).map((m) => m.name),
  ).toEqual(["Unknown"]);
});
test("sorts by context and date", () => {
  const filters = { ...defaultModelFilters, maxInput: "" };
  expect(filterModels(models, { ...filters, sort: "context" })[0].name).toBe(
    "Expensive",
  );
  expect(filterModels(models, { ...filters, sort: "newest" })[0].name).toBe(
    "Expensive",
  );
});

test("text defaults exclude image output and free exclusion does not hide paid image charges", () => {
  expect(defaultModelFilters.input).toBe("text");
  expect(defaultModelFilters.output).toBe("text");
  const paid = {
    id: "paid",
    name: "Paid image input",
    pricing: { prompt: "0", completion: "0", image: "0.04" },
  };
  expect(
    filterModels([...models, paid], {
      ...defaultModelFilters,
      excludeFree: true,
    }).map((m) => m.name),
  ).toEqual(["Paid image input", "Boundary"]);
});

import { Disclosure, Input } from "@heroui/react";
import { Toggle } from "../../components/Toggle";
import { ModelSelect } from "./ModelSelect";
import {
  type CatalogModel,
  type ModelFilterValues,
  outputsOf,
  parametersOf,
  publisherOf,
} from "./modelCatalog";

export function ModelFilterControls({
  models,
  value,
  onChange,
  importing = false,
}: {
  importing?: boolean;
  models: CatalogModel[];
  value: ModelFilterValues;
  onChange: (value: ModelFilterValues) => void;
}) {
  const set = (key: keyof ModelFilterValues, next: string | boolean) =>
    onChange({
      ...value,
      [key]: next,
      ...(key === "output" &&
      next !== "image" &&
      value.sort.startsWith("image-")
        ? { sort: "name" }
        : {}),
    });
  const options = (items: string[]) =>
    [...new Set(items)]
      .filter(Boolean)
      .sort()
      .map((item) => ({ value: item, label: item }));
  return (
    <Disclosure className="model-filter-drawer">
      <Disclosure.Heading>
        <Disclosure.Trigger className="inline-flex items-center gap-2 whitespace-nowrap">
          <span>Filter and sort models</span>
          <Disclosure.Indicator className="ms-0 shrink-0" />
        </Disclosure.Trigger>
      </Disclosure.Heading>
      <Disclosure.Content>
        <Disclosure.Body>
          <fieldset
            className="model-filters"
            aria-label="Model filter controls"
          >
            <label>
              Max input (¢ / 1M tokens)
              <Input
                type="number"
                min="0"
                step="any"
                placeholder="No limit"
                value={value.maxInput}
                onChange={(e) => set("maxInput", e.target.value)}
              />
            </label>
            <label>
              Max output (¢ / 1M tokens)
              <Input
                type="number"
                min="0"
                step="any"
                placeholder="No limit"
                value={value.maxOutput}
                onChange={(e) => set("maxOutput", e.target.value)}
              />
            </label>
            <ModelSelect
              label="Publisher"
              value={value.publisher}
              onChange={(next) => set("publisher", next)}
              options={[
                { value: "", label: "All publishers" },
                ...options(models.map(publisherOf)),
              ]}
            />
            <ModelSelect
              label="Input type"
              value={value.input}
              onChange={(next) => set("input", next)}
              options={[
                { value: "", label: "All input types" },
                ...options([
                  "text",
                  ...models.flatMap(
                    (m) => m.architecture?.input_modalities ?? [],
                  ),
                ]),
              ]}
            />
            <ModelSelect
              label="Output type"
              value={value.output}
              onChange={(next) => set("output", next)}
              options={[
                { value: "", label: "All output types" },
                ...options(["text", ...models.flatMap(outputsOf)]),
              ]}
            />
            <ModelSelect
              label="Capability"
              value={value.capability}
              onChange={(next) => set("capability", next)}
              options={[
                { value: "", label: "All capabilities" },
                ...options(models.flatMap(parametersOf)),
              ]}
            />
            <label>
              Minimum context (tokens)
              <Input
                type="number"
                min="0"
                step="1"
                placeholder="Any"
                value={value.minContext}
                onChange={(e) => set("minContext", e.target.value)}
              />
            </label>
            <ModelSelect
              label="Sort by"
              value={value.sort}
              onChange={(next) => set("sort", next)}
              options={[
                { value: "input-asc", label: "Input cost: low to high" },
                { value: "input-desc", label: "Input cost: high to low" },
                { value: "output-asc", label: "Output cost: low to high" },
                { value: "output-desc", label: "Output cost: high to low" },
                ...(value.output === "image"
                  ? [
                      {
                        value: "image-asc",
                        label: "Image token cost: low to high",
                      },
                      {
                        value: "image-desc",
                        label: "Image token cost: high to low",
                      },
                    ]
                  : []),
                { value: "name", label: "Name: A–Z" },
                { value: "name-desc", label: "Name: Z–A" },
                { value: "context", label: "Context: largest first" },
                { value: "context-asc", label: "Context: smallest first" },
                { value: "newest", label: "Newest first" },
                { value: "newest-asc", label: "Oldest first" },
              ]}
            />
            <Toggle
              checked={value.excludeFree}
              onChange={(checked) => set("excludeFree", checked)}
            >
              Exclude free models
            </Toggle>
            <Toggle
              checked={value.includeUnknown}
              onChange={(checked) => set("includeUnknown", checked)}
            >
              Include unknown or variable token prices
            </Toggle>
            <small>
              {importing
                ? "Import defaults: text input and output; input ≤ 100¢ ($1) / 1M tokens. Clear a price limit for all rates."
                : "All existing models are shown by default, including free models, image models, and models with unknown prices."}
            </small>
          </fieldset>
        </Disclosure.Body>
      </Disclosure.Content>
    </Disclosure>
  );
}

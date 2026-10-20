import { vi, test, expect, afterEach } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import { ModelListPage, ModelBrowserPage } from "./ModelsPage";
import { ModelCosts } from "./ModelCosts";
import { apiFetch } from "../../api/client";

vi.mock("../../api/client", () => ({ apiFetch: vi.fn() }));
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

test("validation offers confirmed cleanup and reports provider failures", async () => {
  const api = vi.mocked(apiFetch);
  api.mockImplementation(async (url, options) => {
    if (url.endsWith("/validate")) {
      if ((options?.payload as { delete_ids?: number[] })?.delete_ids)
        return { message: "Deleted 1 unavailable models." };
      return {
        unavailable: [{ id: 2, name: "Retired model" }],
        failures: [
          "Could not validate Offline provider; its models were left unchanged.",
        ],
      };
    }
    return { models: [], providers: [] };
  });
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <ModelListPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "Validate models" }),
  );
  expect(await screen.findByText("Retired model")).toBeTruthy();
  expect(screen.getByRole("alert")).toHaveTextContent("Offline provider");
  const remove = screen.getByRole("button", {
    name: "Delete unavailable models",
  });
  fireEvent.click(remove);
  expect(api).not.toHaveBeenCalledWith(expect.anything(), {
    payload: { delete_ids: [2] },
  });
  confirm.mockReturnValue(true);
  fireEvent.click(remove);
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith("/api/v1/admin/models/validate", {
      payload: { delete_ids: [2] },
    }),
  );
  expect(await screen.findByText("Deleted 1 unavailable models.")).toBeTruthy();
});

test("checkbox selections stay visible in removable chips while filtering", async () => {
  const api = vi.mocked(apiFetch);
  api.mockImplementation(async (url) => {
    if (url.endsWith("/import")) return { message: "Imported 1 model" };
    return {
      provider: { name: "OpenRouter" },
      models: [
        {
          id: "alpha",
          name: "Alpha",
          pricing: { prompt: "0.000001", completion: "0.000004" },
        },
        { id: "beta", name: "Beta", pricing: { prompt: "0.0000005" } },
      ],
    };
  });
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={["/providers/1"]}>
        <Routes>
          <Route path="/providers/:id" element={<ModelBrowserPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  const alpha = await screen.findByRole("checkbox", { name: "Select Alpha" });
  fireEvent.click(alpha);
  fireEvent.click(screen.getByRole("checkbox", { name: "Select Beta" }));
  expect(screen.getByText("2 selected")).toBeTruthy();
  expect(screen.getByText("$1")).toBeTruthy();
  expect(screen.getByText("$4")).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Search available models"), {
    target: { value: "Beta" },
  });
  expect(screen.queryByRole("checkbox", { name: "Select Alpha" })).toBeNull();
  expect(
    screen.getByRole("button", { name: "Deselect Alpha" }),
  ).toHaveAttribute("data-slot", "close-button");
  fireEvent.click(screen.getByRole("button", { name: "Deselect Alpha" }));
  expect(screen.getByText("1 selected")).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Search available models"), {
    target: { value: "" },
  });
  expect(
    screen.getByRole("checkbox", { name: "Select Alpha" }),
  ).not.toBeChecked();
  expect(screen.getByRole("checkbox", { name: "Select Beta" })).toBeChecked();
  fireEvent.click(screen.getByRole("button", { name: "Import selected" }));
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith(
      "/api/v1/admin/providers/1/models/import",
      { payload: { model_ids: ["beta"] } },
    ),
  );
  expect(await screen.findByText("Imported 1 model")).toBeTruthy();
  expect(screen.queryByRole("region", { name: "Selected models" })).toBeNull();
});

test("refresh clears selections that may no longer be in the catalog", async () => {
  const api = vi.mocked(apiFetch);
  let refreshed = false;
  api.mockImplementation(async (url) => {
    if (url.endsWith("/providers/1/models")) {
      return {
        provider: { name: "OpenRouter" },
        models: refreshed
          ? [{ id: "beta", name: "Beta", pricing: { prompt: "0.000001" } }]
          : [
              {
                id: "alpha",
                name: "Alpha",
                pricing: { prompt: "0.000001" },
              },
              { id: "beta", name: "Beta", pricing: { prompt: "0.000001" } },
            ],
      };
    }
    refreshed = true;
    return {};
  });
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={["/providers/1"]}>
        <Routes>
          <Route path="/providers/:id" element={<ModelBrowserPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  fireEvent.click(
    await screen.findByRole("checkbox", { name: "Select Alpha" }),
  );
  expect(screen.getByText("1 selected")).toBeTruthy();
  fireEvent.click(
    screen.getByRole("button", { name: "Refresh models and costs" }),
  );
  await waitFor(() =>
    expect(
      screen.queryByRole("region", { name: "Selected models" }),
    ).toBeNull(),
  );
  expect(
    screen.queryByRole("button", { name: "Import selected" }),
  ).toBeDisabled();
});

test("model list refreshes provider costs and reports partial failures", async () => {
  const api = vi.mocked(apiFetch);
  let refreshed = false;
  api.mockImplementation(async (url) => {
    if (url.endsWith("/pricing/refresh")) {
      refreshed = true;
      return {
        message: "Refreshed costs for 1 models.",
        failures: [
          "Could not refresh costs from Offline; saved prices were kept.",
        ],
      };
    }
    return {
      models: [
        {
          id: 1,
          name: "Alpha",
          provider_name: "OpenRouter",
          pricing: { prompt: refreshed ? "0.000001" : "0.0000005" },
        },
      ],
      providers: [],
    };
  });
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <ModelListPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  expect(await screen.findByText("$0.5")).toBeTruthy();
  fireEvent.click(
    screen.getByRole("button", { name: "Refresh costs from providers" }),
  );
  expect(await screen.findByText("$1")).toBeTruthy();
  expect(screen.getByRole("alert")).toHaveTextContent("Offline");
});

test("missing prices, free rates, and per-image rates are distinct", () => {
  const view = render(<ModelCosts pricing={{}} />);
  expect(screen.getByText("Pricing unavailable")).toBeTruthy();
  view.rerender(
    <ModelCosts
      pricing={{ prompt: "0", image: "0.04", completion: "invalid" }}
    />,
  );
  expect(screen.getByText("$0 input / 1M tokens")).toBeTruthy();
  expect(screen.getByText("$0.04 / input image")).toBeTruthy();
  expect(screen.queryByText(/NaN/)).toBeNull();
  view.rerender(
    <ModelCosts
      pricing={{ prompt: "0.000001", input_cache_read: "0.0000001" }}
    />,
  );
  expect(screen.queryByText(/cached input/)).toBeNull();
});

test("sync explains its scope and requires confirmation", async () => {
  const api = vi.mocked(apiFetch);
  api.mockImplementation(async (url) =>
    url.endsWith("/sync")
      ? { message: "Sync complete" }
      : { provider: { name: "OpenRouter" }, models: [] },
  );
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={["/providers/1"]}>
        <Routes>
          <Route path="/providers/:id" element={<ModelBrowserPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  const sync = await screen.findByRole("button", {
    name: "Sync imported models",
  });
  expect(
    screen.getByText(/Sync updates all imported models/),
  ).toHaveTextContent("deletes those no longer available");
  fireEvent.click(sync);
  expect(api).not.toHaveBeenCalledWith(
    "/api/v1/admin/providers/1/models/sync",
    expect.anything(),
  );
  confirm.mockReturnValue(true);
  fireEvent.click(sync);
  expect(await screen.findByText("Sync complete")).toBeTruthy();
  expect(api).toHaveBeenCalledWith("/api/v1/admin/providers/1/models/sync", {
    payload: {},
  });
});

test("HeroUI table sorting and shared switches and selects update the results", async () => {
  const api = vi.mocked(apiFetch);
  api.mockResolvedValue({
    providers: [],
    models: [
      {
        id: 1,
        name: "Alpha",
        pricing: { prompt: "0.000001", completion: "0.000002" },
      },
      { id: 2, name: "Free", pricing: { prompt: "0", completion: "0" } },
      { id: 3, name: "UnpricedModel", pricing: {} },
      { id: 4, name: "Image", pricing: {}, image_generation: true },
    ],
  });
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <ModelListPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  const header = await screen.findByRole("columnheader", {
    name: /Input cost/,
  });
  expect(screen.queryByRole("columnheader", { name: /Image cost/ })).toBeNull();
  expect(
    screen.queryByRole("columnheader", { name: /Other costs/ }),
  ).toBeNull();
  const drawer = screen.getByRole("button", { name: "Filter and sort models" });
  expect(drawer).toHaveAttribute("aria-expanded", "false");
  expect(
    screen.queryByRole("switch", { name: "Exclude free models" }),
  ).toBeNull();
  expect(
    screen.getByText("Image · Image generation (unavailable)"),
  ).toBeTruthy();
  fireEvent.click(drawer);
  expect(drawer).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByLabelText("Max input (¢ / 1M tokens)")).toHaveValue(null);
  fireEvent.change(screen.getByLabelText("Max input (¢ / 1M tokens)"), {
    target: { value: "100" },
  });
  fireEvent.click(header);
  expect(header).toHaveAttribute("aria-sort", "ascending");
  fireEvent.click(header);
  await waitFor(() =>
    expect(header).toHaveAttribute("aria-sort", "descending"),
  );
  const rows = screen.getAllByRole("row");
  expect(rows[1]).toHaveTextContent("Alpha");
  expect(rows[2]).toHaveTextContent("Free");
  fireEvent.click(screen.getByRole("switch", { name: "Exclude free models" }));
  expect(screen.queryByText("Free", { exact: true })).toBeNull();
  const includeUnknown = screen.getByRole("switch", {
    name: "Include unknown or variable token prices",
  });
  expect(includeUnknown).toBeChecked();
  fireEvent.click(includeUnknown);
  expect(screen.queryByText(/UnpricedModel/)).toBeNull();
  fireEvent.click(includeUnknown);
  expect(screen.getByText(/UnpricedModel/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: /Output type/ }));
  fireEvent.click(await screen.findByRole("option", { name: "image" }));
  expect(
    await screen.findByText("Image · Image generation (unavailable)"),
  ).toBeTruthy();
  expect(screen.queryByText("Alpha", { exact: true })).toBeNull();
  expect(screen.getByRole("columnheader", { name: /Image cost/ })).toBeTruthy();
  fireEvent.click(drawer);
  expect(drawer).toHaveAttribute("aria-expanded", "false");
  expect(
    screen.queryByRole("switch", { name: "Exclude free models" }),
  ).toBeNull();
  expect(
    screen.getByText("Image · Image generation (unavailable)"),
  ).toBeTruthy();
  fireEvent.click(drawer);
  expect(
    screen.getByRole("switch", { name: "Exclude free models" }),
  ).toBeChecked();
});

test("direct provider rates expose their official source and checked date", () => {
  render(
    <ModelCosts
      pricing={{ prompt: "0.000001", completion: "0.000005" }}
      source="https://platform.claude.com/docs/en/about-claude/pricing"
      updatedAt="2026-10-19T12:00:00Z"
      note="Standard base input/output rates."
    />,
  );
  expect(
    screen.getByRole("link", { name: "Official pricing" }),
  ).toHaveAttribute(
    "href",
    "https://platform.claude.com/docs/en/about-claude/pricing",
  );
  expect(screen.getByText(/Checked/)).toBeTruthy();
  expect(screen.getByText("$1 input / 1M tokens")).toBeTruthy();
  expect(screen.getByText("$5 output / 1M tokens")).toBeTruthy();
});

function mobileViewport() {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: query === "(max-width: 767px)",
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  );
}

test("mobile model drawers reveal details and keep deletion behind confirmation", async () => {
  mobileViewport();
  const api = vi.mocked(apiFetch);
  let deleted = false;
  api.mockImplementation(async (_url, options) => {
    if (options?.method === "DELETE") {
      deleted = true;
      return { deleted: true };
    }
    return {
      providers: [],
      models: deleted
        ? []
        : [
            {
              id: 7,
              name: "Pocket model",
              model_identifier: "maker/a-very-long-model-identifier",
              is_available: true,
              provider_name: "Direct provider",
              context_length: 128000,
              pricing: { prompt: "0.000001", completion: "0.000002" },
              pricing_source: "https://developers.openai.com/api/docs/pricing",
            },
          ],
    };
  });
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <ModelListPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  const details = await screen.findByRole("button", {
    name: "Details for Pocket model",
  });
  expect(screen.queryByRole("grid")).toBeNull();
  expect(details).toHaveAttribute("aria-expanded", "false");
  expect(screen.queryByRole("button", { name: "Delete" })).toBeNull();
  expect(screen.getByText("$1 input / 1M tokens")).toBeTruthy();
  fireEvent.click(details);
  expect(details).toHaveAttribute("aria-expanded", "true");
  expect(
    await screen.findByText("maker/a-very-long-model-identifier"),
  ).toBeTruthy();
  expect(screen.getByText("128,000 tokens")).toBeTruthy();
  expect(screen.queryByRole("link", { name: "Official pricing" })).toBeNull();
  expect(screen.queryByText("Other costs and pricing source")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Delete" }));
  expect(deleted).toBe(false);
  confirm.mockReturnValue(true);
  fireEvent.click(screen.getByRole("button", { name: "Delete" }));
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith("/api/v1/admin/models/7", {
      method: "DELETE",
    }),
  );
  expect(await screen.findByText("No models match.")).toBeTruthy();
});

test("mobile import selection works independently from expanding model details", async () => {
  mobileViewport();
  const api = vi.mocked(apiFetch);
  api.mockImplementation(async (url) =>
    url.endsWith("/import")
      ? { message: "Imported pocket model" }
      : {
          provider: { name: "OpenRouter" },
          models: [
            {
              id: "maker/pocket",
              name: "Pocket",
              context_length: 32000,
              pricing: { prompt: "0.000001" },
            },
          ],
        },
  );
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={["/providers/1"]}>
        <Routes>
          <Route path="/providers/:id" element={<ModelBrowserPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  const select = await screen.findByRole("checkbox", { name: "Select Pocket" });
  const details = screen.getByRole("button", { name: "Details for Pocket" });
  fireEvent.click(select);
  expect(select).toBeChecked();
  expect(details).toHaveAttribute("aria-expanded", "false");
  fireEvent.click(details);
  expect(screen.getByText("32,000 tokens")).toBeTruthy();
  expect(select).toBeChecked();
  expect(screen.queryByRole("button", { name: "Delete" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Import selected" }));
  expect(await screen.findByText("Imported pocket model")).toBeTruthy();
  expect(api).toHaveBeenCalledWith("/api/v1/admin/providers/1/models/import", {
    payload: { model_ids: ["maker/pocket"] },
  });
});

test("provider browse shows image cost only with image output selected", async () => {
  vi.mocked(apiFetch).mockResolvedValue({
    provider: { name: "OpenRouter" },
    models: [
      { id: "text", name: "Text model", pricing: { prompt: "0" } },
      {
        id: "provider/image-model",
        name: "Image model",
        image_generation: true,
        pricing: { prompt: "0", image_token: "0.000002" },
      },
    ],
  });
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={["/providers/1"]}>
        <Routes>
          <Route path="/providers/:id" element={<ModelBrowserPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  await screen.findByRole("checkbox", { name: "Select Text model" });
  expect(screen.queryByRole("columnheader", { name: /Image cost/ })).toBeNull();
  expect(
    screen.queryByRole("columnheader", { name: /Other costs/ }),
  ).toBeNull();
  fireEvent.click(
    screen.getByRole("button", { name: "Filter and sort models" }),
  );
  fireEvent.click(screen.getByRole("button", { name: /Output type/ }));
  fireEvent.click(await screen.findByRole("option", { name: "image" }));
  expect(
    await screen.findByRole("columnheader", { name: /Image cost/ }),
  ).toBeTruthy();
  expect(screen.getByText("$2")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: /Sort by/ }));
  fireEvent.click(
    await screen.findByRole("option", {
      name: "Image token cost: low to high",
    }),
  );
  expect(
    screen.getByRole("columnheader", { name: /Image cost/ }),
  ).toHaveAttribute("aria-sort", "ascending");
  fireEvent.click(screen.getByRole("button", { name: /Output type/ }));
  fireEvent.click(await screen.findByRole("option", { name: /^text$/ }));
  expect(screen.queryByRole("columnheader", { name: /Image cost/ })).toBeNull();
  expect(screen.getByRole("button", { name: /Sort by/ })).toHaveTextContent(
    "Name: A–Z",
  );
  fireEvent.click(screen.getByRole("button", { name: /Sort by/ }));
  expect(screen.queryByRole("option", { name: /Image token cost/ })).toBeNull();
});

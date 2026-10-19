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
  expect(screen.getByText("$1 input / 1M tokens")).toBeTruthy();
  expect(screen.getByText("$4 output / 1M tokens")).toBeTruthy();
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
  expect(await screen.findByText("$0.5 input / 1M tokens")).toBeTruthy();
  fireEvent.click(
    screen.getByRole("button", { name: "Refresh costs from providers" }),
  );
  expect(await screen.findByText("$1 input / 1M tokens")).toBeTruthy();
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
  fireEvent.click(
    screen.getByRole("switch", {
      name: "Include unknown or variable token prices",
    }),
  );
  expect(screen.getByText(/UnpricedModel/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: /Output type/ }));
  fireEvent.click(
    await screen.findByRole("option", { name: "image" }),
  );
  expect(
    await screen.findByText("Image · Image generation (unavailable)"),
  ).toBeTruthy();
  expect(screen.queryByText("Alpha", { exact: true })).toBeNull();
});

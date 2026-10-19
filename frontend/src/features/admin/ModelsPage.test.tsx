import { vi, test, expect, afterEach } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { ModelListPage } from "./ModelsPage";
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

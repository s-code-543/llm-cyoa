import { vi, test, expect } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import { PromptEditPage } from "./PromptsPage";
import { apiFetch } from "../../api/client";

vi.mock("../../api/client", async (original) => ({
  ...(await original<typeof import("../../api/client")>()),
  apiFetch: vi.fn(),
}));
const api = vi.mocked(apiFetch);

const prompt = {
  id: 4, type: "classifier", name: "detect", version: 1, description: "old",
  prompt_text: "text", file_path: "", versions: [{ id: 4, version: 1, description: "old" }],
};

test("editing a prompt saves the description", async () => {
  api.mockImplementation(async (url, init) =>
    init?.method === "PUT"
      ? { ...prompt, description: (init.payload as { description: string }).description }
      : url.endsWith("/prompts") ? { types: [], prompts: [] } : prompt,
  );
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={["/manage/prompts/4"]}>
        <Routes><Route path="/manage/prompts/:id" element={<PromptEditPage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  const field = await screen.findByLabelText("Description");
  fireEvent.change(field, { target: { value: "new" } });
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  expect(await screen.findByText("Saved detect v1")).toBeTruthy();
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith("/api/v1/admin/prompts/4", {
      method: "PUT",
      payload: { description: "new", prompt_text: "text" },
    }),
  );
});

import { vi, test, expect, beforeEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import { ProviderEditPage } from "./ProvidersPage";
import { ConfigNewPage } from "./ConfigPages";
import { WorkflowEditor } from "./WorkflowEditor";
import { ApiError, apiFetch } from "../../api/client";

vi.mock("../../api/client", async (original) => ({
  ...(await original<typeof import("../../api/client")>()),
  apiFetch: vi.fn(),
}));
const api = vi.mocked(apiFetch);
beforeEach(() => {
  cleanup();
  api.mockReset();
});

const wrap = (path: string, route: string, element: React.ReactNode) =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[path]}>
        <Routes><Route path={route} element={element} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );

test("provider form never shows the stored key and keeps it when blank", async () => {
  const provider = {
    id: 3, name: "OR", provider_type: "openrouter", base_url: "", has_api_key: true,
    api_key_hint: "7890", is_active: true, last_tested: null, test_status: "", model_count: 0,
  };
  api.mockImplementation(async (_url, init) =>
    init?.method === "PUT"
      ? provider
      : { types: [{ value: "openrouter", label: "OpenRouter" }], providers: [provider] },
  );
  wrap("/manage/providers/3", "/manage/providers/:id", <ProviderEditPage />);
  const key = (await screen.findByLabelText("API key")) as HTMLInputElement;
  expect(key.value).toBe("");
  expect(key.placeholder).toContain("7890");
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith(
      "/api/v1/admin/providers/3",
      expect.objectContaining({ method: "PUT", payload: expect.objectContaining({ api_key: "" }) }),
    ),
  );
});

test("provider connection test reports the result", async () => {
  const provider = {
    id: 3, name: "OR", provider_type: "openrouter", base_url: "", has_api_key: true,
    api_key_hint: "7890", is_active: true, last_tested: null, test_status: "", model_count: 0,
  };
  api.mockImplementation(async (url) =>
    url.endsWith("/test")
      ? { success: true, message: "reachable" }
      : { types: [{ value: "openrouter", label: "OpenRouter" }], providers: [provider] },
  );
  wrap("/manage/providers/3", "/manage/providers/:id", <ProviderEditPage />);
  fireEvent.click(await screen.findByRole("button", { name: "Test connection" }));
  expect(await screen.findByText(/Connection OK: reachable/)).toBeTruthy();
});

test("configuration form shows server validation inline", async () => {
  const options = {
    adventure_prompts: [], turn_correction_prompts: [], game_ending_prompts: [],
    classifier_prompts: [], judge_prompts: [], models: [], difficulties: [],
  };
  api.mockImplementation(async (_url, init) => {
    if (init?.method === undefined && init?.payload === undefined) return options;
    throw new ApiError("Please fix the highlighted fields.", 400, "validation_failed", undefined, {
      name: "Configuration name is required.",
    });
  });
  wrap("/manage/configurations/new", "/manage/configurations/new", <ConfigNewPage />);
  fireEvent.click(await screen.findByRole("button", { name: "Create configuration" }));
  expect(await screen.findByText("Configuration name is required.")).toBeTruthy();
});

test("workflow editor adds, reorders and removes steps", () => {
  let value: { version?: number; nodes?: { type: string }[] } = {};
  const onChange = vi.fn((next) => (value = next));
  const { rerender } = render(<WorkflowEditor value={value} onChange={onChange} />);
  fireEvent.change(screen.getByLabelText("Step type"), { target: { value: "ApplyRandomPrompt" } });
  fireEvent.click(screen.getByRole("button", { name: "Add step" }));
  const types = () => value.nodes!.map((n) => n.type);
  expect(types()).toEqual([
    "ApplyDifficulty", "ConcatenatePrompt", "ApplyRandomPrompt", "GenerateTurn",
    "ReWriteRefusal", "ReWriteJudge", "ValidateTurn", "SaveGame",
  ]);
  rerender(<WorkflowEditor value={value} onChange={onChange} />);
  fireEvent.click(screen.getByRole("button", { name: "Move step 3 up" }));
  expect(types().slice(0, 3)).toEqual(["ApplyDifficulty", "ApplyRandomPrompt", "ConcatenatePrompt"]);
  rerender(<WorkflowEditor value={value} onChange={onChange} />);
  fireEvent.click(screen.getByRole("button", { name: "Remove step 2" }));
  expect(types()).not.toContain("ApplyRandomPrompt");
});

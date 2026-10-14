import { vi, beforeEach, test, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { AppRoutes } from "./App";
import { apiFetch } from "../api/client";

vi.mock("../api/client", async (original) => ({
  ...(await original<typeof import("../api/client")>()),
  apiFetch: vi.fn(),
}));
const api = vi.mocked(apiFetch);

function show(path: string, permissions: string[] | null) {
  api.mockImplementation(async (url) =>
    url === "/api/v1/session"
      ? {
          user: permissions
            ? { username: "u", email: "", display_name: "Pat" }
            : null,
          permissions: permissions ?? [],
        }
      : url === "/api/v1/admin/dashboard"
        ? {
            total_requests: 3,
            total_refusals: 1,
            total_corrections: 1,
            correction_rate: 33.3,
            recent: [],
          }
        : { recent_games: [], configurations: [] },
  );
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
beforeEach(() => api.mockReset());

test("players do not see the administration menu or its pages", async () => {
  show("/manage", ["play"]);
  expect(await screen.findByText("Access denied")).toBeTruthy();
  expect(screen.queryByRole("link", { name: "Administration" })).toBeNull();
  expect(screen.getByRole("link", { name: "Adventures" })).toBeTruthy();
});

test("admins see the administration menu", async () => {
  show("/manage", ["play", "admin"]);
  expect(
    await screen.findByRole("heading", { name: "Dashboard" }),
  ).toBeTruthy();
  expect(await screen.findByText("33.3%")).toBeTruthy();
  expect(screen.getByRole("link", { name: "Prompts" })).toBeTruthy();
  expect(screen.getByRole("link", { name: "Administration" })).toBeTruthy();
});

test("signed-out visitors are sent to sign in", async () => {
  show("/", null);
  expect(await screen.findByRole("button", { name: "Sign in" })).toBeTruthy();
});

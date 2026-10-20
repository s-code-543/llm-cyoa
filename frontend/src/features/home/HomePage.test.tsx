import { test, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { HomePage } from "./HomePage";
import { getHome } from "../../api/home";
vi.mock("../../api/home", () => ({ getHome: vi.fn(), deleteGame: vi.fn() }));

test("unplayable adventures stay visible with a reason and cannot navigate", async () => {
  vi.mocked(getHome).mockResolvedValue({
    configurations: [],
    recent_games: [
      {
        id: "game-1",
        title: "Saved adventure",
        turn: 2,
        max_turns: 10,
        updated_at: "",
        unavailable_reason: "This configuration has been disabled.",
      },
    ],
  });
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  const link = await screen.findByRole("link", { name: /Saved adventure/ });
  expect(link).toHaveAttribute("aria-disabled", "true");
  expect(link).toHaveAttribute(
    "title",
    "This configuration has been disabled.",
  );
  expect(fireEvent.click(link)).toBe(false);
  expect(
    screen.getByText("This configuration has been disabled."),
  ).toBeTruthy();
  expect(screen.getByRole("button", { name: "Delete" })).toBeEnabled();
});

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
import { ChatsPage } from "./ChatsPage";
import { getAdminChats } from "../../api/admin";

vi.mock("../../api/admin", () => ({ getAdminChats: vi.fn() }));
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

test("admins can find and open another user's chat in debug mode", async () => {
  const api = vi.mocked(getAdminChats);
  api.mockResolvedValue({
    chats: [
      {
        id: "chat-id",
        title: "Lost in the woods",
        owner: "player@example.com",
        updated_at: "2026-10-18T12:00:00Z",
      },
    ],
    has_more: true,
  });
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <ChatsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  expect(await screen.findByText("player@example.com")).toBeTruthy();
  expect(screen.getByRole("link", { name: "Inspect chat" })).toHaveAttribute(
    "href",
    "/chat?conversation_id=chat-id&debug=true",
  );
  fireEvent.click(screen.getByRole("button", { name: "Next" }));
  await waitFor(() => expect(api).toHaveBeenCalledWith("", 50));
  fireEvent.change(screen.getByLabelText("Search chats"), {
    target: { value: "player@example.com" },
  });
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith("player@example.com", 0),
  );
});

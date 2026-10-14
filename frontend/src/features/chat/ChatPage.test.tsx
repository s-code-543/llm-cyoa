import { vi, beforeEach, test, expect } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ChatPage } from "./ChatPage";
import { request } from "../../api/chat";
vi.mock("../../api/chat", async (original) => ({
  ...(await original<typeof import("../../api/chat")>()),
  request: vi.fn(),
}));
const api = vi.mocked(request);
const game = {
  id: "test",
  title: "Arctic expedition",
  configuration: { id: 1, name: "Arctic expedition" },
  messages: [
    {
      id: 1,
      role: "assistant",
      content:
        "**Turn 1 of 10**\n\nThe snow is deep.\n\n<script>danger()</script>",
      is_error: false,
      created_at: "2026-10-11T08:00:00Z",
    },
  ],
  state: {
    turn: 1,
    max_turns: 10,
    choices: ["Enter", "Wait"],
    inventory: [],
    blocked: false,
    game_over: false,
  },
  capabilities: { tts: false },
  pending_request_id: null,
};
beforeEach(() => {
  window.history.replaceState({}, "", "/chat");
  api.mockReset();
  localStorage.clear();
  api.mockImplementation(async (path) =>
    path === "bootstrap"
      ? { configurations: [{ id: 1, name: "Arctic expedition" }] }
      : { conversation: game },
  );
});
function show() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <ChatPage />
    </QueryClientProvider>,
  );
}
test("does not create a conversation on mount and requires an explicit start", async () => {
  show();
  await screen.findByRole("radio", { name: "Arctic expedition" });
  expect(api.mock.calls.every(([, payload]) => payload === undefined)).toBe(
    true,
  );
  fireEvent.click(screen.getByRole("radio", { name: "Arctic expedition" }));
  fireEvent.click(screen.getByRole("button", { name: "Open adventure →" }));
  await screen.findByText("The snow is deep.");
  expect(
    api.mock.calls.filter(
      ([path, payload]) => path === "conversations" && payload,
    ),
  ).toHaveLength(1);
  expect(document.querySelector("script")).toBeNull();
});
test("a failed send preserves the action draft and does not automatically retry", async () => {
  show();
  await screen.findByRole("radio", { name: "Arctic expedition" });
  fireEvent.click(screen.getByRole("radio", { name: "Arctic expedition" }));
  fireEvent.click(screen.getByRole("button", { name: "Open adventure →" }));
  const action = await screen.findByLabelText("Your action");
  api.mockImplementation(async (path) => {
    if (path.endsWith("/turns")) throw new Error("Connection lost");
    return { conversation: game };
  });
  fireEvent.change(action, { target: { value: "Open the door" } });
  fireEvent.click(screen.getByRole("button", { name: "Send action" }));
  await screen.findByRole("alert");
  expect(action).toHaveValue("Open the door");
  await waitFor(() =>
    expect(
      api.mock.calls.filter(([path]) => path.endsWith("/turns")),
    ).toHaveLength(1),
  );
});

test("renders the authoritative next turn and sends a chosen action only once", async () => {
  show();
  await screen.findByRole("radio", { name: "Arctic expedition" });
  fireEvent.click(screen.getByRole("radio", { name: "Arctic expedition" }));
  fireEvent.click(screen.getByRole("button", { name: "Open adventure →" }));
  await screen.findByText("The snow is deep.");
  api.mockImplementation(async (path) =>
    path.endsWith("/turns")
      ? {
          conversation: {
            ...game,
            messages: [
              ...game.messages,
              {
                id: 2,
                role: "assistant",
                content: "A door opens.",
                created_at: "2026-10-11T08:01:00Z",
                is_error: false,
              },
            ],
            state: { ...game.state, turn: 2, choices: ["Look", "Leave"] },
          },
        }
      : { conversation: game },
  );
  const choice = screen.getByRole("button", { name: /01\s*Enter/ });
  fireEvent.click(choice);
  fireEvent.click(choice);
  await screen.findByText("A door opens.");
  expect(
    api.mock.calls.filter(([path]) => path.endsWith("/turns")),
  ).toHaveLength(1);
  expect(
    api.mock.calls.find(([path]) => path.endsWith("/turns"))?.[1],
  ).toMatchObject({ message: "Enter" });
  expect(screen.getByRole("button", { name: /01\s*Look/ })).toBeInTheDocument();
});

test("rollback requires confirmation and accepts the returned transcript", async () => {
  api.mockImplementation(async (path) =>
    path === "bootstrap"
      ? { configurations: [{ id: 1, name: "Arctic expedition" }] }
      : path.endsWith("/rollback")
        ? { conversation: game }
        : {
            conversation: {
              ...game,
              messages: [
                ...game.messages,
                {
                  id: 2,
                  role: "user",
                  content: "Wait",
                  created_at: "2026-10-11T08:01:00Z",
                  is_error: false,
                },
              ],
            },
          },
  );
  show();
  await screen.findByRole("radio", { name: "Arctic expedition" });
  fireEvent.click(screen.getByRole("radio", { name: "Arctic expedition" }));
  fireEvent.click(screen.getByRole("button", { name: "Open adventure →" }));
  fireEvent.click(
    await screen.findByRole("button", { name: "↶ Continue from here" }),
  );
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  expect(api.mock.calls.some(([path]) => path.endsWith("/rollback"))).toBe(
    false,
  );
  fireEvent.click(screen.getByRole("button", { name: /^Roll back$/ }));
  await waitFor(() =>
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
  );
  expect(
    api.mock.calls.find(([path]) => path.endsWith("/rollback"))?.[1],
  ).toMatchObject({ message_id: 1 });
});

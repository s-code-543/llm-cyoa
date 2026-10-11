export type Message = {
  id: number;
  role: "user" | "assistant";
  content: string;
  is_error: boolean;
  created_at: string;
};
export type Configuration = { id: number; name: string };
export type Conversation = {
  id: string;
  title: string;
  configuration: Configuration | null;
  messages: Message[];
  state: {
    turn: number;
    max_turns: number;
    choices: string[];
    inventory: string[];
    blocked: boolean;
    game_over: boolean;
  };
  capabilities: { tts: boolean };
  pending_request_id: string | null;
};
export type Envelope = {
  conversation: Conversation;
  request_id?: string;
  elapsed_ms?: number;
};
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code: string,
    public conversation?: Conversation,
  ) {
    super(message);
  }
}
export async function request<T>(path: string, payload?: unknown): Promise<T> {
  const token =
    document.querySelector<HTMLMetaElement>('meta[name="csrf-token"]')
      ?.content ?? "";
  const response = await fetch(`/api/v1/chat/${path}`, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-CSRFToken": token },
    ...(payload !== undefined
      ? { method: "POST", body: JSON.stringify(payload) }
      : {}),
  });
  if (
    !(response.headers.get("content-type") ?? "").includes("application/json")
  ) {
    throw new ApiError(
      response.status === 403
        ? "Your session or security token expired. Sign in again."
        : "The server is unavailable. Reload before trying again.",
      response.status,
      "invalid_response",
    );
  }
  const data = await response.json();
  if (!response.ok)
    throw new ApiError(
      data.error?.message ?? "Request failed",
      response.status,
      data.error?.code ?? "request_failed",
      data.conversation,
    );
  return data as T;
}

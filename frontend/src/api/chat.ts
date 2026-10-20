import { apiFetch } from "./client";
export type Message = {
  id: number;
  role: "user" | "assistant";
  content: string;
  is_error: boolean;
  image_url?: string | null;
  image_failed?: boolean;
  created_at: string;
};
export type Configuration = { id: number; name: string };
export type Conversation = {
  id: string;
  title: string;
  read_only?: boolean;
  unavailable_reason?: string | null;
  owner?: string;
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
export { ApiError } from "./client";
export async function request<T>(path: string, payload?: unknown): Promise<T> {
  return apiFetch<T>(`/api/v1/chat/${path}`, { payload });
}

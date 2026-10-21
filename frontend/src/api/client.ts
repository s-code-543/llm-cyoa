import type { Conversation } from "./chat";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code: string,
    public conversation?: Conversation,
    public fields: Record<string, string> = {},
  ) {
    super(message);
  }
}

function csrfToken() {
  const cookie = document.cookie
    .split("; ")
    .find((part) => part.startsWith("csrftoken="));
  return cookie
    ? decodeURIComponent(cookie.slice("csrftoken=".length))
    : (document.querySelector<HTMLMetaElement>('meta[name="csrf-token"]')
        ?.content ?? "");
}

export async function apiFetch<T>(
  url: string,
  init: { method?: string; payload?: unknown } = {},
): Promise<T> {
  const method = init.method ?? (init.payload !== undefined ? "POST" : "GET");
  const response = await fetch(url, {
    method,
    credentials: "same-origin",
    headers: {
      ...(init.payload instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      "X-CSRFToken": csrfToken(),
    },
    ...(init.payload !== undefined
      ? {
          body:
            init.payload instanceof FormData
              ? init.payload
              : JSON.stringify(init.payload),
        }
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
      data.error?.fields,
    );
  return data as T;
}
